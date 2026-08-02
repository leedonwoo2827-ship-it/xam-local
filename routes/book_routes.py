"""/api/book — BOOK 트리 개요 · 통계 · 상태.

BOOK 이 없으면 503 을 낸다. 앱을 죽이지는 않는다 — 그 설정을 고칠 화면이 남아
있어야 한다.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

from core.constants import (
    PD_LABEL, SUMMARY_KEYS,
    TOTAL_BUNDLES, TOTAL_QUESTIONS,
)
from services.book import index as bindex, paths, rounds

logger = logging.getLogger(__name__)


def _count_files(sub: str, pattern: str = "") -> int:
    """★ 지금 고른 폴더에서 센다.

    상수 BOOK_DIR 로 세면, 회차는 활성 폴더에서 읽는데 단계별 개수는 .env 폴더에서
    나와 한 응답 안에 두 폴더가 섞인다. 실제로 그 버그가 있었다.
    """
    d = os.path.join(paths.book_dir(), sub)
    if not os.path.isdir(d):
        return 0
    return sum(1 for f in os.listdir(d)
               if (not pattern or f.endswith(pattern))
               and os.path.isfile(os.path.join(d, f)))


def _active() -> dict:
    try:
        from services.book import books
        return books.active_meta()
    except Exception:
        return {}


def _pd() -> str:
    """지금 고른 폴더의 품목 코드. 정해지지 않았으면 빈 문자열 — 상수로 되돌리지 않는다."""
    return (_active().get("pd") or "").strip()


def _label() -> str:
    return (_active().get("label") or "").strip() or PD_LABEL


def setup_book_routes() -> APIRouter:
    router = APIRouter(prefix="/api/book", tags=["book"])

    def _require_book() -> None:
        if not paths.exists():
            raise HTTPException(
                status_code=503,
                detail=(f"이 작업 폴더에는 문항이 없습니다: {paths.book_dir()}\n"
                        "_rounds/ 와 02/ 가 있는 폴더로 전환하세요. "
                        "01/ 만 있으면 '구조화 MD로 정리' 화면만 됩니다."),
            )

    @router.get("/info")
    async def info():
        """단계별 파일 수 · 회차 · 검수 진행률. 전 화면이 이걸로 시작한다."""
        if not paths.exists():
            # 여기서는 503 을 던지지 않는다 — 화면이 '경로 오류' 를 그려야 한다.
            return {
                "exists": False, "book": paths.book_dir(), "pd": _pd(),
                "pd_label": _label(), "scan_only": paths.scan_exists(),
                "rounds": [], "total": 0, "reviewed": 0,
                "stages": {"01": {"md": _count_files("01", ".md")}},
                "error": (f"이 작업 폴더에는 아직 문항이 없습니다: {paths.book_dir()}"
                          + (" — 01/ 기출은 있으니 '구조화 MD로 정리' 부터 하세요."
                             if paths.scan_exists() else "")),
            }

        count_files = _count_files
        res = bindex.query()
        round_rows = []
        for rc in paths.round_codes():
            path = paths.rounds_json(rc)
            if not os.path.isfile(path):
                continue
            doc = rounds.load(rc)
            rn = int(doc.get("round", 0))
            rows = [i for i in res["items"] if i["round"] == rn] if res["items"] else []
            all_rows = [i for i in bindex.cached_items() if i["round"] == rn]
            round_rows.append({
                "code": rc,
                "round": rn,
                "round_label": doc.get("round_label", ""),
                "count": len(doc.get("questions") or []),
                "reviewed": sum(1 for i in all_rows if i["reviewed"]),
                "etag": paths.etag(path),
            })

        return {
            "exists": True,
            "book": paths.book_dir(),
            "pd": _pd(),
            "pd_label": _label(),
            "scan_only": False,
            "total": res["total"],
            "reviewed": res["reviewed"],
            "expected_total": TOTAL_QUESTIONS,
            "rounds": round_rows,
            "stages": {
                "00": {"files": count_files("00")},
                "01": {"md": count_files("01", ".md")},
                "02": {"md": count_files("02", ".md"),
                       "assets": count_files(os.path.join("02", "assets"), ".svg")},
                "03": {"html": count_files("03", ".html"), "md": count_files("03", ".md"),
                       "keys": list(SUMMARY_KEYS)},
                "04": {"json": count_files("04", ".json"),
                       "assets": count_files(os.path.join("04", "assets"), ".svg")},
                "05": {"bundles": sum(1 for b in paths.all_bundles()
                                      if os.path.isdir(paths.bundle_dir(b))),
                       "expected": TOTAL_BUNDLES},
                "06": {"exists": os.path.isdir(paths.out_dir()),
                       "files": count_files("06")},
            },
            "facets": res["facets"],
        }

    @router.get("/stats")
    async def stats():
        """디스크의 difficulty_stats.json 과 지금 다시 계산한 값을 함께 준다.

        둘이 다르면 색인이 낡았다는 뜻이다 — 사전점검이 그걸 잡는다.
        """
        _require_book()
        import json
        items = bindex.cached_items()
        live = bindex.build_stats(items)
        on_disk = None
        if os.path.isfile(paths.q_stats()):
            with open(paths.q_stats(), encoding="utf-8") as f:
                on_disk = json.load(f)
        return {"live": live, "on_disk": on_disk, "stale": on_disk != live}

    @router.get("/health")
    async def health():
        """레일 배지용 값싼 요약."""
        problems = []
        if not paths.exists():
            problems.append({"level": "error",
                             "text": f"문항이 없는 작업 폴더: {paths.book_dir()}"})
            return {"ok": False, "problems": problems}

        for rc in paths.round_codes():
            if not os.path.isfile(paths.rounds_json(rc)):
                problems.append({"level": "error",
                                 "text": f"_rounds/{rc}.json 이 없습니다."})
        res = bindex.query()
        if res["total"] != TOTAL_QUESTIONS:
            problems.append({"level": "warn",
                             "text": f"문항 수가 {res['total']}개입니다 "
                                     f"(기대 {TOTAL_QUESTIONS}개)."})
        if res["reviewed"] < res["total"]:
            problems.append({"level": "warn",
                             "text": f"미검수 문항 {res['total'] - res['reviewed']}개 — "
                                     "전부 검수해야 발행할 수 있습니다."})
        return {"ok": not any(p["level"] == "error" for p in problems),
                "problems": problems}

    return router
