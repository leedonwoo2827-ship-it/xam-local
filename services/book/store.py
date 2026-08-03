"""문항 읽기 · 5파일 저장 트랜잭션.

★ 저장할 때 정확히 이 다섯 곳을 쓴다 (계획 §5):
    1  _rounds/mNN.json                        집필 원천
    2  02/mNN-KK.md                            메타 + 검수상태
    3  02/assets/{name}.svg                    인라인 SVG → 파일
    4  02/_index.json · difficulty_stats.json  재계산
    5  05/<bundle>/source/lesson_<bundle>.json ★ 본문이 실제로 웹에 가는 경로

  04/lesson_mNN.json 과 05/*/source/deck.html 은 쓰지 않는다. deck 과 렌더된 mp4 는
  낡았다고 표시만 한다 — 다시 만드는 건 도구 #2/#3 의 일이다.

BOOK 은 외부에서 다시 동기화될 수 있는 트리다. 그래서 회차 락만으로는 부족하고
세 파일의 복합 etag 를 저장 시점에 다시 대조한다(불일치 → 409).
"""
from __future__ import annotations

import json
import os

from core.atomic_io import atomic_write_text, backup_sibling
from services.book import derive, index as bindex, lesson, md, paths, rounds


class ConflictError(Exception):
    """화면을 연 뒤 디스크가 바뀌었다 → HTTP 409."""


class LockedError(Exception):
    """파일이 잠겨 있다(편집기에서 열어 둔 경우) → HTTP 423."""


class DriftError(Exception):
    """_rounds 와 02/05 산물이 어긋나 있다 → 사람이 어느 쪽을 살릴지 골라야 한다."""


# ── etag ────────────────────────────────────────────────────────────────────
def etag_for(question_id: str) -> str:
    """_rounds · 02 md · 05 lesson 세 파일의 복합 etag."""
    p = paths.parse_qid(question_id)
    if not p:
        raise ValueError(f"문항 id 형식이 잘못됐습니다: {question_id!r}")
    round_no, qno = p
    return "|".join([
        paths.etag(paths.rounds_json(paths.round_code(round_no))),
        paths.etag(paths.q_md(question_id)),
        paths.etag(paths.bundle_lesson(paths.bundle_of(round_no, qno))),
    ])


# ── 읽기 ────────────────────────────────────────────────────────────────────
def read(question_id: str) -> dict:
    """에디터가 쓰는 문항 레코드 전문."""
    p = paths.parse_qid(question_id)
    if not p:
        raise ValueError(f"문항 id 형식이 잘못됐습니다: {question_id!r}")
    round_no, qno = p
    rc = paths.round_code(round_no)

    doc = rounds.load(rc)
    meta = rounds.meta_of(doc)
    q = rounds.question_of(doc, qno)
    if q is None:
        raise KeyError(f"_rounds/{rc}.json 에 {qno}번 문항이 없습니다.")

    md_path = paths.q_md(question_id)
    flags = md.flags_for(q, md_path)
    bundle = paths.bundle_of(round_no, qno)

    warnings: list[dict] = []
    sp = derive.check_speech(q)
    if sp:
        warnings.append(sp)

    # 드리프트 — 조용히 한쪽이 이기게 하지 않는다.
    if os.path.isfile(md_path):
        with open(md_path, encoding="utf-8", newline="") as f:
            # 개행은 비교 대상이 아니다 — paths.to_disk() 로 맞춘 뒤 내용만 본다.
            if f.read() != paths.to_disk(md_path, md.render(q, meta, md.read_flags(md_path))):
                warnings.append({
                    "code": "md_drift", "level": "warn",
                    "text": ("02/*.md 가 _rounds 로 재생성한 결과와 다릅니다. "
                             "누군가 md 를 직접 고쳤을 수 있습니다. 저장하면 "
                             "_rounds 기준으로 덮어씁니다."),
                })
    ldiff = lesson.question_to_block_diff(bundle, q)
    if ldiff:
        keys = [k for k in ldiff if k != "error"]
        warnings.append({
            "code": "lesson_drift", "level": "warn",
            "text": (ldiff.get("error") or
                     f"05 lesson 블록이 _rounds 와 다릅니다: {', '.join(keys)}. "
                     "저장하면 _rounds 기준으로 덮어씁니다."),
            "fields": keys,
        })

    assets = []
    for a in q.get("assets") or []:
        name = (a.get("name") if isinstance(a, dict) else str(a)) or ""
        name = name[:-4] if name.endswith(".svg") else name
        assets.append({
            "name": name,
            "svg": a.get("svg") if isinstance(a, dict) else None,
            "url": paths.book_url(paths.q_svg(name)),
            "on_disk": os.path.isfile(paths.q_svg(name)),
        })

    return {
        "id": question_id,
        "round_code": rc,
        "round": round_no,
        "round_label": meta.get("round_label", ""),
        "question_no": qno,
        "bundle": bundle,
        "bundle_range": paths.bundle_range(bundle),

        "subject": q.get("subject", ""),
        "subject_no": q.get("subject_no", 0),
        "difficulty": q.get("difficulty", ""),
        "tags": list(q.get("tags") or []),
        "derived_from": q.get("derived_from", ""),
        "question": q.get("question", ""),
        "choices": list(q.get("choices") or []),
        "answer_index": q.get("answer_index"),
        "explanation": q.get("explanation", ""),
        "explanation_speech": q.get("explanation_speech", ""),
        "assets": assets,
        # 해설 본문에 인라인된 그림 — 에디터가 미리보기를 띄울 대상
        "inline_figures": derive.inline_figure_names(q.get("explanation", "")),

        "derived": {
            "answer": derive.answer_glyph(q["answer_index"]) if isinstance(q.get("answer_index"), int) else "",
            "has_figure": derive.has_figure(q),
            "has_sql": bool(flags.get("has_sql", False)),
            "has_table": bool(flags.get("has_table", False)),
            "n_choices": derive.n_choices(q),
            "flags_source": flags.get("source", "estimated"),
        },
        "md_flags": {
            "authored_by": flags.get("authored_by", "claude"),
            "verified": bool(flags.get("verified", True)),
            "reviewed": bool(flags.get("reviewed", False)),
            "needs_review": bool(flags.get("needs_review", True)),
        },
        "paths": {
            "rounds": paths.rel(paths.rounds_json(rc)),
            "md": paths.rel(md_path),
            "lesson": paths.rel(paths.bundle_lesson(bundle)),
            "source_md": paths.rel(paths.source_md(q.get("derived_from") or "")),
        },
        "etag": etag_for(question_id),
        "warnings": warnings,
    }


def read_source(question_id: str) -> dict:
    """기출 원문(01/xx.md) — 에디터 우측 드로어의 대조용."""
    rec = read(question_id)
    src = rec.get("derived_from") or ""
    path = paths.source_md(src)
    if not src or not os.path.isfile(path):
        return {"id": src, "exists": False, "md": ""}
    with open(path, encoding="utf-8", newline="") as f:
        return {"id": src, "exists": True, "md": f.read(), "path": paths.rel(path)}


# ── 저장 ────────────────────────────────────────────────────────────────────
_EDITABLE = ("question", "choices", "answer_index", "explanation",
             "explanation_speech", "difficulty", "subject", "subject_no", "tags")


def save(question_id: str, values: dict, flags: dict | None = None,
         etag: str | None = None, *, auto_fix_speech: bool = True) -> dict:
    """5파일 트랜잭션. 내용이 실제로 바뀐 파일만 쓴다."""
    p = paths.parse_qid(question_id)
    if not p:
        raise ValueError(f"문항 id 형식이 잘못됐습니다: {question_id!r}")
    round_no, qno = p
    rc = paths.round_code(round_no)
    bundle = paths.bundle_of(round_no, qno)
    md_path = paths.q_md(question_id)

    with rounds.lock_for(rc):
        # 락을 잡은 뒤 **처음** 하는 일이 etag 대조다. 그 전에 읽으면 의미가 없다.
        if etag is not None and etag != etag_for(question_id):
            raise ConflictError(
                "이 문항이 화면을 연 뒤에 바뀌었습니다(다른 창에서 수정했거나 "
                "BOOK 이 다시 동기화됨). 새로고침해 최신 내용을 확인한 뒤 다시 "
                "수정해 주세요."
            )

        doc = rounds.load(rc)
        meta = rounds.meta_of(doc)
        i = rounds.question_index(doc, qno)
        if i < 0:
            raise KeyError(f"_rounds/{rc}.json 에 {qno}번 문항이 없습니다.")

        before = doc["questions"][i]
        q = dict(before)
        for k in _EDITABLE:
            if k in values:
                q[k] = values[k]
        if "choices" in values:
            q["choices"] = [str(c) for c in values["choices"]]
        if "answer_index" in values:
            q["answer_index"] = int(values["answer_index"])
        if "subject_no" in values:
            q["subject_no"] = int(values["subject_no"])
        if "tags" in values:
            q["tags"] = [str(t).strip() for t in (values["tags"] or []) if str(t).strip()]

        errs = derive.validate_question(q)
        if errs:
            raise ValueError(" / ".join(errs))

        notes: list[dict] = []

        # 정답을 옮겼는데 낭독문 접두어가 그대로면 영상이 틀린 번호를 읽는다.
        speech_edited = "explanation_speech" in values and \
            (values.get("explanation_speech") or "") != (before.get("explanation_speech") or "")
        if auto_fix_speech and not speech_edited and \
                int(before.get("answer_index", -1)) != int(q["answer_index"]):
            fixed = derive.rewrite_speech_prefix(q.get("explanation_speech") or "",
                                                 q["answer_index"])
            if fixed != (q.get("explanation_speech") or ""):
                q["explanation_speech"] = fixed
                notes.append({
                    "code": "speech_rewritten", "level": "info",
                    "text": (f"정답이 바뀌어 낭독문 접두어를 "
                             f"'정답은 {derive.KOR_NUM[q['answer_index']]} 번입니다.' 로 "
                             "고쳤습니다. 본문은 그대로입니다 — 내용도 정답에 맞는지 "
                             "확인하세요."),
                })
                speech_edited = True
        sp = derive.check_speech(q)
        if sp:
            notes.append(sp)

        written: list[str] = []
        try:
            # 1) _rounds
            if q != before:
                doc = dict(doc)
                qs = list(doc["questions"])
                qs[i] = q
                doc["questions"] = qs
                rounds.save(rc, doc)
                written.append(paths.rel(paths.rounds_json(rc)))

            # 2) 02/*.md — 보존 플래그를 합친다
            cur_flags = md.flags_for(before, md_path)
            if flags:
                for k in ("reviewed", "needs_review", "verified", "has_sql", "has_table"):
                    if k in flags:
                        cur_flags[k] = bool(flags[k])
            text = md.render(q, meta, cur_flags)
            if _write_if_changed(md_path, text):
                written.append(paths.rel(md_path))

            # 3) 02/assets/*.svg
            for a in q.get("assets") or []:
                if not isinstance(a, dict) or not a.get("svg"):
                    continue
                name = a["name"][:-4] if a["name"].endswith(".svg") else a["name"]
                if _write_if_changed(paths.q_svg(name), a["svg"]):
                    written.append(paths.rel(paths.q_svg(name)))

            # 4) 05 lesson — ★ 본문이 웹에 가는 경로
            lpath = paths.bundle_lesson(bundle)
            if os.path.isfile(lpath):
                ldoc = lesson.load(bundle)
                # ★ 이번에 값이 실제로 달라진 필드만 넘긴다. 전부 재생성하면 도구 #2 가
                #   넣어 둔 손질(그림 줄 제거·강조 표기)을 그 번들에서 잃는다.
                changed_fields = {k for k in lesson.FIELD_TO_KEYS
                                  if q.get(k) != before.get(k)}
                # 낭독문을 이번에 건드렸으면 lesson 도 새 값으로. 아니면 디스크 손질 보존.
                ldoc = lesson.render(ldoc, q, keep_speech=not speech_edited,
                                     fields=changed_fields)
                if lesson.save(bundle, ldoc):
                    written.append(paths.rel(lpath))
            else:
                notes.append({
                    "code": "lesson_missing", "level": "error",
                    "text": (f"05 lesson 파일이 없습니다: {paths.rel(lpath)}. "
                             "이 문항의 본문 수정은 웹에 반영되지 않습니다."),
                })

            # 5) 색인 · 통계
            res = bindex.write()
            for name, ch in res["changed"].items():
                if ch:
                    written.append(f"02/{name}")
        except PermissionError as e:
            raise LockedError(
                f"파일을 저장하지 못했습니다: {e.filename or ''}. "
                "해당 파일을 편집기나 탐색기 미리보기로 열어 두었다면 닫고 다시 시도하세요."
            ) from e

    # 하위 산물이 낡았다는 신호 — 도구 #2/#3 로 돌아갈 시점을 알린다.
    stale = _stale_downstream(bundle, written)

    return {
        "ok": True,
        "id": question_id,
        "written": written,
        "etag": etag_for(question_id),
        "notes": notes,
        "stale": stale,
        "record": read(question_id),
    }


def set_review(question_id: str, reviewed: bool, etag: str | None = None) -> dict:
    """검수 플래그만 뒤집는 핫패스 — 내용은 건드리지 않는다.

    02/*.md 의 front matter 와 02/_index.json 만 바뀐다. _rounds 와 05 lesson 은
    검수 상태를 들고 있지 않으므로 그대로다.
    """
    return save(
        question_id, values={}, etag=etag,
        flags={"reviewed": bool(reviewed), "needs_review": not bool(reviewed)},
    )


def _write_if_changed(path: str, text: str) -> bool:
    """개행을 그 파일의 규약으로 맞춘 뒤, 내용이 실제로 바뀐 경우에만 쓴다.

    ★ 맞추기 전에 비교하면 CRLF 파일이 매번 '바뀐 것' 으로 보여서 240개가
      첫 저장에서 전부 다시 쓰인다. paths.to_disk() 가 검증과 같은 함수다.
    """
    text = paths.to_disk(path, text)
    if os.path.isfile(path):
        with open(path, encoding="utf-8", newline="") as f:
            if f.read() == text:
                return False
    backup_sibling(path)
    atomic_write_text(path, text)
    return True


def _stale_downstream(bundle: str, written: list[str]) -> dict:
    """본문이 바뀌었으면 deck 과 mp4 가 낡는다.

    deck.html 은 도구 #2(스킬)가, mp4 는 도구 #3 이 만든다. 우리는 쓰지 않고
    '다시 만들어야 한다' 는 사실만 정확히 알린다.
    """
    lesson_rel = paths.rel(paths.bundle_lesson(bundle))
    if lesson_rel not in written:
        return {"bundle": bundle, "deck": False, "video": False}

    lmtime = paths.mtime(paths.bundle_lesson(bundle))
    deck = paths.bundle_deck(bundle)
    mp4 = paths.bundle_mp4(bundle)
    return {
        "bundle": bundle,
        "deck": paths.mtime(deck) < lmtime,
        "video": paths.mtime(mp4) < lmtime,
        "deck_path": paths.rel(deck),
        "video_path": paths.rel(mp4),
        "text": ("본문이 바뀌었습니다 — 이 번들의 deck.html 을 도구 #2 로 다시 만들고, "
                 "영상을 도구 #3 으로 다시 렌더해야 합니다. "
                 "문항 데이터만 웹에 넘기려면 지금 발행해도 됩니다."),
    }
