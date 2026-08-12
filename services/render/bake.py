# -*- coding: utf-8 -*-
"""`_rounds` → `05/<번들>/` **베이크.** 모델을 부르지 않는다 — 룰베이스 조립이다.

한 번들에 세 파일을 **한 번에** 쓴다:

    source/lesson_<번들>.json   부분 lesson (문항 10개 + 과목 머리)
    source/deck.html            슬라이드 (SVG 인라인)
    script/<번들>_script.json   씬 목록 (캡처 대상 · 낭독 · countdown/gap)

★ **왜 한 함수인가.** 렌더 드라이버에 불변식이 하나 있다 —
  `deck.html` 의 `.slide` 개수 == script 의 `capture:true` 씬 개수.
  어긋나면 그 자리에서 멈춘다(`bundles.py` 의 `ok_1to1`, 드라이버 주석도 같은 말).
  분할이 붙은 뒤로는 장수가 내용에 따라 달라지므로, 둘을 따로 만들면 반드시 갈린다.
  그래서 `render.build_pages()` 가 낸 **하나의 목록**에서 둘을 뽑는다.

★ 씬 구성 — 옛 번들(백업 260810) 실측을 그대로 따른다:

      cover      capture ✓
      section    (지금은 안 쓴다 — 과목 머리를 lesson 에만 둔다)
      problem    capture ✓   ← 분할되면 장마다 하나
      countdown  capture ✗   5초
      answer     capture ✓   ← 분할되면 장마다 하나
      gap        capture ✗   1.5초

★ 낭독은 **첫 장에만** 싣는다. 이어지는 장은 고정 시간을 준다 — 사용자가 그렇게
  정했다(2026-08-12: "문제+해설이 2장이냐 3장이냐는 … 이미지가 보이는 시간을 정할
  수도 있어요"). 낭독을 장 수로 억지로 나누면 문장이 중간에서 끊긴다.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from core.atomic_io import atomic_write_json, atomic_write_text
from core.constants import BOOK_DIR
from services.authoring.schema import SUBJECTS, subject_no_for
from services.book import lesson as lessonmod
from services.book import paths
from services.deck import render, theme

# 이어지는 장이 화면에 남는 시간(초). 낭독이 없는 장이므로 시간을 직접 준다.
CONT_SECONDS = 4
COUNTDOWN_SECONDS = 5
GAP_SECONDS = 1.5


def _round_doc(round_code: str) -> Dict[str, Any]:
    p = os.path.join(BOOK_DIR, "_rounds", f"{round_code}.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build_lesson(bundle: str) -> Dict[str, Any]:
    """번들의 부분 lesson. 머리 키는 백업 번들 실측을 따른다."""
    parsed = paths.parse_bundle(bundle)
    if not parsed:
        raise ValueError(f"번들 코드가 아닙니다: {bundle}")
    round_no, part = parsed
    rc = paths.round_code(round_no)
    lo, hi = paths.bundle_range(bundle)
    doc = _round_doc(rc)
    qs = [q for q in doc.get("questions") or []
          if lo <= int(q["question_no"]) <= hi]
    if len(qs) != hi - lo + 1:
        raise ValueError(f"{bundle}: 문항이 {len(qs)}개뿐입니다 ({lo}~{hi} 기대)")

    total_parts = 80 // paths.QUESTIONS_PER_BUNDLE
    subj_no = subject_no_for(lo)
    blocks: List[Dict[str, Any]] = [
        {"kind": "section", "title": f"{subj_no}과목 · {SUBJECTS[subj_no]}"}]
    prev = None
    for q in qs:
        blocks.append(lessonmod.block_from_rounds(q, prev))
        prev = q

    # ★ "자사" 를 쓰지 않는다(2026-08-12 지시).
    out = {
        "version": "1.0", "kind": "lesson",
        "chapter": round_no,
        "title": f"모의고사 {round_no:02d}회 — 문제 풀이 ({part}/{total_parts})",
        "subject": "빅데이터분석기사",
        "theme": doc.get("theme") or "teal",
        "scenes_per_problem": 2, "include_lecture": False,
        "countdown_seconds": COUNTDOWN_SECONDS, "gap_seconds": GAP_SECONDS,
        "round": f"모의고사 {round_no:02d}회",
        "voice": doc.get("voice") or "F2", "speed": doc.get("speed") or 1.05,
        "ai_reading": False, "part_index": part, "part_total": total_parts,
        "blocks": blocks,
    }
    return out


def _narration(meta: Dict[str, Any], block: Optional[Dict[str, Any]],
               lesson: Dict[str, Any]) -> str:
    """이 장의 낭독. 이어지는 장은 빈 문자열(고정 시간으로 넘긴다)."""
    if meta["page"] > 1:
        return ""
    if meta["kind"] == "cover":
        # ★ 회차를 **읽지 않는다**(2026-08-12 지시). `round` 는 "모의고사 01회" 라서
        #   TTS 가 "공일회" 로 읽었다. 회차는 화면(표지 제목)에 이미 있다.
        #   ★ 빈 문자열로 두면 안 된다 — make_bundle_video 가 낭독이 비면 `heading`
        #     (표지 제목 = "모의고사 01회 — …")으로 폴백해서 회차를 되살린다.
        return "문제 편을 시작합니다."
    if meta["kind"] == "problem":
        # 발문만 읽는다. 보기는 화면에 있고, 읽으면 편이 두 배로 길어진다.
        return re.sub(r"\s+", " ", str(block.get("question") or "")).strip()
    # 해설 — 낭독문이 따로 있다(`explanation_speech`).
    return re.sub(r"\s+", " ",
                  str(block.get("explanation_speech")
                      or block.get("explanation") or "")).strip()


def build_script(bundle: str, lesson: Dict[str, Any],
                 metas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """씬 목록. `metas` 는 `render.build_pages()` 가 낸 것과 **같은 순서**여야 한다."""
    by_no = {int(b["number"]): b for b in lesson["blocks"]
             if b.get("kind") == "problem" and b.get("number")}
    scenes: List[Dict[str, Any]] = []
    si = 0

    def add(kind: str, *, capture: bool, heading: str, narration: str = "",
            seconds: Optional[float] = None, number: Optional[int] = None) -> None:
        nonlocal si
        sc: Dict[str, Any] = {
            "scene": si, "kind": kind, "capture": capture, "heading": heading,
            "narration": narration, "narration_text": narration,
        }
        if number is not None:
            sc["number"] = number
        if kind == "countdown":
            sc["countdown_seconds"] = int(seconds or COUNTDOWN_SECONDS)
        elif kind == "gap":
            sc["gap_seconds"] = float(seconds or GAP_SECONDS)
        elif seconds:
            # 낭독이 없는 이어지는 장 — 화면에 남는 시간을 직접 준다.
            sc["hold_seconds"] = float(seconds)
        scenes.append(sc)
        si += 1

    prev_no: Optional[int] = None
    for meta in metas:
        no = meta.get("number")
        blk = by_no.get(int(no)) if no else None
        # ★ 문항이 바뀌는 자리에 countdown·gap 을 끼운다. 앞 문항의 해설이 끝난 뒤다.
        if meta["kind"] == "problem" and meta["page"] == 1:
            if prev_no is not None:
                add("gap", capture=False, heading="", seconds=GAP_SECONDS)
            prev_no = no
        nar = _narration(meta, blk, lesson)
        if meta["kind"] == "cover":
            add("cover", capture=True, heading=lesson.get("title") or "",
                narration=nar)
        elif meta["kind"] == "problem":
            head = f"{no}번 문제" + (f" ({meta['page']}/{meta['pages']})"
                                   if meta["pages"] > 1 else "")
            add("problem", capture=True, heading=head, narration=nar,
                seconds=(None if meta["page"] == 1 else CONT_SECONDS), number=no)
            if meta["page"] == meta["pages"]:
                # ★ `number` 를 반드시 같이 넘긴다. chodangi 의 make_bundle_video 는
                #   `last_problem_img.get(r["number"])` 로 **그 문항의 마지막 문제 장**을
                #   찾아 그 위에 5→1 배지를 얹는다(deck_capture.countdown_frames).
                #   number 가 없으면 조회가 None 이 되어 `solid_frame()` — 즉 **백지에
                #   숫자만** 뜬다. 실측으로 그렇게 나왔다(2026-08-12).
                add("countdown", capture=False, heading="생각할 시간",
                    seconds=COUNTDOWN_SECONDS, number=no)
        else:
            mark = blk.get("answer") if blk else ""
            head = (f"{no}번 · 정답 {mark}"
                    + (f" ({meta['page']}/{meta['pages']})"
                       if meta["pages"] > 1 else ""))
            add("answer", capture=True, heading=head, narration=nar,
                seconds=(None if meta["page"] == 1 else CONT_SECONDS), number=no)

    return {
        "version": "1.0", "kind": "series",
        "round": lesson.get("round") or "",
        "subject": lesson.get("subject") or "",
        "theme": lesson.get("theme") or "teal",
        "voice": lesson.get("voice") or "F2",
        "speed": lesson.get("speed") or 1.05,
        "scenes": scenes,
    }


def bake_one(bundle: str) -> Dict[str, Any]:
    """번들 하나를 굽는다. 1:1 이 안 맞으면 **쓰지 않고** 예외를 낸다."""
    lesson = build_lesson(bundle)
    assets_dir = os.path.join(BOOK_DIR, "02", "assets")
    pages = render.build_pages(lesson, asset_dir="assets",
                              inline_dir=assets_dir)
    htmls = [h for h, _m in pages]
    metas = [m for _h, m in pages]

    deck = render.render_deck(lesson, tokens_css=theme.tokens_css(),
                              asset_dir="assets", inline_dir=assets_dir)
    n_slide = len(re.findall(r'class="[^"]*\bslide\b[^"]*"', deck))
    script = build_script(bundle, lesson, metas)
    n_cap = sum(1 for s in script["scenes"] if s["capture"])

    # ★ 하드 게이트. 어긋난 것을 쓰면 렌더가 72편 다 실패한다.
    if n_slide != n_cap or n_slide != len(htmls):
        raise ValueError(
            f"{bundle}: 1:1 이 깨졌습니다 — deck 슬라이드 {n_slide} · "
            f"캡처 씬 {n_cap} · 페이지 {len(htmls)}")

    lp = paths.bundle_lesson(bundle)
    dp = paths.bundle_deck(bundle)
    sp = paths.bundle_script(bundle)
    atomic_write_json(lp, lesson, indent=2, trailing_newline=True)
    atomic_write_text(dp, paths.to_disk(dp, deck))
    atomic_write_json(sp, script, indent=2, trailing_newline=True)

    from collections import Counter
    kinds = Counter(s["kind"] for s in script["scenes"])
    return {
        "bundle": bundle, "ok": True,
        "slides": n_slide, "scenes": len(script["scenes"]),
        "capture": n_cap, "kinds": dict(kinds),
        "written": [paths.rel(lp), paths.rel(dp), paths.rel(sp)],
    }
