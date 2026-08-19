"""01/ 기출 OCR 문항 — 읽기 · 확정 · 바이트 충실 쓰기.

이건 도구 #1(exam-ocr-tool)의 산물이다. 그 툴의 `qmodel.write_question` 이 찍는
포맷을 그대로 재현해야 한다. **02/ 와 포맷이 다르다:**

  · 개행이 **CRLF** 다 (02/ 는 LF 전용)
  · front matter 19키 — `source_pdf`·`source_pages`·`has_latex`·`ocr_by` 가 더 있고
    `tags`·`derived_from`·`authored_by` 는 없다
  · `source_pages` 는 **블록 목록** (02/ 의 tags 는 인라인 flow)
  · 섹션이 `## 문제` → `## 지문`(선택) → `## 보기` → `## 해설`
    ★ `## 지문` 은 02/ 에 없는 섹션이다. 표·SQL·그림이 여기 들어간다.

원 툴은 PyYAML 로 `safe_dump(allow_unicode=True, sort_keys=False)` 를 쓴다. 우리도
같은 방식으로 찍어야 바이트가 맞는다(손으로 조립하면 들여쓰기가 어긋난다).
"""
from __future__ import annotations

import os
import re

import yaml

from core.atomic_io import backup_sibling
from core.constants import ANSWER_GLYPHS
from services.book import paths

# 도구 #1 의 FRONTMATTER_ORDER 와 같아야 한다.
FM_ORDER = (
    "id", "round", "round_label", "subject", "subject_no", "question_no",
    "answer", "answer_index", "difficulty", "source_pdf", "source_pages",
    "has_figure", "has_sql", "has_table", "has_latex", "ocr_by",
    "verified", "reviewed", "needs_review",
)

SEC_Q = "## 문제"
SEC_J = "## 지문"
SEC_C = "## 보기"
SEC_E = "## 해설"

# ★ 개행을 상수로 두지 않는다. `01/` 이 늘 CRLF 라고 본 것이 틀렸다 —
#   빅분기 폴더는 CRLF 인데 SQLD 폴더는 LF 다(`finalize.py` 가 `paths.to_disk()` 로
#   파일의 규약을 따라 썼기 때문이다). 상수로 박아 두니 SQLD 에서 337개가 전부
#   첫 줄에서 어긋나 「바이트 충실도 0/337」 로 저장이 통째로 막혔다(2026-08-19).
#   렌더러는 **LF 로만** 조립하고, 개행은 `paths.to_disk()` 한 곳만 지난다.
_ID_RE = re.compile(r"^(\d{2})-(\d{2})$")


def qid(round_no: int, question_no: int) -> str:
    return f"{int(round_no):02d}-{int(question_no):02d}"


def parse_qid(v: str) -> tuple[int, int] | None:
    m = _ID_RE.match((v or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def md_path(question_id: str) -> str:
    return os.path.join(paths.book_dir(), "01", f"{question_id}.md")


def _read(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    # newline="" — CRLF 를 그대로 읽는다. 변환되면 왕복 검증이 무의미해진다.
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


# ── 파서 ────────────────────────────────────────────────────────────────────
def _join_choice(buf: list, bare: bool) -> str:
    """보기 한 개의 줄들 → 본문. 앞뒤 빈 줄만 떼고 **안쪽은 건드리지 않는다.**"""
    out = list(buf)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)



def parse(text: str) -> dict:
    """01/*.md → {fm, question, jimun, choices, explanation}"""
    if not text.startswith("---"):
        raise ValueError("front matter 로 시작하지 않습니다.")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("front matter 를 닫는 --- 가 없습니다.")
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].replace("\r\n", "\n")

    def sec(name: str, nexts: tuple[str, ...]) -> str:
        i = body.find(name)
        if i < 0:
            return ""
        start = i + len(name)
        end = len(body)
        for n in nexts:
            j = body.find(n, start)
            if 0 <= j < end:
                end = j
        return body[start:end].strip()

    question = sec(SEC_Q, (SEC_J, SEC_C, SEC_E))
    jimun = sec(SEC_J, (SEC_C, SEC_E))
    raw_ch = sec(SEC_C, (SEC_E,))
    explanation = sec(SEC_E, ())

    # ★ 보기를 **글자 그대로** 뜬다. 다듬지 않는다.
    #
    #   전에는 줄마다 `strip()` 하고 이어 붙였다. 그래서 SQL 블록 보기의 들여쓰기가
    #   사라지고(`  from (` → `from (`), 「글리프 + 여러 줄」 인 보기가 블록형으로
    #   바뀌어 왕복 검증이 깨졌다(실측 SQLD 01-31·01-32). 01/ 은 파이프라인의
    #   시작점이라 여기서 한 글자만 달라도 뒤 단계가 전부 그 값을 쓴다.
    #
    #   보기마다 **어느 꼴이었는지**(`① 본문` 인가 `①` 뒤 빈 줄 + 블록인가)를 함께
    #   남긴다. 렌더러가 추측하면 같은 실수를 반복한다.
    choices: list[str] = []
    blocks: list[bool] = []
    _cur: list[str] | None = None
    _bare = False
    for raw in raw_ch.split("\n"):
        _t = raw.strip()
        if _t[:1] in ANSWER_GLYPHS and _t[:1]:
            if _cur is not None:
                choices.append(_join_choice(_cur, _bare))
                blocks.append(_bare)
            _rest = _t[1:]
            _bare = not _rest.strip()
            _cur = [] if _bare else [_rest.lstrip()]
        elif _cur is not None:
            _cur.append(raw)          # ★ 원문 그대로 — 들여쓰기가 내용이다
        elif _t:
            _cur, _bare = [raw], False
    if _cur is not None:
        choices.append(_join_choice(_cur, _bare))
        blocks.append(_bare)

    # ★ 보기 사이 간격을 **파일에서 읽는다.** 추측하지 않는다.
    #
    #   전에는 「지문이 있으면 빈 줄」 로 갈랐다. 빅분기 80문항에서 우연히 맞았을 뿐이고
    #   (지문이 있는 01-17 만 빈 줄이었다), SQLD 337개 중 57개가 그 규칙과 어긋나
    #   왕복 검증이 0/337 로 떨어졌다. 실제 기준은 `finalize.py` 의 **자산 유무** 인데
    #   파일만 보고는 자산이 있었는지 알 수 없다 — 그래서 **결과를 보존한다.**
    #   내용은 원천이고 형식은 파일에서 온다. 그것이 바이트 충실도의 원칙이다.
    _gl = "".join(ANSWER_GLYPHS)
    _blank = bool(re.search(r"\n[ \t]*\n[ \t]*[" + re.escape(_gl) + r"]", "\n" + raw_ch))
    return {"fm": fm, "question": question, "jimun": jimun,
            "choices": choices, "explanation": explanation,
            "choice_sep": "\n\n" if _blank else "\n",
            "choice_blocks": blocks,
            # ★ 본문 끝의 빈 줄까지 보존한다. 확정(`finalize`)이 빈 토큰을 펼치면
            #   꼬리에 빈 줄이 남는다 — 실측 8문항이 그렇다. 여기서 다듬으면
            #   그 8개가 왕복 검증에서 떨어지고 저장이 통째로 막힌다.
            "body_tail": body[len(body.rstrip()):] or "\n"}


# ── 렌더러 ──────────────────────────────────────────────────────────────────
def render(fm: dict, question: str, jimun: str, choices: list[str],
           explanation: str, choice_sep: str = "",
           choice_blocks: list | None = None, body_tail: str = "") -> str:
    """도구 #1 의 write_question 과 같은 바이트를 낸다."""
    ordered = {k: fm[k] for k in FM_ORDER if k in fm}
    front = yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False).strip()

    parts = [SEC_Q + "\n" + (question or "").strip()]
    if (jimun or "").strip():
        parts.append(SEC_J + "\n" + jimun.strip())

    # ★ **기록된 꼴**을 그대로 쓴다(`parse` 의 `choice_blocks`). 추측은 되돌림용이다.
    #   추측식(`\n` 이 있으면 블록)은 「글리프 + 여러 줄」 보기를 블록으로 바꿔 버렸다.
    out_lines = []
    for i, c in enumerate(choices or []):
        ex = (c or "").rstrip()
        mark = ANSWER_GLYPHS[i] if i < len(ANSWER_GLYPHS) else f"{i + 1}."
        if choice_blocks is not None and i < len(choice_blocks):
            blocky = bool(choice_blocks[i])
        else:
            _s = ex.lstrip()
            blocky = ("\n" in ex or _s[:2] in ("**", "| ", "``", "![")
                      or _s.startswith("|"))
        out_lines.append(f"{mark}\n\n{ex}" if blocky else f"{mark} {ex}")
    # ★ 보기 줄 사이 간격이 문항에 따라 다르다. 도구 #1 의 _body() 가 두 경로로
    #   갈리기 때문이다 — 자산(지문)이 있으면 _body_tokens 로 가서 "\n\n".join,
    #   없으면 legacy 경로로 "\n".join 이다.
    #   실측: 80문항 중 지문이 있는 01-17 만 "\n\n" 이고 나머지 79개는 "\n".
    # ★ 파일에서 읽은 간격을 그대로 쓴다. 없을 때(새 파일)만 추정한다.
    sep = choice_sep or ("\n\n" if (jimun or "").strip() else "\n")
    parts.append(SEC_C + "\n" + sep.join(out_lines))

    if (explanation or "").strip():
        parts.append(SEC_E + "\n" + explanation.strip())

    # ★ **LF 로 낸다.** 디스크 개행은 `paths.to_disk(path, text)` 가 파일마다 정한다.
    return (f"---\n{front}\n---\n\n" + "\n\n".join(parts)
            + (body_tail or "\n"))


def render_from_file(question_id: str, *, overrides: dict | None = None) -> str:
    """디스크의 md 를 파싱해서 그대로 다시 찍는다(왕복 검증용)."""
    text = _read(md_path(question_id))
    if text is None:
        raise FileNotFoundError(md_path(question_id))
    d = parse(text)
    fm = dict(d["fm"])
    if overrides:
        fm.update(overrides)
    text = render(fm, d["question"], d["jimun"], d["choices"], d["explanation"],
                  d.get("choice_sep") or "", d.get("choice_blocks"),
                  d.get("body_tail") or "")
    # ★ 왕복 검증은 **디스크에 들어갈 모양**과 비교해야 한다. 렌더러 출력(LF)을
    #   그대로 비교하면 CRLF 로 저장된 책이 전부 불일치로 뜬다.
    return paths.to_disk(md_path(question_id), text)


# ── 목록 · 읽기 ─────────────────────────────────────────────────────────────
def _preview(text: str, n: int = 110) -> str:
    t = " ".join((text or "").split())
    return t[:n] + ("…" if len(t) > n else "")


def list_items(*, unconfirmed: bool = False, q: str = "") -> dict:
    """01/ 문항 목록. 위 판(OCR 본문)이 이걸 쓴다."""
    d = os.path.join(paths.book_dir(), "01")
    if not os.path.isdir(d):
        return {"exists": False, "count": 0, "confirmed": 0, "items": [],
                "error": f"01/ 폴더가 없습니다: {d}"}

    names = sorted(f for f in os.listdir(d)
                   if f.endswith(".md") and not f.startswith("_"))
    items, confirmed = [], 0
    for name in names:
        qid_ = name[:-3]
        text = _read(os.path.join(d, name))
        if text is None:
            continue
        try:
            p = parse(text)
        except Exception as e:
            items.append({"id": qid_, "error": f"{type(e).__name__}: {e}",
                          "confirmed": False})
            continue
        fm = p["fm"]
        ok = bool(fm.get("verified")) and bool(fm.get("reviewed")) \
            and not bool(fm.get("needs_review"))
        if ok:
            confirmed += 1
        items.append({
            "id": qid_,
            "round": fm.get("round"),
            "round_label": fm.get("round_label", ""),
            "question_no": fm.get("question_no"),
            "subject": fm.get("subject", ""),
            "subject_no": fm.get("subject_no"),
            "answer": fm.get("answer", ""),
            "answer_index": fm.get("answer_index"),
            "difficulty": fm.get("difficulty"),
            "has_figure": bool(fm.get("has_figure")),
            "has_sql": bool(fm.get("has_sql")),
            "has_table": bool(fm.get("has_table")),
            "has_latex": bool(fm.get("has_latex")),
            "has_jimun": bool(p["jimun"].strip()),
            "n_choices": len(p["choices"]),
            "verified": bool(fm.get("verified")),
            "reviewed": bool(fm.get("reviewed")),
            "needs_review": bool(fm.get("needs_review")),
            "confirmed": ok,
            "ocr_by": fm.get("ocr_by", ""),
            "source_pdf": fm.get("source_pdf", ""),
            "source_pages": fm.get("source_pages") or [],
            # ★ OCR 본문 미리보기 — 위 판에 이 글이 뜬다
            "preview": _preview(p["question"]),
            "bytes": len(text.encode("utf-8")),
        })

    rows = items
    if unconfirmed:
        rows = [i for i in rows if not i.get("confirmed")]
    if q:
        needle = q.strip().lower()
        rows = [i for i in rows if needle in i["id"].lower()
                or needle in (i.get("subject") or "").lower()
                or needle in (i.get("preview") or "").lower()]

    pdfs = sorted({i.get("source_pdf") for i in items if i.get("source_pdf")})
    subjects = []
    for i in items:
        s = i.get("subject")
        if s and s not in subjects:
            subjects.append(s)
    return {
        "exists": True,
        "count": len(items),
        "filtered": len(rows),
        "confirmed": confirmed,
        "items": rows,
        "facets": {"pdfs": pdfs, "subjects": subjects,
                   "rounds": sorted({i.get("round") for i in items if i.get("round")})},
        "pdf_dir": os.path.join(paths.book_dir(), "00"),
    }


def read(question_id: str) -> dict:
    path = md_path(question_id)
    text = _read(path)
    if text is None:
        raise KeyError(f"{question_id} 를 찾을 수 없습니다: {paths.rel(path)}")
    p = parse(text)
    fm = p["fm"]
    return {
        "id": question_id,
        "fm": fm,
        "question": p["question"],
        "jimun": p["jimun"],
        "choices": p["choices"],
        "explanation": p["explanation"],
        # OCR 본문 전문 — 위 판에서 '원문 펴기' 로 보는 값
        "md": text,
        "path": paths.rel(path),
        "etag": paths.etag(path),
        "confirmed": (bool(fm.get("verified")) and bool(fm.get("reviewed"))
                      and not bool(fm.get("needs_review"))),
        "derived": {
            "answer": (ANSWER_GLYPHS[fm["answer_index"]]
                       if isinstance(fm.get("answer_index"), int)
                       and 0 <= fm["answer_index"] < len(ANSWER_GLYPHS) else ""),
            "n_choices": len(p["choices"]),
            "has_jimun": bool(p["jimun"].strip()),
        },
        "pdf": _pdf_info(fm),
    }


def _pdf_info(fm: dict) -> dict:
    """원문 PDF 대조용. 00/ 에 실제로 있는지 확인한다."""
    name = fm.get("source_pdf") or ""
    p = os.path.join(paths.book_dir(), "00", name) if name else ""
    return {
        "name": name,
        "exists": bool(name) and os.path.isfile(p),
        "url": paths.book_url(p) if name and os.path.isfile(p) else None,
        "pages": fm.get("source_pages") or [],
    }


# ── 쓰기 ────────────────────────────────────────────────────────────────────
class ConflictError(Exception):
    """화면을 연 뒤 디스크가 바뀌었다 → 409."""


class LockedError(Exception):
    """파일이 잠겨 있다 → 423."""


EDITABLE_FM = ("subject", "subject_no", "difficulty", "answer_index",
               "round_label", "has_latex")


def save(question_id: str, values: dict, *, flags: dict | None = None,
         etag: str | None = None) -> dict:
    """01/{qid}.md 를 다시 쓴다. 이 파일 하나만 건드린다.

    02/ 와 달리 하위 산물이 없다 — 01/ 은 파이프라인의 시작점이고 02/ 는 사람이
    다시 집필하는 단계다. 그래서 여기서 05/lesson 을 건드리지 않는다.
    """
    path = md_path(question_id)
    if etag is not None and etag != paths.etag(path):
        raise ConflictError(
            "이 문항이 화면을 연 뒤에 바뀌었습니다. 새로고침해 최신 내용을 확인한 뒤 "
            "다시 수정해 주세요.")

    cur = _read(path)
    if cur is None:
        raise KeyError(f"{question_id} 를 찾을 수 없습니다.")
    d = parse(cur)
    fm = dict(d["fm"])

    question = values.get("question", d["question"])
    jimun = values.get("jimun", d["jimun"])
    choices = values.get("choices", d["choices"])
    explanation = values.get("explanation", d["explanation"])

    for k in EDITABLE_FM:
        if k in values:
            fm[k] = values[k]
    if "answer_index" in values:
        ai = int(values["answer_index"])
        if not 0 <= ai < len(choices or []):
            raise ValueError(f"정답 번호가 범위를 벗어났습니다: {ai}")
        fm["answer_index"] = ai
        fm["answer"] = ANSWER_GLYPHS[ai]

    if flags:
        for k in ("verified", "reviewed", "needs_review"):
            if k in flags:
                fm[k] = bool(flags[k])

    errs = []
    if not (question or "").strip():
        errs.append("문제문이 비어 있습니다.")
    if len(choices or []) < 2:
        errs.append(f"보기가 {len(choices or [])}개입니다.")
    if not isinstance(fm.get("answer_index"), int):
        errs.append("정답 번호가 없습니다.")
    if errs:
        raise ValueError(" / ".join(errs))

    # ★ 저장도 **원래 간격을 지킨다.** 여기서 바꾸면 고친 문항 하나 때문에
    #   그 파일이 왕복 검증에서 떨어지고, 다음 저장이 통째로 막힌다.
    text = paths.to_disk(path, render(fm, question, jimun, choices, explanation,
                                      d.get("choice_sep") or "",
                                      d.get("choice_blocks"),
                                      d.get("body_tail") or ""))
    written = []
    if text != cur:
        try:
            backup_sibling(path)
            # newline="" — `to_disk()` 가 개행을 정했다. 여기서 또 변환하면 CRCRLF 가 된다.
            with open(path + f".tmp.{os.getpid()}", "w", encoding="utf-8", newline="") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(path + f".tmp.{os.getpid()}", path)
            written.append(paths.rel(path))
        except PermissionError as e:
            raise LockedError(
                f"파일을 저장하지 못했습니다: {paths.rel(path)}. "
                "편집기에서 열어 두었다면 닫고 다시 시도하세요.") from e

    return {"ok": True, "id": question_id, "written": written,
            "etag": paths.etag(path), "record": read(question_id)}


def confirm(question_id: str, confirmed: bool = True,
            etag: str | None = None) -> dict:
    """확정 — verified·reviewed true, needs_review false. 도구 #1 의 finalize 와 같다."""
    return save(question_id, {}, etag=etag, flags={
        "verified": bool(confirmed),
        "reviewed": bool(confirmed),
        "needs_review": not bool(confirmed),
    })


# ── 왕복 검증 ───────────────────────────────────────────────────────────────
def verify() -> dict:
    """01/*.md 를 파싱→재렌더해서 바이트가 같은지 본다. 저장 경로의 게이트다."""
    d = os.path.join(paths.book_dir(), "01")
    if not os.path.isdir(d):
        return {"ok": False, "error": f"01/ 폴더가 없습니다: {d}"}
    names = sorted(f for f in os.listdir(d)
                   if f.endswith(".md") and not f.startswith("_"))
    ok, fail = 0, []
    for name in names:
        qid_ = name[:-3]
        original = _read(os.path.join(d, name))
        try:
            rendered = render_from_file(qid_)
        except Exception as e:
            fail.append({"id": qid_, "error": f"{type(e).__name__}: {e}"})
            continue
        if rendered == original:
            ok += 1
        else:
            diff = None
            for i, (a, b) in enumerate(zip(original, rendered)):
                if a != b:
                    diff = {"at_char": i, "at_line": original[:i].count("\n") + 1,
                            "expected": repr(original[max(0, i - 20):i + 20]),
                            "got": repr(rendered[max(0, i - 20):i + 20])}
                    break
            fail.append({"id": qid_,
                         "bytes_expected": len(original.encode("utf-8")),
                         "bytes_rendered": len(rendered.encode("utf-8")),
                         **(diff or {"note": "길이가 다릅니다."})})
    return {"ok": not fail, "kind": "01/*.md", "total": len(names),
            "passed": ok, "fail": fail[:20], "fail_count": len(fail)}
