"""잡 스냅샷 영속화 — data/jobs/{id}.json + data/jobs/{id}.log

aim-local 의 services/studio/jobstore.py 를 이식하고 두 가지를 더했다.
  · 로그 링버퍼 — 24번들 렌더는 약 1만 줄을 뱉는다. 잡 파일에 전부 담으면 파일과
    폴링 응답이 같이 부푼다. 스냅샷에는 최근 LOG_TAIL 줄만 두고, 전체는 별도
    append-only .log 파일에 미러링한다.
  · 쓰기 스로틀 — 렌더는 2초마다 줄을 뱉는다. 상태 전이는 즉시 저장하고, 로그만
    바뀐 경우는 1.5초에 최대 한 번만 fsync 한다.

_ID_RE 경로 이탈 가드는 원본 그대로 유지한다.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import tempfile
import threading
import time
from typing import Any

from core.constants import JOB_HISTORY, JOBS_DIR, LOG_TAIL

logger = logging.getLogger(__name__)

MAX_KEEP = JOB_HISTORY
_WRITE_LOCK = threading.Lock()
_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")
_THROTTLE_SEC = 1.5
_last_write: dict[str, float] = {}


def jobs_dir() -> str:
    os.makedirs(JOBS_DIR, exist_ok=True)
    return JOBS_DIR


def _path(job_id: str, ext: str = ".json") -> str | None:
    if not _ID_RE.match(job_id or ""):
        return None                      # 경로 이탈 방지 (id 는 uuid4().hex)
    return os.path.join(jobs_dir(), f"{job_id}{ext}")


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def save(job: dict[str, Any], *, force: bool = True) -> None:
    """잡 스냅샷 저장. 실패해도 렌더 자체를 막지 않는다.

    force=False 는 '로그만 바뀌었다' 는 뜻 — 스로틀에 걸리면 건너뛴다.
    """
    jid = job.get("id", "")
    path = _path(jid)
    if not path:
        return

    if not force:
        last = _last_write.get(jid, 0.0)
        if time.monotonic() - last < _THROTTLE_SEC:
            return

    try:
        rec = dict(job)
        rec["saved_at"] = now_iso()
        # 링버퍼 — 스냅샷에는 꼬리만 담는다.
        full = rec.get("log") or []
        rec["log_seq"] = job.get("log_seq", len(full))
        rec["log"] = full[-LOG_TAIL:]
        with _WRITE_LOCK:
            fd, tmp = tempfile.mkstemp(prefix=".job_", suffix=".json", dir=jobs_dir())
            os.close(fd)
            try:
                with open(tmp, "w", encoding="utf-8", newline="") as f:
                    json.dump(rec, f, ensure_ascii=False)
                os.replace(tmp, path)
            except Exception:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
        _last_write[jid] = time.monotonic()
        _prune()
    except Exception as e:
        logger.warning("잡 이력 저장 실패 (%s): %s", jid, e)


def append_log_file(job_id: str, lines: list[str]) -> None:
    """전체 로그를 append-only 파일에 미러링한다(링버퍼로 잘린 앞부분 보존).

    UTF-8 로 쓴다 — chodangi 의 로그 전문이 한국어다.
    """
    path = _path(job_id, ".log")
    if not path or not lines:
        return
    try:
        with open(path, "a", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


def log_path(job_id: str) -> str | None:
    p = _path(job_id, ".log")
    return p if p and os.path.isfile(p) else None


def load(job_id: str) -> dict[str, Any] | None:
    path = _path(job_id)
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    """최신순 요약 목록(사이드바용 가벼운 필드만)."""
    d = jobs_dir()
    try:
        names = [n for n in os.listdir(d) if n.endswith(".json")]
    except OSError:
        return []
    items = []
    for n in names:
        try:
            with open(os.path.join(d, n), encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:
            continue
        items.append(summary(rec))
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return items[:limit]


def summary(rec: dict[str, Any]) -> dict[str, Any]:
    """목록·사이드바가 쓰는 가벼운 요약."""
    return {
        "id": rec.get("id"),
        "kind": rec.get("kind"),
        "label": rec.get("label"),
        "status": rec.get("status"),
        "created_at": rec.get("created_at"),
        "finished_at": rec.get("finished_at"),
        "done_count": rec.get("done_count", 0),
        "total_count": rec.get("total_count", 0),
        "error": rec.get("error"),
        "note": rec.get("note"),
        "publish": {k: v for k, v in (rec.get("publish") or {}).items()
                    if k in ("dir", "files", "bytes", "dir_exists")} or None,
    }


def restore(jobs: dict[str, dict[str, Any]]) -> tuple[int, int]:
    """기동 시 메모리 레지스트리 복원.

    ★ running / queued 로 남아 있는 잡은 error 로 고쳐 쓴다. 스레드는 재시작을
      넘기지 못하는데 그 행이 영원히 running 으로 남으면 렌더 락이 영구히 막힌다.
    """
    restored = broken = 0
    for meta in list_jobs(limit=MAX_KEEP):
        jid = meta.get("id")
        if not jid or jid in jobs:
            continue
        rec = load(jid)
        if not rec:
            continue
        if rec.get("status") in ("running", "queued"):
            rec["status"] = "error"
            rec["error"] = "서버가 재시작되어 작업이 끊겼습니다."
            rec["finished_at"] = rec.get("finished_at") or now_iso()
            for it in (rec.get("items") or {}).values():
                if isinstance(it, dict) and it.get("status") in ("running", "queued"):
                    it["status"] = "error"
                    it["error"] = "서버 재시작으로 중단"
            save(rec)
            broken += 1
        pub = rec.get("publish")
        if isinstance(pub, dict) and pub.get("dir"):
            pub["dir_exists"] = os.path.isdir(pub["dir"])
        rec["restored"] = True
        jobs[jid] = rec
        restored += 1
    return restored, broken


def _prune() -> None:
    """MAX_KEEP 초과분(오래된 것부터) 정리. .log 짝도 같이 지운다."""
    d = jobs_dir()
    try:
        entries = [(os.path.getmtime(os.path.join(d, n)), n)
                   for n in os.listdir(d) if n.endswith(".json")]
    except OSError:
        return
    if len(entries) <= MAX_KEEP:
        return
    entries.sort()
    for _, n in entries[:len(entries) - MAX_KEEP]:
        for p in (os.path.join(d, n), os.path.join(d, n[:-5] + ".log")):
            try:
                os.remove(p)
            except OSError:
                pass
