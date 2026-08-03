"""초안 → `01/{RR}-{NN}.md` 확정 (바이트 충실) + 그림 크롭.

★ 이 파일은 도구 #1 의 `app/qmodel.py` 를 **이식**한 것이다. 재현이 아니다.
  업로드본의 `services/book/scan.py` 는 같은 형식을 추측해 근사했는데, 보기 줄
  간격을 '지문 유무' 로 갈랐다. 실제 기준은 **자산(assets) 유무** 다 —
  `qmodel._body()` 가 자산이 있으면 `_body_tokens`(선지 사이 빈 줄), 없으면
  레거시 경로(빈 줄 없음)로 갈린다. 실측 80문항에서는 둘이 우연히 일치했지만,
  자산은 있고 토큰을 선지·해설로 옮긴 문항이 생기면 어긋난다.

## 형식 (도구 #1 의 write_question 과 같은 바이트)

    ---
    <yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()>
    ---

    ## 문제
    …
    ## 지문        (자산 토큰이 펼쳐진 자리. 없으면 섹션 자체가 없다)
    ## 보기
    ① …
    ## 해설

front matter 19키 순서 고정. 개행은 **파일에서 감지**한다 — 원본 도구가
`path.write_text()` 로 썼기 때문에 Windows 에서는 CRLF 가 되고, 리눅스 세션이
만든 판은 LF 다. `paths.to_disk()` 가 그 판단을 한 곳에서 한다.
"""
from __future__ import annotations

import os
import re

import yaml

from core.atomic_io import atomic_write_text, backup_sibling
from services.book import paths
from services.ocr import project

# 도구 #1 의 FRONTMATTER_ORDER. 이 순서가 곧 파일 형식이다.
FM_ORDER = (
    "id", "round", "round_label", "subject", "subject_no", "question_no",
    "answer", "answer_index", "difficulty", "source_pdf", "source_pages",
    "has_figure", "has_sql", "has_table", "has_latex", "ocr_by",
    "verified", "reviewed", "needs_review",
)

CIRCLED = {"①": 0, "②": 1, "③": 2, "④": 3, "⑤": 4}
CIRCLED_INV = {0: "①", 1: "②", 2: "③", 3: "④", 4: "⑤"}

_TOKEN_RE = re.compile(r"\{\{([A-Za-z]+-\d+)\}\}")
_INLINE_MATH = re.compile(r"(?<!\\)\$[^$\n]+?(?<!\\)\$")


def answer_to_index(answer: str | None) -> int | None:
    if not answer:
        return None
    a = str(answer).strip()
    if a in CIRCLED:
        return CIRCLED[a]
    if a.isdigit() and 1 <= int(a) <= 5:
        return int(a) - 1
    return None


def index_to_circled(idx) -> str:
    return CIRCLED_INV.get(idx, "") if isinstance(idx, int) else ""


def qid(round_no: int, question_no: int) -> str:
    return f"{int(round_no):02d}-{int(question_no):02d}"


def md_path(round_no: int, question_no: int) -> str:
    return os.path.join(paths.book_dir(), "01",
                        f"{qid(round_no, question_no)}.md")


# ── 자산 → MD ───────────────────────────────────────────────────────────────
def _img(a: dict) -> str:
    src = a.get("path") or a.get("file") or ""
    note = a.get("note") or "figure"
    return f"![{note}]({src})" if src else ""


def asset_md(a: dict) -> str:
    """자산 하나 → MD 조각. qmodel._asset_md 와 같아야 한다."""
    t = a.get("type")
    if t == "table":
        title = (a.get("title") or "").strip()
        md = (a.get("md") or "").strip()
        return f"**{title}**\n\n{md}" if title else md
    if t in ("sql", "box"):
        return "```sql\n" + (a.get("text") or "").strip() + "\n```"
    if t == "figure":
        return _img(a)
    if t == "text":
        return "```text\n" + (a.get("text") or "").strip() + "\n```"
    if t == "latex":
        # 디스플레이 수식. 인라인 수식은 자산이 아니라 본문에 $…$ 로 직접 쓴다.
        return "$$\n" + (a.get("text") or "").strip() + "\n$$"
    return ""


def expand_tokens(text: str, assets: dict) -> str:
    if not text:
        return text or ""
    return _TOKEN_RE.sub(
        lambda m: asset_md(assets[m.group(1)]) if m.group(1) in assets else m.group(0),
        text)


def _has(q: dict, kind: str) -> bool:
    """has_table / has_sql / has_figure / has_latex 판정 (자산 우선, 없으면 레거시)."""
    assets = q.get("assets") or {}
    if kind == "latex":
        if any(a.get("type") == "latex" for a in assets.values()):
            return True
        fields = [q.get("stem") or "", q.get("jimun") or "", q.get("explanation") or ""]
        fields += [c or "" for c in (q.get("choices") or [])]
        fields += [a.get("md") or a.get("text") or "" for a in assets.values()]
        return any(_INLINE_MATH.search(t) for t in fields)
    if assets:
        types = [a.get("type") for a in assets.values()]
        return (("sql" in types or "box" in types) if kind == "sql" else kind in types)
    legacy = {"figure": "figures", "sql": "sql", "table": "tables"}[kind]
    return bool(q.get(legacy))


# ── 본문 ────────────────────────────────────────────────────────────────────
def is_block_choice(text: str) -> bool:
    """보기를 `①` 단독 줄 + 빈 줄 + 본문 으로 써야 하는가 (qmodel 과 같은 판정)."""
    ex = (text or "").lstrip()
    return bool(ex) and ("\n" in ex or ex[:2] in ("**", "| ", "``", "![")
                         or ex.startswith("|"))


def _body_tokens(q: dict, assets: dict) -> str:
    """자산이 있는 문항 — 토큰을 펼친다. **선지 사이가 빈 줄이다.**"""
    parts = ["## 문제\n" + expand_tokens((q.get("stem") or "").strip(), assets)]
    jm = expand_tokens((q.get("jimun") or "").strip(), assets)
    if jm.strip():
        parts.append("## 지문\n" + jm)
    lines = []
    for i, c in enumerate(q.get("choices") or []):
        ex = expand_tokens((c or "").strip(), assets)
        mark = CIRCLED_INV.get(i, f"{i + 1}.")
        lines.append(f"{mark}\n\n{ex}" if is_block_choice(ex) else f"{mark} {ex}")
    parts.append("## 보기\n" + "\n\n".join(lines))
    expl = expand_tokens((q.get("explanation") or "").strip(), assets)
    if expl.strip():
        parts.append("## 해설\n" + expl)
    return "\n\n".join(parts) + "\n"


def _is_explanation_fig(f: dict) -> bool:
    return (f.get("placement") or "지문") in ("해설", "explanation")


def _body_legacy(q: dict) -> str:
    """자산이 없는 문항 — 고정 슬롯(SQL → 표 → 그림). **선지 사이가 한 줄이다.**"""
    parts = ["## 문제\n" + (q.get("stem") or "").strip()]

    figs = q.get("figures") or []
    stem_figs = [f for f in figs if not _is_explanation_fig(f)]
    expl_figs = [f for f in figs if _is_explanation_fig(f)]
    tables_in_expl = (q.get("tables_placement") or "지문") in ("해설", "explanation")
    sql_in_expl = (q.get("sql_placement") or "지문") in ("해설", "explanation")

    jimun: list[str] = []
    if q.get("sql") and not sql_in_expl:
        jimun.append("```sql\n" + q["sql"].strip() + "\n```")
    if q.get("tables") and not tables_in_expl:
        jimun.append(q["tables"].strip())
    for f in stem_figs:
        img = _img(f)
        if img:
            jimun.append(img)
    if jimun:
        parts.append("## 지문\n" + "\n\n".join(jimun))

    lines = [f"{CIRCLED_INV.get(i, str(i + 1) + '.')} {(c or '').strip()}"
             for i, c in enumerate(q.get("choices") or [])]
    parts.append("## 보기\n" + "\n".join(lines))

    expl: list[str] = []
    if q.get("explanation"):
        expl.append(q["explanation"].strip())
    if q.get("sql") and sql_in_expl:
        expl.append("```sql\n" + q["sql"].strip() + "\n```")
    if q.get("tables") and tables_in_expl:
        expl.append(q["tables"].strip())
    for f in expl_figs:
        img = _img(f)
        if img:
            expl.append(img)
    if expl:
        parts.append("## 해설\n" + "\n\n".join(expl))
    return "\n\n".join(parts) + "\n"


def body(q: dict) -> str:
    """★ 두 경로로 갈린다 — 기준은 **자산 유무** (지문 유무가 아니다)."""
    assets = q.get("assets") or {}
    return _body_tokens(q, assets) if assets else _body_legacy(q)


# ── front matter · 전문 ─────────────────────────────────────────────────────
def front_matter(q: dict) -> dict:
    rn = int(q["round"])
    qn = int(q["question_no"])
    subject, subject_no = project.subject_for(qn, q.get("subject_no"))
    if q.get("subject"):
        subject = q["subject"]
    ans = q.get("answer") or index_to_circled(q.get("answer_index"))
    ans_idx = q.get("answer_index")
    if ans_idx is None:
        ans_idx = answer_to_index(ans)

    fm = {
        "id": qid(rn, qn),
        "round": rn,
        "round_label": q.get("round_label") or project.round_label(rn),
        "subject": subject,
        "subject_no": q.get("subject_no", subject_no),
        "question_no": qn,
        "answer": ans or "",
        "answer_index": ans_idx,
        "difficulty": q.get("difficulty"),
        "source_pdf": q.get("source_pdf", ""),
        "source_pages": q.get("source_pages", []),
        "has_figure": _has(q, "figure"),
        "has_sql": _has(q, "sql"),
        "has_table": _has(q, "table"),
        "has_latex": _has(q, "latex"),
        "ocr_by": q.get("ocr_by", "claude"),
        "verified": bool(q.get("verified", False)),
        "reviewed": bool(q.get("reviewed", False)),
        "needs_review": bool(q.get("needs_review", True)),
    }
    return {k: fm[k] for k in FM_ORDER if k in fm}


def render(q: dict) -> str:
    """문항 하나 → 01/*.md 전문 (LF 기준. 개행 변환은 paths.to_disk 가 한다).

    ★ PyYAML 로 덤프한다. 손으로 조립하면 들여쓰기와 인용부호가 어긋난다 —
      `source_pages` 는 블록 목록이고 `round_label` 은 무인용부호 한글 스칼라다.
    """
    front = yaml.safe_dump(front_matter(q), allow_unicode=True,
                           sort_keys=False).strip()
    return f"---\n{front}\n---\n\n{body(q)}"


# ── 그림 크롭 ───────────────────────────────────────────────────────────────
def crop_figure(src: str, page: int, bbox, dest: str) -> None:
    """페이지 PNG 의 bbox 를 잘라 dest 로 저장한다."""
    from PIL import Image
    img = Image.open(project.scan_png(src, page))
    x, y, w, h = [max(0, int(v)) for v in bbox]
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    img.crop((x, y, x + w, y + h)).save(dest)


# ── 확정 ────────────────────────────────────────────────────────────────────
class LockedError(Exception):
    """파일이 잠겨 있다(편집기에서 열어 둔 경우) → HTTP 423."""


def prepare(q: dict, src: str, page: int, *, crop: bool = True,
            stage: str | None = None) -> dict:
    """확정 직전 상태로 문항을 다듬는다 — 자산 그림 경로 · source_pdf · source_pages.

    crop=False 면 PNG 를 만들지 않고 `path` 만 채운다. 확정 게이트가 디스크를
    건드리지 않고 바이트만 비교할 때 쓴다(경로는 `images/{qid}_{aid}.png` 로
    결정론적이라 크롭 없이도 같은 MD 가 나온다).
    """
    rn, qn = int(q["round"]), int(q["question_no"])
    q = dict(q)
    stage = stage or os.path.join(paths.book_dir(), "01")

    assets = {k: dict(v) for k, v in (q.get("assets") or {}).items()}
    for aid, a in assets.items():
        if a.get("type") == "figure" and a.get("bbox"):
            rel = f"images/{qid(rn, qn)}_{aid}.png"
            if crop:
                crop_figure(src, page, a["bbox"], os.path.join(stage, rel))
            a["path"] = rel
    if assets:
        q["assets"] = assets

    figs_out = []
    for i, f in enumerate(q.get("figures") or [], 1):
        if f.get("bbox"):
            rel = f"images/{qid(rn, qn)}_{i}.png"
            if crop:
                crop_figure(src, page, f["bbox"], os.path.join(stage, rel))
            figs_out.append({"path": rel, "note": f.get("note", "figure"),
                             "bbox": f["bbox"], "placement": f.get("placement", "지문")})
        elif f.get("path"):
            figs_out.append(f)
    if figs_out or q.get("figures"):
        q["figures"] = figs_out

    q.setdefault("source_pdf", project.source_pdf_name(src))
    q.setdefault("source_pages", [int(page)])
    return q


def render_for(q: dict, src: str, page: int, *,
               mark_reviewed: bool = True) -> tuple[str, str]:
    """(01/ 안의 경로, 그 파일에 들어갈 바이트) — 쓰지 않는다. 게이트용.

    ★ mark_reviewed 기본이 True 인 이유: 게이트는 "지금 확정하면 같은 바이트가
      나오는가" 를 묻는다. 확정은 `reviewed=true · needs_review=false` 를 함께
      쓰므로, 그 표시를 빼고 비교하면 80문항이 그 두 줄만으로 전부 불일치로 뜬다.
    """
    q = dict(q)
    if mark_reviewed:
        q["reviewed"] = True
        q["needs_review"] = False
    q = prepare(q, src, page, crop=False)
    path = md_path(int(q["round"]), int(q["question_no"]))
    return path, paths.to_disk(path, render(q))


def finalize_question(q: dict, src: str, page: int, *,
                      dest_dir: str | None = None) -> dict:
    """그림 bbox 크롭 → 문항 MD 기록. 내용이 바뀐 경우에만 쓴다."""
    rn, qn = int(q["round"]), int(q["question_no"])
    stage = dest_dir or os.path.join(paths.book_dir(), "01")
    q = prepare(q, src, page, crop=True, stage=stage)

    path = os.path.join(stage, f"{qid(rn, qn)}.md")
    text = paths.to_disk(path, render(q))

    cur = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8", newline="") as f:
            cur = f.read()
    if cur == text:
        return {"id": qid(rn, qn), "path": paths.rel(path), "changed": False}
    try:
        backup_sibling(path)
        atomic_write_text(path, text)
    except PermissionError as e:
        raise LockedError(
            f"파일을 저장하지 못했습니다: {paths.rel(path)}. "
            "편집기나 탐색기 미리보기로 열어 두었다면 닫고 다시 시도하세요.") from e
    return {"id": qid(rn, qn), "path": paths.rel(path), "changed": True}


def finalize_page(src: str, page: int, questions: list[dict], *,
                  mark_reviewed: bool = True,
                  dest_dir: str | None = None) -> dict:
    """페이지의 문항들을 확정한다. 회차·문항번호가 없는 문항은 오류로 낸다."""
    bad = [i for i, q in enumerate(questions)
           if not q.get("round") or not q.get("question_no")]
    if bad:
        raise ValueError(
            f"회차 또는 문항번호가 없는 문항이 있습니다 (카드 {[i + 1 for i in bad]}). "
            "상단 '회차' 를 채우고 각 카드의 문항번호를 확인하세요.")

    saved, unchanged = [], []
    for q in questions:
        q = dict(q)
        if mark_reviewed:
            q["reviewed"] = True
            q["needs_review"] = False
        r = finalize_question(q, src, page, dest_dir=dest_dir)
        (saved if r["changed"] else unchanged).append(r["path"])
    return {"ok": True, "saved": saved, "unchanged": unchanged,
            "count": len(questions)}
