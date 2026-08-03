"""확정 게이트 + 회차 정합성 검증.

## 왜 게이트가 필요한가

`01/*.md` 를 쓰는 코드가 두 개가 됐다 — 이 패키지의 `finalize.py`(초안에서 확정)와
`services/book/scan.py`(확정된 md 를 한 문항씩 손보기). 둘이 바이트로 어긋나면
한쪽으로 저장할 때 다른 쪽이 만든 파일이 조용히 바뀐다.

    venv\\Scripts\\python -m services.ocr.checks              두 검사 다
    venv\\Scripts\\python -m services.ocr.checks --refinalize   확정 왕복만
    venv\\Scripts\\python -m services.ocr.checks --round        회차 정합성만

`refinalize` 는 **디스크에 아무것도 쓰지 않는다.** 모든 초안을 확정했을 때의 바이트를
계산해 지금 `01/*.md` 와 비교한다. 이게 통과하지 않으면 UI 의 `확정(MD 저장)` 을
막는다 — 통과하지 못하는 렌더러로 확정하면 이미 검수한 파일이 망가진다.
"""
from __future__ import annotations

import os
import re
from collections import Counter

from services.book import paths
from services.ocr import draft, finalize, project

TOKEN = re.compile(r"\{\{([A-Za-z]+-\d+)\}\}")
INLINE_MATH = re.compile(r"(?<!\\)\$[^$\n]+?(?<!\\)\$")
CIRCLED = "①②③④⑤"
DIFFICULTIES = ("하", "중", "상")


def _read(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


# ── 확정 왕복 (게이트) ──────────────────────────────────────────────────────
def refinalize() -> dict:
    """모든 초안을 확정했을 때의 바이트 = 지금 01/*.md 인가.

    · same     이미 확정돼 있고 바이트가 같다            → 정상
    · new      아직 01/ 에 없다 (판독했지만 미확정)       → 정상. 게이트를 막지 않는다
    · differ   있는데 바이트가 다르다                     → ★ 게이트 실패
    """
    if not project.exists():
        return {"ok": False, "total": 0, "same": 0, "new": 0,
                "error": f"OCR 판독 폴더를 찾을 수 없습니다: {project.ocr_dir() or '(미지정)'}"}

    same, new, differ, errors = 0, [], [], []
    for src, page in draft.all_drafts():
        d = draft.load(src, page)
        for q in (d or {}).get("questions") or []:
            if not q.get("round") or not q.get("question_no"):
                continue
            try:
                path, text = finalize.render_for(q, src, page)
            except Exception as e:
                errors.append({"src": src, "page": page,
                               "question_no": q.get("question_no"),
                               "error": f"{type(e).__name__}: {e}"})
                continue
            cur = _read(path)
            if cur is None:
                new.append(os.path.basename(path)[:-3])
            elif cur == text:
                same += 1
            else:
                i = next((i for i, (a, b) in enumerate(zip(cur, text)) if a != b),
                         min(len(cur), len(text)))
                differ.append({
                    "id": os.path.basename(path)[:-3],
                    "path": paths.rel(path),
                    "at_char": i,
                    "at_line": cur[:i].count("\n") + 1,
                    "expected": repr(cur[max(0, i - 30):i + 30]),
                    "got": repr(text[max(0, i - 30):i + 30]),
                    "bytes_expected": len(cur.encode("utf-8")),
                    "bytes_rendered": len(text.encode("utf-8")),
                })

    total = same + len(new) + len(differ)
    return {
        "ok": not differ and not errors,
        "kind": "초안 → 01/*.md 확정 왕복",
        "total": total, "same": same,
        "new": new[:40], "new_count": len(new),
        "differ": differ[:20], "differ_count": len(differ),
        "errors": errors[:20], "error_count": len(errors),
        "gate": ("확정(MD 저장) 을 쓸 수 있습니다." if not differ and not errors else
                 "★ 확정을 막았습니다 — 지금 렌더러로 확정하면 이미 검수한 "
                 "01/*.md 가 바뀝니다."),
    }


def gate_ok() -> tuple[bool, str]:
    """UI·라우터가 쓰는 짧은 형태."""
    r = refinalize()
    if r.get("error"):
        return False, r["error"]
    if r["ok"]:
        return True, ""
    parts = []
    if r["differ_count"]:
        parts.append(f"바이트 불일치 {r['differ_count']}건")
    if r["error_count"]:
        parts.append(f"렌더 오류 {r['error_count']}건")
    return False, (
        f"확정 왕복 검증이 통과하지 않아 저장을 막았습니다 ({' · '.join(parts)}). "
        "`python -m services.ocr.checks --refinalize` 로 원인을 확인하세요.")


# ── 회차 정합성 ─────────────────────────────────────────────────────────────
def _texts(q: dict) -> list[str]:
    out = [q.get("stem") or "", q.get("jimun") or "", q.get("explanation") or ""]
    out += [c or "" for c in (q.get("choices") or [])]
    return out


def verify_round(src: str, round_no: int, *, total: int | None = None) -> dict:
    """한 회차의 초안이 앞뒤가 맞는가. 판독 직후 / 정답 병합 직후에 돌린다."""
    if total is None:
        total = project.questions_per_round()
    answers: dict[int, str] = {}
    for a in draft.load_answers(src, round_no):
        answers.update({int(k): v for k, v in (a.get("answers") or {}).items()})

    qs: dict[int, dict] = {}
    pages: dict[int, list[int]] = {}
    probs: list[str] = []
    for s, page in draft.all_drafts(src):
        d = draft.load(s, page) or {}
        for q in d.get("questions") or []:
            if int(q.get("round") or 0) != int(round_no):
                continue
            n = int(q.get("question_no") or 0)
            if n in qs:
                probs.append(f"{n}번: 중복 (p{page})")
            qs[n] = q
            pages.setdefault(page, []).append(n)

    if total:
        missing = sorted(set(range(1, total + 1)) - set(qs))
        if missing:
            probs.append(f"누락 문항: {missing}")
        extra = sorted(n for n in qs if not 1 <= n <= total)
        if extra:
            probs.append(f"범위 밖 문항: {extra}")

    bounds = project.subject_bounds()
    for n in sorted(qs):
        q = qs[n]
        ch = q.get("choices") or []
        if len(ch) < 2:
            probs.append(f"{n}번: 보기 {len(ch)}개")
        if not (q.get("stem") or "").strip():
            probs.append(f"{n}번: 발문 비어있음")
        if not (q.get("explanation") or "").strip():
            probs.append(f"{n}번: 해설 비어있음")

        a = q.get("answer") or ""
        if a not in CIRCLED:
            probs.append(f"{n}번: 정답기호 이상 {a!r}")
        elif n in answers and a != answers[n]:
            probs.append(f"{n}번: 정답 불일치 — 초안 {a} vs 정답표 {answers[n]}")
        if q.get("answer_index") != finalize.answer_to_index(a):
            probs.append(f"{n}번: answer_index 불일치")

        assets = q.get("assets") or {}
        used: set[str] = set()
        for t in _texts(q):
            used |= set(TOKEN.findall(t))
        for t in (a2.get("md") or a2.get("text") or "" for a2 in assets.values()):
            used |= set(TOKEN.findall(t))
        if used - set(assets):
            probs.append(f"{n}번: 정의 없는 토큰 {sorted(used - set(assets))}")
        if set(assets) - used:
            probs.append(f"{n}번: 미사용 자산 {sorted(set(assets) - used)}")

        want = next((s for hi, s in bounds if n <= hi), None) if bounds else None
        if want and q.get("subject_no") != want:
            probs.append(f"{n}번: 과목 {q.get('subject_no')} (문항번호 기준 {want})")

        for t in _texts(q):
            if t.count("$") % 2:
                probs.append(f"{n}번: $ 개수 홀수 — 수식 짝 확인 필요")
                break

    latex = sorted(n for n, q in qs.items()
                   if any(INLINE_MATH.search(t) for t in _texts(q))
                   or any(a.get("type") == "latex"
                          for a in (q.get("assets") or {}).values()))
    return {
        "src": src, "round": int(round_no),
        "count": len(qs), "total": total,
        "pages": {str(p): len(v) for p, v in sorted(pages.items())},
        "answers": dict(sorted(Counter(q.get("answer") for q in qs.values()).items(),
                               key=lambda kv: str(kv[0]))),
        "subjects": dict(sorted(Counter(q.get("subject_no") for q in qs.values()).items(),
                                key=lambda kv: str(kv[0]))),
        "difficulty": dict(sorted(
            Counter(q.get("difficulty") for q in qs.values()).items(),
            key=lambda kv: DIFFICULTIES.index(kv[0]) if kv[0] in DIFFICULTIES else 9)),
        "latex": latex,
        "problems": probs,
        "ok": not probs,
    }


def verify_all_rounds() -> list[dict]:
    """초안에 등장하는 (src, 회차) 전부. ★ 회차 수를 하드코딩하지 않는다."""
    seen: dict[tuple[str, int], bool] = {}
    for src, page in draft.all_drafts():
        d = draft.load(src, page) or {}
        for q in d.get("questions") or []:
            rn = q.get("round")
            if rn:
                seen[(src, int(rn))] = True
        if d.get("round"):
            seen.setdefault((src, int(d["round"])), True)
    return [verify_round(src, rn) for src, rn in sorted(seen)]


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main() -> int:
    import argparse
    from dotenv import load_dotenv
    load_dotenv(".env", encoding="utf-8-sig")

    p = argparse.ArgumentParser(description="OCR 확정 게이트 · 회차 정합성 검증")
    p.add_argument("--refinalize", action="store_true", help="확정 왕복만")
    p.add_argument("--refinalize-dry", dest="refinalize", action="store_true",
                   help="--refinalize 와 같다 (쓰지 않는 것이 기본이다)")
    p.add_argument("--round", action="store_true", help="회차 정합성만")
    a = p.parse_args()
    both = not (a.refinalize or a.round)

    rc = 0
    print(f"BOOK: {paths.book_dir()}")
    print(f"OCR : {project.ocr_dir() or '(미지정)'}")
    print()

    if a.refinalize or both:
        r = refinalize()
        if r.get("error"):
            print("[error]", r["error"])
            return 2
        print(f"  초안 → 01/*.md 확정 왕복      "
              f"일치 {r['same']}/{r['total']}"
              + (f"  ·  미확정(신규) {r['new_count']}" if r["new_count"] else "")
              + (f"  ·  불일치 {r['differ_count']}" if r["differ_count"] else ""))
        for d in r["differ"]:
            print(f"  [differ] {d['id']}  line {d['at_line']}")
            print(f"           기대={d['expected']}")
            print(f"           실제={d['got']}")
        for e in r["errors"]:
            print(f"  [error]  p{e['page']} {e['question_no']}번  {e['error']}")
        print(("  [ok] " if r["ok"] else "  [FAIL] ") + r["gate"])
        print()
        rc = rc or (0 if r["ok"] else 1)

    if a.round or both:
        for r in verify_all_rounds():
            print(f"[{r['src']} {r['round']:02d}회]  문항 {r['count']}"
                  + (f"/{r['total']}" if r["total"] else ""))
            print("  페이지별 :", "  ".join(f"p{k}={v}" for k, v in r["pages"].items()))
            print("  정답분포 :", r["answers"])
            print("  과목분포 :", r["subjects"])
            print("  난이도   :", r["difficulty"])
            print(f"  수식 문항 : {len(r['latex'])}개  {r['latex']}")
            if r["problems"]:
                print("  경고:")
                for x in r["problems"]:
                    print("   -", x)
                rc = rc or 1
            else:
                print("  경고: 없음")
            print()
    return rc


if __name__ == "__main__":
    raise SystemExit(_main())
