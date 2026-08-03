"""`00/*.pdf` → `data/raw_pages/<stem>/page_NNN.png` (pypdfium2).

원본은 `260730-ocr/scripts/render.py` 다. 그대로 옮기면 오늘 바로 밟는 지뢰가
셋 있어서 같이 고쳤다. `00/` 의 실측 상태(2026-08-03):

    Big Data Analysis Engineer1.pdf   640KB   → bdae1      (1회차, 18p = 문제12 + 해설6)
    Big Data Analysis Engineer2.pdf   425KB   → bdae2      (2회차 문제)
    Big Data Analysis Engineer3.pdf   491KB   → bdae3      (3회차 문제)
    정답및해설.pdf                     640KB   ★ Engineer1.pdf 과 sha256 동일
    정답및해설2.pdf                    267KB   → bdae2-ans (2회차 해설)
    정답및해설3.pdf                    284KB   → bdae3-ans (3회차 해설)

1. **중복 PDF** — `정답및해설.pdf` 는 `Engineer1.pdf` 과 바이트가 같다(`bfa8dbc…`).
   그대로 렌더하면 1회차 18페이지가 패널에 두 벌 뜬다. sha256 으로 잡아 건너뛰고
   `dup_of` 로 남긴다.
   ★ 기존 `_primary` 로는 못 막는다. 그건 "하나만 보이기" 라서 bdae2·bdae3 까지 숨는다.

2. **한글 stem** — 원본 `slugify` 가 `가-힣` 를 남겨서 `정답및해설2` 가 그대로
   폴더명·URL 이 된다. 해설 PDF 는 짝이 되는 문제 stem 에서 `bdae2-ans` 로 만든다.

3. **1회차와 2·3회차의 구조가 다르다** — 1회차는 한 PDF 안에 문제+해설이고
   2·3회차는 분리다. `_sources.json` 에 `role`·`pair` 를 남겨 다음 단계
   (`answers.py`)가 소스가 둘로 갈린 회차를 다룰 수 있게 한다.

CLI:
    venv\\Scripts\\python -m services.ocr.pdfrender            전부 (이미 있는 것은 건너뜀)
    venv\\Scripts\\python -m services.ocr.pdfrender --force    다시 렌더
    venv\\Scripts\\python -m services.ocr.pdfrender --dry      계획만 보기
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata

from core.atomic_io import atomic_write_text
from services.book import jsonio
from services.ocr import project

DPI = 200

# 자주 쓰는 영문 시험명 축약 — 슬러그를 짧게 유지한다.
ABBREV = {
    "big data analysis engineer": "bdae",
    "big data analyst": "bda",
}

# 해설 파트로 판정하는 파일명 조각. 문제 PDF 와 붙어 있으면 소용없지만,
# 실측 교재는 전부 파일명으로 구분된다.
_ANSWER_HINT = re.compile(r"정답|해설|answer|solution", re.I)
_TRAILING_NUM = re.compile(r"(\d+)\s*$")


def slugify(stem: str) -> str:
    """PDF 파일명 → 경로·URL 에 안전한 짧은 stem."""
    s = unicodedata.normalize("NFKC", stem).strip().lower()
    for long, short in ABBREV.items():
        if s.startswith(long):
            s = short + s[len(long):]
            break
    s = re.sub(r"[^0-9a-z가-힣]+", "-", s).strip("-")
    return s or "src"


def ascii_slug(stem: str) -> str:
    """한글을 뺀 슬러그. 비어 있으면 빈 문자열 — 호출자가 짝에서 이름을 만든다."""
    s = slugify(stem)
    s = re.sub(r"[^0-9a-z\-]+", "-", s).strip("-")
    return s


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _series_no(stem: str) -> int | None:
    """파일명 끝 숫자 = 회차 힌트. `정답및해설2` → 2, `정답및해설` → 1(암묵)."""
    m = _TRAILING_NUM.search(stem)
    return int(m.group(1)) if m else None


def plan() -> dict:
    """`00/` 의 PDF 를 훑어 stem·역할·짝·중복을 정한다. 디스크를 건드리지 않는다."""
    d = project.pdf_dir()
    if not os.path.isdir(d):
        return {"pdf_dir": d, "exists": False, "items": [],
                "error": f"원본 PDF 폴더가 없습니다: {d}"}

    files = sorted(f for f in os.listdir(d) if f.lower().endswith(".pdf"))
    # 문제 PDF 를 먼저 처리해야 해설 PDF 가 짝을 찾을 수 있다.
    questions = [f for f in files if not _ANSWER_HINT.search(os.path.splitext(f)[0])]
    answers = [f for f in files if _ANSWER_HINT.search(os.path.splitext(f)[0])]

    items: list[dict] = []
    by_hash: dict[str, str] = {}
    q_by_no: dict[int, str] = {}

    for name in questions:
        path = os.path.join(d, name)
        stem_raw = os.path.splitext(name)[0]
        stem = slugify(stem_raw)
        h = sha256(path)
        rec = {"file": name, "src": stem, "role": "문제", "sha256": h}
        if h in by_hash:
            rec["dup_of"] = by_hash[h]
        else:
            by_hash[h] = stem
            n = _series_no(stem_raw)
            if n is not None:
                q_by_no.setdefault(n, stem)
        items.append(rec)

    for name in answers:
        path = os.path.join(d, name)
        stem_raw = os.path.splitext(name)[0]
        h = sha256(path)
        n = _series_no(stem_raw)
        pair = q_by_no.get(n if n is not None else 1)
        # ★ 한글 stem 을 폴더명으로 쓰지 않는다. 짝이 있으면 `<짝>-ans`.
        stem = f"{pair}-ans" if pair else (ascii_slug(stem_raw) or "ans")
        rec = {"file": name, "src": stem, "role": "해설", "sha256": h}
        if pair:
            rec["pair"] = pair
        if h in by_hash:
            # 문제 PDF 와 같은 파일 = 그 PDF 안에 해설이 함께 있다는 뜻이다.
            rec["dup_of"] = by_hash[h]
        else:
            by_hash[h] = stem
        items.append(rec)

    return {"pdf_dir": d, "exists": True, "items": items}


def render_pdf(pdf: str, out_dir: str) -> int:
    import pypdfium2 as pdfium

    os.makedirs(out_dir, exist_ok=True)
    doc = pdfium.PdfDocument(pdf)
    n = len(doc)
    scale = DPI / 72.0
    for i in range(n):
        doc[i].render(scale=scale).to_pil().save(
            os.path.join(out_dir, f"page_{i + 1:03d}.png"))
    doc.close()
    return n


def run(*, force: bool = False, dry: bool = False) -> dict:
    """계획대로 렌더하고 `_sources.json` 을 갱신한다."""
    p = plan()
    if not p.get("exists"):
        return p
    if not project.ocr_dir():
        return dict(p, error="OCR 판독 폴더가 지정되지 않았습니다.")

    raw = project.raw_dir()
    prev = project.load_sources()
    sources: dict = {}
    if isinstance(prev.get("_primary"), str):
        sources["_primary"] = prev["_primary"]

    log: list[str] = []
    total = 0
    for rec in p["items"]:
        src, name = rec["src"], rec["file"]
        entry = {k: rec[k] for k in ("file", "role", "sha256") if k in rec}
        if "pair" in rec:
            entry["pair"] = rec["pair"]

        if "dup_of" in rec:
            # ★ 렌더하지 않는다. 같은 내용이 두 벌 뜨는 것을 막는 자리다.
            entry["dup_of"] = rec["dup_of"]
            entry["skipped"] = "중복(sha256 동일)"
            log.append(f"  건너뜀  {name}  ≡ {rec['dup_of']} (내용 동일)")
            # stem 이 겹치면(같은 짝) 기록을 덮지 않는다.
            sources.setdefault(f"{src}#dup", entry)
            continue

        out_dir = os.path.join(raw, src)
        existing = project.list_pages(src)
        if existing and not force:
            entry["pages"] = len(existing)
            sources[src] = entry
            log.append(f"  유지    {name} → {src}/  ({len(existing)}p, 이미 있음)")
            total += len(existing)
            continue
        if dry:
            entry["pages"] = None
            sources[src] = entry
            log.append(f"  (계획)  {name} → {src}/")
            continue
        n = render_pdf(os.path.join(p["pdf_dir"], name), out_dir)
        entry["pages"] = n
        sources[src] = entry
        log.append(f"  렌더    {name} → {src}/  ({n}p)")
        total += n

    if not dry:
        os.makedirs(raw, exist_ok=True)
        idx = os.path.join(raw, "_sources.json")
        atomic_write_text(idx, jsonio.render(idx, sources))

    return {"pdf_dir": p["pdf_dir"], "exists": True, "items": p["items"],
            "sources": sources, "log": log, "pages": total, "dry": dry}


def _main() -> int:
    import argparse
    from dotenv import load_dotenv
    load_dotenv(".env", encoding="utf-8-sig")

    ap = argparse.ArgumentParser(description="00/*.pdf → data/raw_pages/<stem>/*.png")
    ap.add_argument("--force", action="store_true", help="이미 렌더된 것도 다시")
    ap.add_argument("--dry", action="store_true", help="계획만 보고 쓰지 않는다")
    a = ap.parse_args()

    r = run(force=a.force, dry=a.dry)
    print(f"원본 폴더: {r.get('pdf_dir')}")
    print(f"OCR 폴더 : {project.ocr_dir() or '(미지정)'}")
    if r.get("error"):
        print("[error]", r["error"])
        return 2
    for line in r.get("log") or []:
        print(line)
    print(f"TOTAL: {r.get('pages')} pages" + ("  (--dry)" if a.dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
