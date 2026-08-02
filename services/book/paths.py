"""BOOK 트리의 모든 경로 템플릿 — 여기 한 곳에서만 조립한다.

BOOK 은 도구 #1 이 원격 세션에서 만들어 동기화해 준 외부 트리다. 경로 규칙이
코드 여러 군데에 흩어지면 책이 하나 더 생겼을 때 반드시 한 곳을 빠뜨린다.
"""
from __future__ import annotations

import os
import re
from typing import Iterator

from core.constants import (
    BOOK_DIR, BUNDLES_PER_ROUND, QUESTIONS_PER_BUNDLE, SUMMARY_KEYS,
)

# ── 식별자 ──────────────────────────────────────────────────────────────────
QID_RE = re.compile(r"^m(\d{2})-(\d{2})$")           # m01-07
BUNDLE_RE = re.compile(r"^m(\d{2})-(\d{1,2})$")      # m01-1
ROUND_RE = re.compile(r"^m(\d{2})$")                 # m01


def book_dir() -> str:
    """지금 쓰는 BOOK 경로.

    ★ .env 의 XAM_BOOK 은 '첫 실행 기본값' 이고, 실제로는 작업 폴더 화면에서 고른
      폴더(data/books.json 의 active)를 쓴다. 그래서 상수가 아니라 함수다 —
      이 모듈의 모든 경로 함수가 이걸 거치므로 폴더 전환이 즉시 반영된다.
      books 모듈을 못 불러오는 상황(초기 부팅·순환 import)에서는 상수로 떨어진다.
    """
    try:
        from services.book import books
        return books.active_path()
    except Exception:
        return BOOK_DIR


def exists() -> bool:
    """BOOK 이 쓸 수 있는 상태인가 — _rounds 와 02 가 다 있어야 한다.

    01/ 만 있는 폴더(#1 을 돌리고 #2 를 돌리기 직전)는 False 다. 문항 교정·영상·발행은
    못 하지만 '구조화 MD로 정리' 화면은 된다 — 그 화면은 scan_exists() 를 본다.
    """
    return os.path.isdir(os.path.join(book_dir(), "_rounds")) and \
           os.path.isdir(os.path.join(book_dir(), "02"))


def scan_exists() -> bool:
    """01/ 기출 md 가 있는가 — '구조화 MD로 정리' 화면의 전제."""
    return os.path.isdir(os.path.join(book_dir(), "01"))


def round_codes() -> list[str]:
    """이 폴더에 **실제로 있는** 회차 코드.

    ★ 상수로 두면 안 된다. 빅데이터는 3회차지만 SQLD 는 21회차이고, 어느 책이든
      처음에는 1~2회차만 들어온다. _rounds/mNN.json 을 세어서 만든다.
      _rounds 가 아직 없으면 빈 리스트다 — 호출자가 "아직 없음" 을 그려야 한다.
    """
    d = os.path.join(book_dir(), "_rounds")
    try:
        return sorted(f[:-5] for f in os.listdir(d)
                      if f.endswith(".json") and ROUND_RE.match(f[:-5]))
    except OSError:
        return []


def rel(path: str) -> str:
    """BOOK 상대경로로 되돌린다. _index.json 의 `path` 필드가 이 형식이다."""
    try:
        return os.path.relpath(path, book_dir()).replace("\\", "/")
    except ValueError:
        return path


# ── 식별자 파싱 · 조립 ──────────────────────────────────────────────────────
def qid(round_no: int, question_no: int) -> str:
    """(1, 7) → 'm01-07'. 02/*.md 의 id 이자 ex_problem.src_id 다."""
    return f"m{int(round_no):02d}-{int(question_no):02d}"


def parse_qid(value: str) -> tuple[int, int] | None:
    m = QID_RE.match((value or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def round_code(round_no: int) -> str:
    return f"m{int(round_no):02d}"


def parse_round_code(value: str) -> int | None:
    m = ROUND_RE.match((value or "").strip())
    return int(m.group(1)) if m else None


def bundle_of(round_no: int, question_no: int) -> str:
    """문항 → 그 문항이 실린 영상 번들. 번들은 10문항씩 묶여 있다.

    (1, 7)  → 'm01-1'
    (1, 10) → 'm01-1'
    (1, 11) → 'm01-2'
    (3, 80) → 'm03-8'
    """
    part = (int(question_no) - 1) // QUESTIONS_PER_BUNDLE + 1
    return f"m{int(round_no):02d}-{part}"


def bundle_range(bundle: str) -> tuple[int, int] | None:
    """'m01-3' → (21, 30). 번들이 담당하는 문항 번호 구간."""
    m = BUNDLE_RE.match((bundle or "").strip())
    if not m:
        return None
    part = int(m.group(2))
    lo = (part - 1) * QUESTIONS_PER_BUNDLE + 1
    return lo, lo + QUESTIONS_PER_BUNDLE - 1


def parse_bundle(bundle: str) -> tuple[int, int] | None:
    """'m01-3' → (round=1, part=3)."""
    m = BUNDLE_RE.match((bundle or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def bundles_in_round(round_code: str) -> int:
    """그 회차의 번들 수 — 문항 수에서 계산한다.

    ★ 상수(8)로 고정하면 안 된다. 빅데이터는 80문항/회차라 8개지만, 회차당 문항 수가
      다른 책이 오면(예: 50문항 → 5개) 있지도 않은 번들 3개를 '미생성' 으로 띄운다.
      _rounds 를 못 읽으면 상수로 떨어진다.
    """
    import json
    try:
        with open(rounds_json(round_code), encoding="utf-8") as f:
            n = len(json.load(f).get("questions") or [])
        if n:
            return -(-n // QUESTIONS_PER_BUNDLE)      # 올림
    except (OSError, ValueError):
        pass
    return BUNDLES_PER_ROUND


def all_bundles() -> list[str]:
    """이 폴더의 번들 코드.

    회차 수도 회차당 번들 수도 폴더에서 읽는다 — 3회차든 9회차든 21회차든 맞는다.
    """
    return [f"{rc}-{p}"
            for rc in round_codes()
            for p in range(1, bundles_in_round(rc) + 1)]


def all_qids() -> Iterator[str]:
    from core.constants import QUESTIONS_PER_ROUND
    for rc in round_codes():
        rn = parse_round_code(rc)
        for qno in range(1, QUESTIONS_PER_ROUND + 1):
            yield qid(rn, qno)


# ── _rounds/ 집필 원천 ──────────────────────────────────────────────────────
def rounds_json(round_code_or_no) -> str:
    rc = round_code_or_no if isinstance(round_code_or_no, str) else round_code(round_code_or_no)
    return os.path.join(book_dir(), "_rounds", f"{rc}.json")


# ── 01/ 기출 OCR (읽기 전용) ────────────────────────────────────────────────
def source_md(source_id: str) -> str:
    """derived_from('01-09') → 01/01-09.md. 에디터의 기출 대조용."""
    return os.path.join(book_dir(), "01", f"{source_id}.md")


# ── 02/ 자사 문항 ───────────────────────────────────────────────────────────
def q_md(question_id: str) -> str:
    return os.path.join(book_dir(), "02", f"{question_id}.md")


def q_svg(asset_name: str) -> str:
    """asset_name 은 확장자 없는 이름('m01-02-dmz')이다."""
    name = asset_name if asset_name.endswith(".svg") else f"{asset_name}.svg"
    return os.path.join(book_dir(), "02", "assets", name)


def q_assets_dir() -> str:
    return os.path.join(book_dir(), "02", "assets")


def q_index() -> str:
    return os.path.join(book_dir(), "02", "_index.json")


def q_stats() -> str:
    return os.path.join(book_dir(), "02", "difficulty_stats.json")


# ── 03/ 요약노트 ────────────────────────────────────────────────────────────
def summary_html(key: str) -> str:
    return os.path.join(book_dir(), "03", f"summary_{key}.html")


def summary_md(key: str) -> str:
    return os.path.join(book_dir(), "03", f"summary_{key}.md")


def summary_index_html() -> str:
    return os.path.join(book_dir(), "03", "summary_index.html")


def summary_keys() -> tuple[str, ...]:
    return SUMMARY_KEYS


# ── 04/ 회차 lesson (읽기 전용 — build_check.py 가 읽지 않는다) ─────────────
def round_lesson(round_code_or_no) -> str:
    rc = round_code_or_no if isinstance(round_code_or_no, str) else round_code(round_code_or_no)
    return os.path.join(book_dir(), "04", f"lesson_{rc}.json")


# ── 05/ 영상 번들 ───────────────────────────────────────────────────────────
def bundle_dir(bundle: str) -> str:
    return os.path.join(book_dir(), "05", bundle)


def bundle_lesson(bundle: str) -> str:
    """★ 문제 본문이 실제로 웹에 가는 경로.

    axexam 의 build_check.py 는 문제문·보기·해설·정답을 이 파일에서만 읽는다.
    02/*.md 는 과목·난이도·태그·검수상태만 공급한다. 문항을 고칠 때 이 파일을
    같이 쓰지 않으면 수정이 웹에 전혀 반영되지 않는다.
    """
    return os.path.join(bundle_dir(bundle), "source", f"lesson_{bundle}.json")


def bundle_deck(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "source", "deck.html")


def bundle_script(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "script", f"{bundle}_script.json")


def bundle_review(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "review.json")


def bundle_mp4(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "draft", f"{bundle}.static.mp4")


def bundle_vtt(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "draft", f"{bundle}.ko.vtt")


def bundle_srt(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "subtitles", "subtitles.srt")


def bundle_images_dir(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "images")


def bundle_audio_dir(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "audio")


# ── 06/ 발행 산출물 (axexam build_check.py 가 소유) ─────────────────────────
def out_dir() -> str:
    return os.path.join(book_dir(), "06")


def problems_json() -> str:
    return os.path.join(out_dir(), "problems.json")


# ── 파일 상태 ───────────────────────────────────────────────────────────────
def etag(path: str) -> str:
    """mtime_ns-size. BOOK 은 외부에서 다시 동기화될 수 있어서 저장 전에 대조한다."""
    try:
        st = os.stat(path)
        return f"{st.st_mtime_ns}-{st.st_size}"
    except FileNotFoundError:
        return "0-0"


def mtime(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except FileNotFoundError:
        return 0.0


def size(path: str) -> int:
    try:
        return os.stat(path).st_size
    except FileNotFoundError:
        return 0


def book_url(path: str) -> str:
    """BOOK 안의 파일 → 브라우저가 읽을 /book/... URL (mp4 · vtt · svg 미리보기)."""
    return "/book/" + rel(path)
