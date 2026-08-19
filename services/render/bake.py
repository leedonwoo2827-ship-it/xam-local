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
# ★ `BOOK_DIR` 을 **모듈 상수로 잡지 않는다.** 그것은 `.env` 의 첫 실행 기본값이고,
#   실제로 쓰는 폴더는 작업 폴더 화면에서 고른 것이다(`paths.book_dir()`).
#   상수로 잡아 두니 폴더를 SQLD 로 바꿔도 화면이 시작할 때의 빅분기를 계속 읽었다
#   — 집필 화면에 SQLD 시험정보와 빅분기 회차가 함께 뜬 원인이다(2026-08-19).
from core.speak import to_speech
from services.authoring.schema import subject_no_for, subjects
from services.book import lesson as lessonmod
from services.book import paths
from services.deck import render, theme
from services.render import speech

# 이어지는 장이 화면에 남는 시간(초). 낭독이 없는 장이므로 시간을 직접 준다.
CONT_SECONDS = 4
COUNTDOWN_SECONDS = 5
GAP_SECONDS = 1.5


def _round_doc(round_code: str) -> Dict[str, Any]:
    p = os.path.join(paths.book_dir(), "_rounds", f"{round_code}.json")
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

    # ★ 회차 문항수를 **시험정보에서** 읽는다. `80` 이 박혀 있어서 SQLD(50문항)의
    #   번들 수가 5가 아니라 8로 찍혔다 — 제목의 `(3/8)` 이 거짓이 된다.
    # ★ 굽기 전에 시험정보를 확인한다 — 없으면 번들 경계가 다른 품목 값으로 잡힌다.
    from services.authoring import parts as _P

    _P.require()
    total_parts = max(1, -(-_round_items() // _per_bundle()))
    subj_no = subject_no_for(lo)
    blocks: List[Dict[str, Any]] = [
        {"kind": "section", "title": f"{subj_no}과목 · {subjects().get(subj_no, '')}"}]
    prev = None
    for q in qs:
        blocks.append(lessonmod.block_from_rounds(q, prev))
        prev = q

    # ★ "자사" 를 쓰지 않는다(2026-08-12 지시).
    out = {
        "version": "1.0", "kind": "lesson",
        "chapter": round_no,
        "title": f"모의고사 {round_no:02d}회 — 문제 풀이 ({part}/{total_parts})",
        # ★ 품목명·테마도 시험정보에서. 상수면 SQLD 영상에 빅분기 이름이 박힌다.
        "subject": _exam_label(),
        "theme": doc.get("theme") or _exam_theme(),
        "scenes_per_problem": 2, "include_lecture": False,
        "countdown_seconds": COUNTDOWN_SECONDS, "gap_seconds": GAP_SECONDS,
        "round": f"모의고사 {round_no:02d}회",
        "voice": doc.get("voice") or "F2", "speed": doc.get("speed") or 1.05,
        "ai_reading": False, "part_index": part, "part_total": total_parts,
        "blocks": blocks,
    }
    return out


def _exam() -> Dict[str, Any]:
    try:
        from services.authoring import parts

        return parts.active() or {}
    except Exception:                                        # noqa: BLE001
        return {}


def _round_items() -> int:
    """회차 문항수 — 시험정보에서. 못 읽으면 폴백 상수."""
    try:
        from services.authoring import parts

        return int(parts.round_size(parts.active()))
    except Exception:                                        # noqa: BLE001
        return int(paths.FALLBACK_QUESTIONS_PER_ROUND)


def _per_bundle() -> int:
    """번들(영상 1편) 문항수 — 시험정보의 `video.problems_per_bundle`.

    ★ `pr_key` 규칙과 묶여 있어 함부로 바꿀 값이 아니지만, **품목이 정하는 값**이다.
      상수로 두면 문항수가 다른 시험에서 번들 경계가 어긋난다.
    """
    n = ((_exam().get("video") or {}).get("problems_per_bundle") or 0)
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    return n if n > 0 else int(paths.QUESTIONS_PER_BUNDLE)


def _exam_label() -> str:
    return str(_exam().get("label") or "").strip() or "자격시험"


def _exam_theme() -> str:
    return str(_exam().get("theme") or "").strip() or "teal"


def _speech_terms() -> Dict[str, str]:
    """이 품목의 약어 사전(`exams/<pd>.json` 의 `speech_dict`). 없으면 빈 dict.

    ★ 사람이 손으로 고친 발음(`05/<번들>/script/*_speech.json`)이 이보다 위다 —
      그쪽은 씬 단위 최종 결정이고, 이것은 자동 변환의 기본값이다.
    """
    try:
        from services.authoring import parts

        return {str(k): str(v) for k, v in
                ((parts.active() or {}).get("speech_dict") or {}).items()}
    except Exception:                                        # noqa: BLE001
        return {}


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
        # ★ 여기서 글자를 **빼지 않는다.** 이 함수의 값은 `narration`(자막)이 되고
        #   자막은 원문이어야 한다. 읽지 말 것을 덜어내는 일은 발음 쪽
        #   (`core.speak.to_speech`)이 한다 — 전에 괄호 제거를 여기 넣었더니
        #   자막에서도 `(Information)` 이 사라졌다(실측 91곳).
        return re.sub(r"\s+", " ", str(block.get("question") or "")).strip()
    # 해설 — 낭독문이 따로 있다(`explanation_speech`).
    return re.sub(r"\s+", " ",
                  str(block.get("explanation_speech")
                      or block.get("explanation") or "")).strip()


def build_script(bundle: str, lesson: Dict[str, Any],
                 metas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """씬 목록. `metas` 는 `render.build_pages()` 가 낸 것과 **같은 순서**여야 한다.

    ★ 씬마다 **두 트랙**을 쓴다. 엔진이 원래 그렇게 받는다
      (`voicewright.schemas.ScriptScene` 의 `narration_text` · `srt_text`).

        narration       자막 — 화면에 뜨는 원문. `2007년 3월`
        narration_text  발음 — TTS 가 읽는 글.  `이천칠 년 삼 월`

      발음은 자막에서 규칙으로 만들고(`core.speak.speak_numbers`), 그 위에
      **사람이 고친 것**을 얹는다(`services.render.speech` 의 덮어쓰기 파일).
      전에는 두 값을 같게 써서 TTS 가 `2007년` 을 글자대로 읽었다.
    """
    by_no = {int(b["number"]): b for b in lesson["blocks"]
             if b.get("kind") == "problem" and b.get("number")}
    scenes: List[Dict[str, Any]] = []
    si = 0
    # 사람이 고친 발음. 씬 번호로 붙는다 — 이 함수가 씬 번호를 매기므로 여기서 얹는다.
    hand = speech.overrides(bundle)
    used: List[int] = []
    drift: List[int] = []

    def add(kind: str, *, capture: bool, heading: str, narration: str = "",
            seconds: Optional[float] = None, number: Optional[int] = None) -> None:
        nonlocal si
        # ★ 품목별 약어 사전을 함께 넘긴다 — 공용 규칙(된소리·소숫점·연도) 위에
        #   덧붙는 층이다. `SQL`→에스큐엘 은 SQLD 의 것이고 빅분기 것과 다르다.
        say = to_speech(narration, _speech_terms())
        e = hand.get(si) or {}
        hand_text = (e.get("text") or "").strip()
        if hand_text:
            # ★ 고친 뒤에 발문이 바뀌었으면 **쓰지 않는다.** 낡은 발음을 조용히 읽는
            #   것이 가장 나쁘다 — 화면·리포트가 그 씬을 집어 준다.
            if (e.get("from") or "").strip() != narration.strip():
                drift.append(si)
            else:
                say = hand_text
                used.append(si)
        sc: Dict[str, Any] = {
            "scene": si, "kind": kind, "capture": capture, "heading": heading,
            "narration": narration, "narration_text": say,
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

    if drift:
        print(f"[warn] {bundle}: 씬 {drift} 의 발음 덮어쓰기를 쓰지 않았습니다 — "
              "고친 뒤에 발문이 바뀌었습니다(speech.json 의 from 이 지금 자막과 다름). "
              "영상 화면에서 그 씬을 다시 보고 저장하세요.")
    return {
        "version": "1.0", "kind": "series",
        "round": lesson.get("round") or "",
        "subject": lesson.get("subject") or "",
        "theme": lesson.get("theme") or "teal",
        "voice": lesson.get("voice") or "F2",
        "speed": lesson.get("speed") or 1.05,
        "scenes": scenes,
        # 리포트용 — 이 번들에서 사람 손이 실제로 쓰인 씬과, 어긋나 버려진 씬
        "_speech_used": used, "_speech_drifted": drift,
    }


def bake_one(bundle: str) -> Dict[str, Any]:
    """번들 하나를 굽는다. 1:1 이 안 맞으면 **쓰지 않고** 예외를 낸다."""
    lesson = build_lesson(bundle)
    assets_dir = os.path.join(paths.book_dir(), "02", "assets")
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
