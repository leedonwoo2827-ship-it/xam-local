# -*- coding: utf-8 -*-
"""스테이징 파트 → `_rounds/mNN.json` **반입.**

★ 여기가 유일한 반입 통로다. 모델은 파일을 쓸 수 없고(`provider` 가 Write 금지),
  `draft` 는 `data/authoring/` 까지만 쓴다. 그래서 검증에 걸린 파트가 이미 검수된
  문항을 덮는 일이 구조적으로 불가능하다.

★ 문항번호로 **UPSERT** 한다. DELETE 하지 않는다 — 웹 임포트가
  `UNIQUE (pd_id, pr_key)` 위에서 UPSERT 인 것과 같은 규칙이다. 파트 3만 다시
  집필해도 나머지 70문항이 그대로 남아야 한다.

★ 저장 전 `.bak` 을 남긴다. 되돌리기가 rename 이 되게(계획의 "되돌리기 경계").
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from core.atomic_io import atomic_write_json, backup_sibling

from .draft import n_parts, round_size, staging_path

# 회차 머리 기본값 — **실측**이다. `_rounds/m01.json` ~ `m09.json` 이 전부 같았다
# (2026-08-10). 발명하면 렌더의 목소리·속도·카운트다운이 회차마다 갈린다.
ROUND_DEFAULTS: Dict[str, Any] = {
    # ★ 아래 둘은 **되돌림값**이다. 실제 값은 시험정보에서 온다
    #   (`round_defaults()`). 품목이 바뀌면 과목명·테마가 바뀌는데 상수로 두면
    #   SQLD 회차에 「빅데이터분석기사 · teal」 이 박힌다.
    "subject_default": "빅데이터분석기사",
    "theme": "teal",
    "voice": "F2",
    "speed": 1.05,
    "countdown_seconds": 5,
    "gap_seconds": 1.5,
    "ai_reading": False,
}

def round_defaults() -> Dict[str, Any]:
    """회차 머리 기본값 — 시험정보의 값을 덮어씌운 것.

    ★ 목소리·속도·카운트다운은 렌더 설정이라 실측 상수 그대로 쓴다.
      **과목명(`subject_default`)과 테마(`theme`)는 시험의 정체**라 품목에서 온다.
    """
    from services.authoring import parts

    d = parts.active() or {}
    out = dict(ROUND_DEFAULTS)
    if str(d.get("label") or "").strip():
        out["subject_default"] = str(d["label"]).strip()
    if str(d.get("theme") or "").strip():
        out["theme"] = str(d["theme"]).strip()
    return out


# `_rounds` 문항 키 순서 — 실측 순서 그대로. `build.py` 는 순서를 안 보지만,
# 사람이 diff 를 읽는다. 회차마다 키 순서가 흔들리면 diff 가 통째로 붉어진다.
ITEM_ORDER = ["question_no", "subject", "subject_no", "difficulty", "tags",
              "derived_from", "question", "passage", "table", "choices",
              "answer_index", "explanation", "explanation_speech", "assets"]


def rounds_path(book_dir: str, round_code: str) -> str:
    return os.path.join(book_dir, "_rounds", f"{round_code}.json")


def _round_head(round_code: str) -> Dict[str, Any]:
    n = int(round_code.lstrip("m") or 0)
    return {"round_code": round_code, "round": n,
            # ★ **「자사」 를 넣지 않는다.** 이 값이 vendor 빌더를 지나
            #   `04/lesson_*.json` 의 title·round·**narration** 으로 들어간다 —
            #   즉 음성과 자막에 그대로 나간다(실측: 빅분기 `04/lesson_m01.json` 의
            #   narration 이 「자사 모의고사 01회 빅데이터 분석 기획 문제입니다」).
            #   `bake.py` 는 2026-08-12 에 고쳤는데 이 값이 남아 다른 길로 새고 있었다.
            #   「자사·타사」 는 프롬프트·문서에서만 쓰는 말이다.
            "round_label": f"모의고사 {n:02d}회", **round_defaults()}


def _ordered(item: Dict[str, Any]) -> Dict[str, Any]:
    """키 순서를 실측 순서로 맞추고, 값이 없는 선택 키는 뺀다."""
    out: Dict[str, Any] = {}
    for k in ITEM_ORDER:
        if k in ("table", "assets"):
            if item.get(k):          # 빈 배열·None 이면 키 자체를 뺀다(실측과 같게)
                out[k] = item[k]
        elif k in item:
            out[k] = item[k]
    # 스키마 밖 키가 들어오면 조용히 버리지 않고 뒤에 붙인다 — 버리면 못 알아챈다
    for k, v in item.items():
        if k not in out:
            out[k] = v
    return out


def collect_ready(round_code: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """반입 가능한 파트만 모은다. 문제 있는 파트는 **건너뛰고 이유를 돌려준다.**"""
    items: List[Dict[str, Any]] = []
    blocked: List[str] = []
    for i in range(1, n_parts() + 1):
        p = staging_path(round_code, i)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            blocked.append(f"파트 {i}: 파일을 읽을 수 없습니다 — {e}")
            continue
        if not d.get("ok"):
            probs = d.get("problems") or ["사유 미기록"]
            blocked.append(f"파트 {i}: {probs[0]}"
                           + (f" (외 {len(probs)-1}건)" if len(probs) > 1 else ""))
            continue
        items += list(d.get("items") or [])
    return items, blocked


def merge_round(*, book_dir: str, round_code: str,
                dry_run: bool = False) -> Dict[str, Any]:
    """스테이징의 합격 파트를 `_rounds/mNN.json` 에 UPSERT 한다."""
    new_items, blocked = collect_ready(round_code)
    path = rounds_path(book_dir, round_code)

    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError) as e:
            return {"ok": False, "error": f"기존 회차 파일을 읽을 수 없습니다 — {e}",
                    "path": path}
        # ★ 머리 값은 **기존 것을 유지한다.** 사람이 목소리·속도를 바꿔 뒀을 수 있다.
        existing = {int(q.get("question_no", 0)): q for q in (doc.get("questions") or [])}
    else:
        doc = _round_head(round_code)
        existing = {}

    added, replaced = [], []
    for it in new_items:
        no = int(it.get("question_no", 0))
        (replaced if no in existing else added).append(no)
        existing[no] = _ordered(it)

    doc["questions"] = [existing[k] for k in sorted(existing)]
    total = len(doc["questions"])

    report = {
        "ok": bool(new_items) and not blocked,
        "path": path,
        "round": round_code,
        "added": sorted(added),
        "replaced": sorted(replaced),
        "total": total,
        # ★ 회차 크기는 시험정보에서. 상수(80)로 보면 SQLD(50) 는 영원히 미완성이다.
        "complete": total == round_size(),
        "blocked": blocked,
        "dry_run": dry_run,
    }
    if not new_items:
        report["ok"] = False
        report["error"] = ("반입할 파트가 없습니다 — 스테이징이 비었거나 "
                           "모든 파트가 검증에 걸렸습니다.")
        return report
    if blocked:
        # ★ 부분 반입을 하지 않는다. 합격 파트만 넣고 "됐다" 고 하면, 사람은 회차가
        #   완성된 줄 알고 다음 단계로 간다. 막고 무엇이 걸렸는지 보여 준다.
        report["error"] = "검증에 걸린 파트가 있어 반입을 멈췄습니다."
        return report

    if not dry_run:
        backup_sibling(path)
        atomic_write_json(path, doc, indent=2, trailing_newline=True)
    return report
