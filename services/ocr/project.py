"""OCR 작업 폴더 해석 · 소스(PDF) 목록 · 페이지 목록 · 시험 설정.

## 작업 폴더가 두 개다

    D:\\00work\\260730-ocr\\data\\      판독 작업물 — raw_pages/*.png · ocr_draft/*.json
    D:\\00work\\ocr-output-260730\\     책 산출물   — 00/ 01/ 02/ … (= paths.book_dir())

앞쪽을 여기서 'OCR 폴더', 뒤쪽을 'BOOK' 이라 부른다. 원본 도구는 둘을 자기 위치에서
계산했지만(`ROOT.parent / f"ocr-output-{date}"`), 이 앱은 BOOK 을 사용자가 고르므로
방향이 반대다 — BOOK 에서 OCR 폴더를 찾는다.

찾는 순서:
  1. `data/books.json` 의 그 항목에 적힌 `ocr` 경로 (작업 폴더 화면에서 지정)
  2. `.env` 의 `XAM_OCR`
  3. BOOK 폴더 이름에서 유도 — `ocr-output-260730` → 형제 폴더 `260730-ocr`

★ 이 순서는 `pd` 추측 금지 규칙과 다르다. `pd` 는 틀리면 라이브 문제은행을 덮어쓰지만
  OCR 폴더는 틀리면 "초안이 없다" 고 보일 뿐이라 유도해도 안전하다. 대신 화면에
  어느 폴더를 보고 있는지 항상 띄운다.
"""
from __future__ import annotations

import json
import os
import re

from core.constants import OCR_DIR
from services.book import paths

# `ocr-output-260730` → `260730`
_BOOK_DATE_RE = re.compile(r"(?:ocr-output-)?(\d{6})")
_PAGE_RE = re.compile(r"^page_(\d+)\.png$")

# 시험 설정 기본값 — book.json / _book.json 이 없을 때만 쓴다.
DEFAULT_BOOK = {
    "title": "",
    "subjects": {},
    "subject_bounds": [],
    "questions_per_round": 0,
    "round_label": "제{n}회",
    "difficulty_rubric": [],
}


# ── 폴더 ────────────────────────────────────────────────────────────────────
def derive_from_book(book_dir: str) -> str:
    """BOOK 폴더 이름에서 OCR 프로젝트 폴더를 유도한다.

    `D:\\00work\\ocr-output-260730` → `D:\\00work\\260730-ocr`
    날짜를 못 찾으면 빈 문자열(= 유도 실패)을 준다.
    """
    name = os.path.basename(os.path.normpath(book_dir))
    m = _BOOK_DATE_RE.search(name)
    if not m:
        return ""
    return os.path.join(os.path.dirname(os.path.normpath(book_dir)),
                        f"{m.group(1)}-ocr")


def ocr_dir() -> str:
    """지금 쓰는 OCR 폴더. 없으면 빈 문자열."""
    try:
        from services.book import books
        p = books.active_ocr_path()
        if p:
            return p
    except Exception:
        pass
    if OCR_DIR:
        return OCR_DIR
    return derive_from_book(paths.book_dir())


def exists() -> bool:
    d = ocr_dir()
    return bool(d) and os.path.isdir(os.path.join(d, "data"))


def raw_dir() -> str:
    return os.path.join(ocr_dir(), "data", "raw_pages")


def draft_dir() -> str:
    return os.path.join(ocr_dir(), "data", "ocr_draft")


def answers_dir() -> str:
    return os.path.join(ocr_dir(), "data", "answers")


def index_dir() -> str:
    return os.path.join(ocr_dir(), "data", "index")


def scan_png(src: str, page: int) -> str:
    return os.path.join(raw_dir(), src, f"page_{int(page):03d}.png")


def pdf_dir() -> str:
    """원본 PDF 를 넣는 곳 — BOOK 의 00/ 이다(프로젝트 안이 아니다)."""
    return os.path.join(paths.book_dir(), "00")


# ── 시험 설정 ───────────────────────────────────────────────────────────────
def book_config() -> dict:
    """과목 체계·회차당 문항수·회차 표기.

    OCR 폴더의 `book.json` 을 먼저 본다(원본 도구의 규약). 없으면 BOOK 의
    `_book.json`. ★ 모듈 전역에 담지 않는다 — 원본은 `use_book()` 이 전역을 다시
    묶었는데, 이 앱은 작업 폴더가 요청마다 바뀔 수 있어 그 방식이 위험하다.
    """
    cfg = dict(DEFAULT_BOOK)
    cfg.update(_from_examspec())
    for path in (os.path.join(ocr_dir(), "book.json") if ocr_dir() else "",
                 os.path.join(paths.book_dir(), "_book.json")):
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                # ★ `difficulty_rubric` 도 받는다. 난이도 기준은 **문제집별로 다르다**
                #   (2026-08-18 지시) — 코드에 박으면 폴더를 바꿔도 옛 기준이 쓰인다.
                for k in ("title", "subjects", "subject_bounds",
                          "questions_per_round", "round_label", "difficulty_rubric"):
                    if d.get(k):
                        cfg[k] = d[k]
        except (OSError, ValueError):
            continue
    return cfg


def _from_examspec() -> dict:
    """시험정보(`exams/<pd>.json`)에서 과목 체계·난이도를 가져온다.

    ★ **여기가 원천이다.** 문항 집필 화면 하단의 「시험정보 관리」가 이 파일을 고치고,
      문제집이 추가되거나 시험이 개정되면 사람이 그것을 갱신한다(2026-08-18 지시).
      전에는 OCR 쪽이 `book.json` 을 따로 봤다 — 같은 사실을 두 곳에 두면 개정 때
      한쪽만 고쳐지고, 어느 쪽이 맞는지 알 수 없다.

    ★ `book.json` · `_book.json` 은 **여전히 읽는다**(이 함수 뒤에서 덮어쓴다).
      시험정보에 없는 폴더별 예외를 둘 자리가 필요하고, 옛 폴더의 호환도 지킨다.
    """
    try:
        from services.book import books
        from services.authoring import examspec
        pd = (books.active_meta() or {}).get("pd") or ""
        if not pd:
            return {}
        d = examspec.load(pd)
    except Exception:                                  # noqa: BLE001 — 없으면 조용히 건너뛴다
        return {}
    if not isinstance(d, dict):
        return {}

    out: dict = {}
    subs = d.get("subjects") or []
    if subs:
        # subjects: [{no, name, count}] → subjects{no: name} + subject_bounds[(누적 상한, no)]
        names, bounds, acc = {}, [], 0
        for sv in subs:
            try:
                no = int(sv["no"]); cnt = int(sv.get("count") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            names[no] = str(sv.get("name") or "")
            acc += cnt
            bounds.append([acc, no])
        if names:
            out["subjects"] = names
        if bounds:
            out["subject_bounds"] = bounds
    if (d.get("round") or {}).get("size"):
        out["questions_per_round"] = int(d["round"]["size"])
    if d.get("label"):
        out["title"] = str(d["label"])
    rub = (d.get("difficulty") or {}).get("rubric")
    if rub:
        out["difficulty_rubric"] = rub
    return out


def subject_bounds() -> tuple[tuple[int, int], ...]:
    return tuple((int(hi), int(s)) for hi, s in (book_config().get("subject_bounds") or ()))


def subjects() -> dict[int, str]:
    return {int(k): v for k, v in (book_config().get("subjects") or {}).items()}


def questions_per_round() -> int:
    """★ 상수가 아니다. 책마다 다르고(빅분기 80 · SQLD 50), 설정이 없으면 0 이다."""
    return int(book_config().get("questions_per_round") or 0)


def round_label(round_no: int) -> str:
    fmt = book_config().get("round_label") or "제{n}회"
    try:
        return fmt.format(n=int(round_no), nn=f"{int(round_no):02d}")
    except (KeyError, IndexError, ValueError):
        return fmt


def subject_for(question_no: int, subject_no: int | None = None) -> tuple[str, int]:
    """과목명·과목번호. subject_no 가 주어지면 우선, 아니면 문항번호로 추정한다."""
    subs = subjects()
    if subject_no in subs:
        return subs[subject_no], int(subject_no)
    bounds = subject_bounds()
    if not bounds:
        return (subs.get(1, ""), 1) if subs else ("", 1)
    inferred = next((s for hi, s in bounds if question_no <= hi), bounds[-1][1])
    return subs.get(inferred, ""), inferred


# ── 소스(PDF) 목록 ──────────────────────────────────────────────────────────
def load_sources() -> dict:
    """`data/raw_pages/_sources.json`.

    두 가지 형식을 다 읽는다.
      구형(원본 도구)  {"bdae1": "Big Data Analysis Engineer1.pdf"}
      신형(이 앱)      {"bdae1": {"file": …, "role": "문제", "pages": 18,
                                  "sha256": …, "pair": …, "dup_of": …}}
    `_primary` 키는 소스 이름이 아니라 설정이라 그대로 둔다.
    """
    path = os.path.join(raw_dir(), "_sources.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def source_entry(src: str) -> dict:
    """구형·신형을 같은 모양으로 돌려준다."""
    v = load_sources().get(src)
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        return {"file": v, "role": "문제"}
    return {}


def source_pdf_name(src: str) -> str:
    """stem → 원본 PDF 실제 파일명.

    stem 은 슬러그(`bdae1`)라서 그대로 쓰면 실제 파일명과 달라진다. 확정 MD 의
    `source_pdf` 에는 다음 단계 앱들이 출처를 추적하도록 **실명**을 넣는다.
    """
    return source_entry(src).get("file") or f"{src}.pdf"


def rendered_srcs() -> list[str]:
    """렌더된 stem 전체 — 폴더를 센다(설정이 아니라 디스크가 기준)."""
    d = raw_dir()
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if os.path.isdir(os.path.join(d, f)))


def primary_src() -> str | None:
    """검수 UI 를 한 소스로 좁힐 때의 대표 stem. **명시했을 때만** 값이 있다.

    같은 책을 여러 벌 넣은 경우(출판사 PDF + 직접 스캔)에만 쓴다. 서로 다른 내용인
    소스가 여러 개일 때 지정하면 나머지가 통째로 안 보인다.
    ★ 중복 PDF 는 `_primary` 로 숨기지 않는다 — `dup_of` 로 렌더 자체를 건너뛴다.
    """
    p = load_sources().get("_primary")
    return p if isinstance(p, str) and p in rendered_srcs() else None


def visible_srcs() -> list[str]:
    """검수 UI 에 보여줄 소스 — 해설 전용 소스는 목록에서 빼지 않는다.

    해설 PDF 도 사람이 대조해야 하므로 보이는 게 맞다. 다만 `role` 을 같이 줘서
    화면이 '해설' 로 표시할 수 있게 한다.
    """
    p = primary_src()
    if p:
        return [p]
    return rendered_srcs()


def list_pages(src: str) -> list[int]:
    d = os.path.join(raw_dir(), src)
    if not os.path.isdir(d):
        return []
    out = []
    for f in os.listdir(d):
        m = _PAGE_RE.match(f)
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def page_map() -> dict:
    """`data/index/page_map.json` — 페이지 → 회차·문항구간 대응(있을 때만)."""
    path = os.path.join(index_dir(), "page_map.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    if isinstance(d, list):
        return {f'{e.get("src")}:{e.get("page")}': e for e in d}
    return d if isinstance(d, dict) else {}


def info() -> dict:
    """화면 상단에 늘 띄우는 '어디를 보고 있는가'."""
    cfg = book_config()
    return {
        "ocr_dir": ocr_dir(),
        "exists": exists(),
        "book_dir": paths.book_dir(),
        "stage_dir": os.path.join(paths.book_dir(), "01"),
        "pdf_dir": pdf_dir(),
        "title": cfg.get("title") or "",
        "questions_per_round": questions_per_round(),
        "subjects": subjects(),
        "primary": primary_src(),
        "srcs": [dict(source_entry(s), src=s, pages=len(list_pages(s)))
                 for s in rendered_srcs()],
    }
