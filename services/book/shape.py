"""이 책의 '형태' — 회차 수 · 회차당 문항 수 · 과목 수 · 번들 수.

★ 왜 모듈 하나를 따로 두는가

업로드본은 이 값들을 `core/constants.py` 에 상수로 뒀다.

    ROUND_CODES = ("m01", "m02", "m03")
    QUESTIONS_PER_ROUND = 80
    TOTAL_QUESTIONS = 240
    TOTAL_BUNDLES = 24
    SUBJECT_COUNT = 4

자사 회차가 **m01~m09(720문항 · 72번들)** 로 늘어날 예정이고, SQLD 는 이미 6회차 ·
300문항이다. 상수로 두면 사전점검이 "240개 기대" 를 들고 도는데, 그 리포트는
`과목 N종`·`NNN문제` 처럼 **숫자를 확인하는 것이 목적**이라서 기대값이 낡으면
검사가 조용히 무의미해진다.

그래서 전부 폴더에서 센다. 읽을 수 없을 때만 폴백을 쓰고, 폴백을 썼다는 사실을
같이 돌려준다 — 호출자가 "폴더에서 못 읽었다" 를 화면에 표시할 수 있게.
"""
from __future__ import annotations

import json
import os

from core.constants import FALLBACK_QUESTIONS_PER_ROUND, QUESTIONS_PER_BUNDLE
from services.book import paths


def round_codes() -> list[str]:
    """이 폴더에 실제로 있는 회차 코드. `_rounds/mNN.json` 을 센다."""
    return paths.round_codes()


def _round_doc(round_code: str) -> dict | None:
    try:
        with open(paths.rounds_json(round_code), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def questions_in_round(round_code: str) -> int:
    d = _round_doc(round_code)
    return len(d.get("questions") or []) if d else 0


def questions_per_round() -> int:
    """가장 흔한 회차 문항 수. 회차마다 다르면 최빈값을 쓴다.

    ★ 회차별로 다를 수 있다는 점이 중요하다. 마지막 회차를 집필하는 중이면
      그 회차만 30문항일 수 있고, 그때 "전부 80이어야 한다" 고 보면 사전점검이
      정상 상태를 오류로 부른다.
    """
    counts = [questions_in_round(rc) for rc in round_codes()]
    counts = [c for c in counts if c]
    if not counts:
        return FALLBACK_QUESTIONS_PER_ROUND
    return max(set(counts), key=counts.count)


def total_questions() -> int:
    """실제 문항 총수 — 회차 수 × 상수가 아니라 회차별 합이다."""
    return sum(questions_in_round(rc) for rc in round_codes())


def bundles_per_round(round_code: str) -> int:
    n = questions_in_round(round_code)
    if not n:
        return -(-questions_per_round() // QUESTIONS_PER_BUNDLE)
    return -(-n // QUESTIONS_PER_BUNDLE)          # 올림


def total_bundles() -> int:
    return len(paths.all_bundles())


def subjects() -> list[str]:
    """이 책의 과목명 — 첫 등장 순서. `_rounds` 가 원천이다."""
    out: list[str] = []
    for rc in round_codes():
        d = _round_doc(rc)
        for q in (d or {}).get("questions") or []:
            s = (q.get("subject") or "").strip()
            if s and s not in out:
                out.append(s)
    return out


def subject_count() -> int:
    """★ 4 로 못박으면 안 된다 — SQLD 는 2과목이다."""
    return len(subjects())


def summary() -> dict:
    """사전점검·화면이 쓰는 한 덩어리. 폴더에서 읽은 값인지도 같이 알려준다."""
    rcs = round_codes()
    per = {rc: questions_in_round(rc) for rc in rcs}
    return {
        "rounds": rcs,
        "round_count": len(rcs),
        "questions_per_round": questions_per_round(),
        "questions_by_round": per,
        "total_questions": total_questions(),
        "bundles": paths.all_bundles(),
        "total_bundles": total_bundles(),
        "subjects": subjects(),
        "subject_count": subject_count(),
        "questions_per_bundle": QUESTIONS_PER_BUNDLE,
        # 회차마다 문항 수가 다르면 화면이 그 사실을 알려야 한다.
        "uneven": len({v for v in per.values() if v}) > 1,
        "from_disk": bool(rcs),
    }
