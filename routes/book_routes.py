"""/api/book — BOOK 트리 개요 · 통계 · 상태.

BOOK 이 없으면 503 을 낸다. 앱을 죽이지는 않는다 — 그 설정을 고칠 화면이 남아
있어야 한다.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

from core.constants import PD_LABEL
from services.book import index as bindex, paths, rounds, shape

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
    """활성 폴더의 표시 이름. 없으면 .env 의 값으로 떨어진다.

    ★ 좌하단 칩이 이 값을 쓴다. 예전에는 셸이 /api/version 의 상수를 직접 봤는데,
      그러면 폴더 카드에서 이름을 고쳐도 칩이 바뀌지 않고, 폴더를 지정하지 않은
      첫 실행에도 이미 품목이 정해진 것처럼 보였다.
    """
    return (_active().get("label") or "").strip() or PD_LABEL


def _first_run() -> bool:
    """사람이 작업 폴더를 한 번도 지정하지 않았는가 (data/books.json 없음)."""
    try:
        from services.book import books
        return books.is_first_run()
    except Exception:
        return False


def setup_book_routes() -> APIRouter:
    router = APIRouter(prefix="/api/book", tags=["book"])

    def _require_book() -> None:
        if not paths.exists():
            raise HTTPException(
                status_code=503,
                detail=(f"이 작업 폴더는 아직 01/ 단계입니다: {paths.book_dir()}\n"
                        "문항 교정·영상·발행은 _rounds/ 와 02/ 가 있어야 열립니다 — "
                        "그 둘은 도구 #2(Claude Desktop 스킬)가 만듭니다. "
                        "지금 쓸 수 있는 화면은 'OCR 검수' 와 '구조화 MD로 정리' 입니다."),
            )

    @router.get("/info")
    async def info():
        """단계별 파일 수 · 회차 · 검수 진행률. 전 화면이 이걸로 시작한다."""
        if not paths.exists():
            # 여기서는 503 을 던지지 않는다 — 화면이 '경로 오류' 를 그려야 한다.
            return {
                "exists": False, "book": paths.book_dir(), "pd": _pd(),
                "pd_label": _label(), "first_run": _first_run(), "scan_only": paths.scan_exists(),
                "rounds": [], "total": 0, "reviewed": 0,
                "stages": {"01": {"md": _count_files("01", ".md")}},
                # ★ 사실대로 쓴다. 02/ 를 만드는 것은 이 앱의 화면이 아니라 도구 #2
                #   (Claude Desktop 스킬)다. 예전 문구가 "'구조화 MD로 정리' 로 02/ 를
                #   먼저 만드세요" 였는데, 그 화면은 01/ 을 손보는 곳이라 따라가면 막힌다.
                "error": (
                    f"이 작업 폴더는 아직 01/ 단계입니다: {paths.book_dir()}\n"
                    "문항 교정·영상·발행은 _rounds/ 와 02/ 가 있어야 열립니다 — "
                    "그 둘은 도구 #2(Claude Desktop 스킬)가 01/ 을 읽어 만듭니다."
                    if paths.scan_exists() else
                    f"이 작업 폴더에는 아직 아무 단계도 없습니다: {paths.book_dir()}\n"
                    "00/ 에 원본 PDF 를 넣고 'OCR 검수' 에서 [PDF 렌더] 부터 시작하세요."),
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
            "pd_label": _label(), "first_run": _first_run(),
            "scan_only": False,
            "total": res["total"],
            "reviewed": res["reviewed"],
            # 기대값도 폴더에서 센다. 상수로 두면 회차가 늘 때 조용히 낡는다.
            "expected_total": shape.total_questions(),
            "shape": shape.summary(),
            "rounds": round_rows,
            "stages": {
                "00": {"files": count_files("00")},
                "01": {"md": count_files("01", ".md")},
                "02": {"md": count_files("02", ".md"),
                       "assets": count_files(os.path.join("02", "assets"), ".svg")},
                "03": {"html": count_files("03", ".html"), "md": count_files("03", ".md"),
                       "keys": list(paths.summary_keys())},
                "04": {"json": count_files("04", ".json"),
                       "assets": count_files(os.path.join("04", "assets"), ".svg")},
                "05": {"bundles": sum(1 for b in paths.all_bundles()
                                      if os.path.isdir(paths.bundle_dir(b))),
                       "expected": shape.total_bundles()},
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
        # ★ "기대 240개" 를 상수로 들고 있으면 회차가 늘 때마다 이 경고가 잘못 뜬다.
        #   회차별 문항 수가 서로 다를 때만 알린다 — 그건 집필이 덜 끝난 신호다.
        sh = shape.summary()
        if sh["uneven"]:
            uneven = ", ".join(f"{k} {v}문" for k, v in sh["questions_by_round"].items())
            problems.append({"level": "warn",
                             "text": f"회차별 문항 수가 다릅니다 — {uneven}."})
        if res["total"] != sh["total_questions"]:
            problems.append({"level": "warn",
                             "text": f"색인 문항 {res['total']}개 vs "
                                     f"_rounds {sh['total_questions']}개 — 색인이 낡았습니다."})
        if res["reviewed"] < res["total"]:
            problems.append({"level": "warn",
                             "text": f"미검수 문항 {res['total'] - res['reviewed']}개 — "
                                     "전부 검수해야 발행할 수 있습니다."})
        return {"ok": not any(p["level"] == "error" for p in problems),
                "problems": problems}

    return router
