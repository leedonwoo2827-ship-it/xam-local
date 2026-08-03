"""분리형 교재의 정답·해설을 문제 초안에 주입 (원본 `scripts/merge_answers.py`).

## 교재 유형 두 가지

    A. 문제 + 해설이 같은 페이지 (SQLD)      판독 때 한 문항에 다 채운다 → 이 단계 불필요
    B. 문제 파트와 해설 파트가 분리 (빅분기)  회차 뒤쪽에 정답표+해설이 몰려 있다

B 는 두 단계다. 판독은 `stem`·`choices`·`assets` 만 채우고, 정답·해설은 회차 단위로
`data/answers/<src>_rNN.json` 에 모아 여기서 문항번호로 맞춰 넣는다.

    {"src": "bdae2", "answer_src": "bdae2-ans", "round": 2,
     "question_pages": [1, …, 13], "answer_pages": [1, …, 7],
     "answers":      {"1": "②", …},
     "explanations": {"1": "…", …},
     "explanation_assets": {"2": {"t-1": {…}}}}

★ `answer_src` 가 이 앱에서 새로 생긴 키다. 1회차는 문제와 해설이 **한 PDF**(bdae1
  18페이지) 안에 있어서 페이지 번호가 하나의 좌표계였다. 2·3회차는 문제 PDF 와 해설
  PDF 가 **따로**라서 양쪽 모두 1페이지부터 시작한다. 그걸 구분하지 않으면
  `answer_pages: [1..7]` 이 문제 1~7페이지로 읽힌다.

  `source_pages` 는 기존 형식(정수 목록)을 유지한다 — 1회차 80문항이 이미 그 형태로
  확정돼 있어 형식을 바꾸면 바이트가 어긋난다. 대신 해설이 다른 소스에서 왔으면
  초안에 `answer_src`·`answer_pdf` 를 남겨 출처를 추적할 수 있게 한다.

이미 값이 있으면 `force=False` 에서는 건드리지 않는다 — 검수한 내용을 보호한다.
"""
from __future__ import annotations

from services.ocr import draft, finalize, project


def merge_one(doc: dict, *, force: bool = False, check: bool = False) -> dict:
    """정답 파일 하나를 초안에 반영한다. check=True 면 쓰지 않고 대조만."""
    src = str(doc["src"])
    rnd = int(doc["round"])
    answer_src = str(doc.get("answer_src") or src)
    answers = {int(k): v for k, v in (doc.get("answers") or {}).items()}
    expls = {int(k): v for k, v in (doc.get("explanations") or {}).items()}
    ex_assets = {int(k): v for k, v in (doc.get("explanation_assets") or {}).items()}
    answer_pages = [int(p) for p in (doc.get("answer_pages") or [])]
    answer_pdf = project.source_pdf_name(answer_src) if answer_src != src else ""

    stat = {"문항": 0, "정답주입": 0, "해설주입": 0, "건너뜀": 0, "정답없음": 0}
    seen: set[int] = set()
    written: list[str] = []

    for s, page in draft.all_drafts(src):
        d = draft.load(s, page)
        if not d:
            continue
        dirty = False
        for q in d.get("questions") or []:
            if int(q.get("round") or 0) != rnd:
                continue
            qn = int(q.get("question_no") or 0)
            seen.add(qn)
            stat["문항"] += 1

            if qn not in answers:
                stat["정답없음"] += 1
                continue

            if q.get("answer") and not force:
                stat["건너뜀"] += 1
            else:
                if q.get("answer") != answers[qn]:
                    q["answer"] = answers[qn]
                    q["answer_index"] = finalize.answer_to_index(answers[qn])
                    dirty = True
                stat["정답주입"] += 1

            expl = expls.get(qn, "")
            if expl and (force or not (q.get("explanation") or "").strip()):
                q["explanation"] = expl
                if qn in ex_assets:
                    q.setdefault("assets", {}).update(ex_assets[qn])
                # 출처 = 문제가 실린 페이지 + 해설이 실린 페이지
                sp = {int(p) for p in (q.get("source_pages") or [])}
                sp.add(int(page))
                sp |= set(answer_pages)
                q["source_pages"] = sorted(sp)
                if answer_pdf:
                    # 해설이 다른 PDF 에서 왔다 — 정수 목록만으로는 구분이 안 되므로
                    # 초안에 출처를 남긴다(확정 MD 형식은 건드리지 않는다).
                    q["answer_src"] = answer_src
                    q["answer_pdf"] = answer_pdf
                dirty = True
                stat["해설주입"] += 1

        if dirty and not check:
            _, wrote = draft.save(s, page, d)
            if wrote:
                written.append(f"{s}_p{page:03d}.json")

    warn = []
    missing = sorted(set(answers) - seen)
    if missing:
        warn.append(f"정답표엔 있으나 문제 초안에 없는 문항: {missing}")
    extra = sorted(seen - set(answers))
    if extra:
        warn.append(f"문제 초안엔 있으나 정답표에 없는 문항: {extra}")

    return {"src": src, "round": rnd, "answer_src": answer_src,
            "file": doc.get("_file", ""), "stat": stat,
            "warnings": warn, "written": written, "check": check}


def merge(src: str | None = None, round_no: int | None = None, *,
          force: bool = False, check: bool = False) -> dict:
    docs = draft.load_answers(src, round_no)
    if not docs:
        return {"ok": False, "results": [],
                "error": f"정답 파일이 없습니다: {project.answers_dir()}"}
    results = [merge_one(d, force=force, check=check) for d in docs]
    return {"ok": True, "results": results,
            "written": [w for r in results for w in r["written"]]}


def _main() -> int:
    import argparse
    from dotenv import load_dotenv
    load_dotenv(".env", encoding="utf-8-sig")

    p = argparse.ArgumentParser(description="정답·해설을 문제 초안에 주입")
    p.add_argument("--src", help="문제 소스 stem (예: bdae2)")
    p.add_argument("--round", type=int, help="회차 번호")
    p.add_argument("--force", action="store_true", help="기존 값도 덮어쓴다")
    p.add_argument("--check", action="store_true", help="쓰지 않고 대조만")
    a = p.parse_args()

    r = merge(a.src, a.round, force=a.force, check=a.check)
    if not r["ok"]:
        print("[error]", r["error"])
        return 2
    for res in r["results"]:
        head = f"{res['file'] or res['src']}  ({res['src']} {res['round']:02d}회"
        if res["answer_src"] != res["src"]:
            head += f", 해설 {res['answer_src']}"
        print(head + ")")
        print("  " + "  ".join(f"{k} {v}" for k, v in res["stat"].items()))
        for w in res["warnings"]:
            print("  [경고]", w)
    if a.check:
        print("(--check: 파일을 쓰지 않았습니다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
