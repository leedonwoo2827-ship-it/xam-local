#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exam-forge build helper.

회차 데이터(rounds/mNN.json)를 읽어 파이프라인 산출물을 결정적으로 생성한다.
  - 02/{id}.md            : 문항 MD (YAML frontmatter + 문제/지문/보기/해설)
  - 04/lesson_{code}.json : 문제 영상 대본 (compy-ui-mujejip lesson JSON, include_lecture=false)
  - 02/assets/{id}.svg    : 그림 문항 SVG
  - 02/_index.json        : 전체 문항 메타 목록 (재집계)
  - 02/difficulty_stats.json : 난이도/과목/정답 분포 통계 (재집계)

표준 라이브러리만 사용. Python 3.11+.

사용 예:
  python build.py --book D:/00work/ocr-output-260723
  python build.py --book D:/00work/ocr-output-260723 --round m01 --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# 콘솔 인코딩(cp949 등)에서 한글/기호 출력 시 크래시 방지
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

CIRCLED = ["①", "②", "③", "④"]


# ----------------------------------------------------------------------------- helpers
def circled(idx: int) -> str:
    if 0 <= idx < len(CIRCLED):
        return CIRCLED[idx]
    raise ValueError(f"answer_index out of range: {idx}")


def detect_flags(q: dict) -> tuple[bool, bool, bool]:
    blob = "\n".join(
        str(x) for x in [
            q.get("question", ""), q.get("passage") or "", q.get("explanation", ""),
        ] + list(q.get("choices", []))
    )
    has_sql = bool(q.get("sql")) or "```sql" in blob or bool(re.search(r"\bSELECT\b|\bINSERT\b|\bCREATE\b", blob))
    has_table = bool(q.get("table")) or (bool(re.search(r"\n\s*\|", blob)) and "---" in blob)
    has_figure = bool(q.get("svg")) or bool(q.get("assets")) or "![" in blob or "<svg" in blob
    return has_figure, has_sql, has_table


def to_plain(text: str) -> str:
    """lesson JSON의 화면/자막/낭독 필드용 순수 텍스트화.
    마크다운 리터럴(볼드 **, 인라인 코드 `, 이미지 ![](), 코드펜스 ```)을 제거하되
    단일 `*`(SELECT * 등)는 보존한다. (MD/02 산출물에는 적용하지 않음)"""
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)     # 이미지 마크다운 제거
    s = re.sub(r"(?m)^[ \t]*```[^\n]*$", "", s)      # 코드펜스 라인 제거(내용은 유지)
    s = s.replace("**", "")                           # 볼드 마커 제거(단일 * 는 보존)
    s = s.replace("`", "")                            # 인라인 코드 백틱 제거
    s = re.sub(r"\n{3,}", "\n\n", s)                  # 과다 빈 줄 정리
    return s.strip()


def to_speech(text: str) -> str:
    """낭독(TTS) 필드용. to_plain 후 괄호 (…) 안 부가설명을 '읽지 않도록' 제거.
    (자막/화면 필드에는 적용하지 않음 → 괄호 유지)"""
    s = to_plain(text)
    prev = None
    while prev != s:  # 중첩 괄호까지 제거
        prev = s
        s = re.sub(r"\s*\([^()]*\)", "", s)      # 반각 ()
        s = re.sub(r"\s*（[^（）]*）", "", s)      # 전각 （）
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s+([,.!?、。])", r"\1", s)
    return s.strip()


def asset_names(q: dict, qid: str) -> list[str]:
    """문항이 참조하는 SVG 파일명 집합(순서 유지, 중복 제거).
    assets[].name + 레거시 svg(→{id}.svg) + 본문 ](assets/NAME) 참조."""
    names: list[str] = []
    for a in q.get("assets", []) or []:
        n = str(a["name"])
        names.append(n if n.endswith(".svg") else n + ".svg")
    svg = q.get("svg")
    if svg and str(svg).strip().startswith("<svg"):
        names.append(f"{qid}.svg")
    blob = "\n".join(str(x) for x in [
        q.get("question", ""), q.get("passage") or "", q.get("explanation", "")])
    for m in re.finditer(r"\]\(assets/([^)\s]+)\)", blob):
        nm = m.group(1)
        names.append(nm if nm.endswith(".svg") else nm + ".svg")
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def yaml_escape(s: str) -> str:
    # 단순 스칼라: 특수문자 있으면 큰따옴표로 감싸기
    if s == "" or re.search(r'[:#\[\]{}",&*?|<>=!%@`]', s) or s.strip() != s:
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return s


def render_frontmatter(fm: dict) -> str:
    lines = ["---"]
    order = [
        "id", "round", "round_label", "subject", "subject_no", "question_no",
        "answer", "answer_index", "difficulty", "tags", "derived_from",
        "has_figure", "has_sql", "has_table",
        "authored_by", "verified", "reviewed", "needs_review",
    ]
    for k in order:
        v = fm.get(k)
        if k == "tags":
            arr = ", ".join(yaml_escape(str(t)) for t in (v or []))
            lines.append(f"tags: [{arr}]")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, int):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {yaml_escape(str(v))}")
    lines.append("---")
    return "\n".join(lines)


def render_choices_md(choices: list[str]) -> str:
    out = []
    for i, c in enumerate(choices):
        mark = circled(i)
        c = str(c)
        if "\n" in c or "```" in c:
            out.append(f"{mark}\n\n{c.strip()}\n")
        else:
            out.append(f"{mark} {c.strip()}")
    return "\n".join(out)


def render_table_md(t: dict) -> str:
    """구조화 표 {columns, rows} → GitHub 마크다운 표."""
    cols = [str(c) for c in t.get("columns", [])]
    rows = t.get("rows", [])
    out = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def render_md(fm: dict, q: dict) -> str:
    parts = [render_frontmatter(fm), "", "## 문제", q["question"].strip(), ""]
    passage = q.get("passage")
    table = q.get("table")
    sql = q.get("sql")
    svg = q.get("svg")
    if passage or table or sql or svg:
        parts.append("## 지문")
        if passage:
            parts.append(passage.strip())
        if table:
            parts.append(render_table_md(table))
        if sql:
            parts.append("```sql\n" + str(sql).strip() + "\n```")
        if svg and str(svg).strip().startswith("<svg"):
            parts.append(f"\n![figure](assets/{fm['id']}.svg)")
        parts.append("")
    parts.append("## 보기")
    parts.append(render_choices_md(q["choices"]))
    parts.append("")
    parts.append("## 해설")
    parts.append(q["explanation"].strip())
    parts.append("")
    return "\n".join(parts)


def build_frontmatter(round_meta: dict, q: dict) -> dict:
    code = round_meta["round_code"]
    qno = q["question_no"]
    qid = f"{code}-{qno:02d}"
    hf, hs, ht = detect_flags(q)
    return {
        "id": qid,
        "round": round_meta["round"],
        "round_label": round_meta["round_label"],
        "subject": q["subject"],
        "subject_no": q["subject_no"],
        "question_no": qno,
        "answer": circled(q["answer_index"]),
        "answer_index": q["answer_index"],
        "difficulty": q["difficulty"],
        "tags": q.get("tags", []),
        "derived_from": q.get("derived_from", ""),
        "has_figure": hf,
        "has_sql": hs,
        "has_table": ht,
        "authored_by": "claude",
        "verified": True,
        "reviewed": False,
        "needs_review": True,
    }


def lesson_problem_block(q: dict, qid: str, names: list[str]) -> dict:
    # question 엔 질문만. 지문(passage)·표(table)·코드(sql)는 구조화 필드로 분리 → 렌더가 또렷하게.
    # 텍스트 필드는 순수 텍스트(마크다운 제거). sql/table 은 원형 유지.
    block = {
        "number": q["question_no"],
        "type": "multiple_choice",
        "question": to_plain(q["question"]),
    }
    if q.get("passage"):
        block["passage"] = to_plain(q["passage"])       # 긴 지문 → 별도 '지문 씬'
    if q.get("sql"):
        block["sql"] = str(q["sql"]).strip()             # 코드 문자열 그대로 → 모노스페이스 코드카드
    if q.get("table"):
        block["table"] = q["table"]                       # {columns, rows} 구조 그대로
    # choices는 원문자 접두 없이 순수 텍스트(렌더러가 번호 부여 → ①① 중복 방지)
    block["choices"] = [to_plain(str(c)) for c in q["choices"]]
    if q.get("hide_choices") is not None:
        block["hide_choices"] = bool(q["hide_choices"])  # true=문제 화면 보기 생략, TTS는 낭독
    block.update({
        "answer": circled(q["answer_index"]),             # 해설 다중 페이지에도 정답 배너 유지용
        "answer_index": q["answer_index"],
        "explanation": to_plain(q["explanation"]),
        # 낭독체(소리나는 대로). 괄호 (…) 부가설명은 읽지 않도록 to_speech가 제거(자막은 유지).
        # #3는 "정답은 N번" 자동 삽입 안 함 → 정답 안내는 "정답은 N번입니다. …"로 시작하게 집필.
        "explanation_speech": to_speech(q.get("explanation_speech") or q["explanation"]),
        "difficulty": q["difficulty"],
        "tags": q.get("tags", []),
    })
    if names:  # 참조 SVG 파일명(도형은 04/assets 에 동반 복사됨)
        block["assets"] = names
    if q.get("narration_question"):
        block["narration_question"] = to_speech(q["narration_question"])
    if q.get("narration_answer"):
        block["narration_answer"] = to_speech(q["narration_answer"])
    return block


def build_lesson(round_meta: dict, questions: list[dict]) -> dict:
    code = round_meta["round_code"]
    blocks = []
    last_subject = None
    for q in questions:
        if q["subject"] != last_subject:
            blocks.append({
                "kind": "section",
                "title": q["subject"],
                "subtitle": f"{q['subject_no']}과목",
                "narration": f"{round_meta['round_label']} {q['subject']} 문제입니다.",
            })
            last_subject = q["subject"]
        qid = f"{code}-{q['question_no']:02d}"
        blocks.append({"kind": "problem", **lesson_problem_block(q, qid, asset_names(q, qid))})
    return {
        "version": "1.0",
        "kind": "lesson",
        "chapter": round_meta["round"],
        "title": f"{round_meta['round_label']} — 문제 풀이(문제 전용)",
        "subject": round_meta.get("subject_default", "SQLD"),
        "theme": round_meta.get("theme", "sqld"),
        "scenes_per_problem": round_meta.get("scenes_per_problem", 2),
        "include_lecture": False,
        "countdown_seconds": round_meta.get("countdown_seconds", 5),
        "gap_seconds": round_meta.get("gap_seconds", 1.5),
        "round": round_meta["round_label"],
        "voice": round_meta.get("voice", "F2"),
        "speed": round_meta.get("speed", 1.05),
        "ai_reading": round_meta.get("ai_reading", False),
        "blocks": blocks,
    }


# ----------------------------------------------------------------------------- core
def process_round(path: Path, book: Path, dry: bool) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    code = data["round_code"]
    questions = sorted(data["questions"], key=lambda x: x["question_no"])
    dir02 = book / "02"
    dir04 = book / "04"
    assets = dir02 / "assets"
    assets04 = dir04 / "assets"

    def write_asset(name: str, svg_text: str) -> None:
        # 도형은 02/assets(문제용)와 04/assets(영상 대본 동반) 양쪽에 기록.
        if dry:
            return
        for d in (assets, assets04):
            d.mkdir(parents=True, exist_ok=True)
            (d / name).write_text(svg_text, encoding="utf-8")

    index_items = []
    for q in questions:
        fm = build_frontmatter(data, q)
        md = render_md(fm, q)
        md_path = dir02 / f"{fm['id']}.md"
        if not dry:
            dir02.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md, encoding="utf-8")
        # SVG 자산 — 문항당 여러 개 허용(문제/지문/해설 어디서든 ![..](assets/NAME.svg)로 참조).
        # (a) assets[]: [{"name": "m01-09-erd", "svg": "<svg ...>"}]  → {02,04}/assets/NAME.svg
        for a in q.get("assets", []) or []:
            name = str(a["name"])
            if not name.endswith(".svg"):
                name += ".svg"
            write_asset(name, a["svg"])
        # (b) 레거시 단일 svg(인라인 문자열) → {02,04}/assets/{id}.svg (지문에 자동 첨부)
        svg = q.get("svg")
        if svg and str(svg).strip().startswith("<svg"):
            write_asset(f"{fm['id']}.svg", svg)
        index_items.append({
            "id": fm["id"], "round": fm["round"], "subject": fm["subject"],
            "subject_no": fm["subject_no"], "question_no": fm["question_no"],
            "answer": fm["answer"], "answer_index": fm["answer_index"],
            "difficulty": fm["difficulty"], "tags": fm["tags"],
            "derived_from": fm["derived_from"],
            "has_figure": fm["has_figure"], "has_sql": fm["has_sql"], "has_table": fm["has_table"],
            "reviewed": False, "n_choices": len(q["choices"]),
            "path": f"02/{fm['id']}.md",
        })

    lesson = build_lesson(data, questions)
    if not dry:
        dir04.mkdir(parents=True, exist_ok=True)
        (dir04 / f"lesson_{code}.json").write_text(
            json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{code}] {len(questions)}문항 → 02/*.md, 04/lesson_{code}.json" + (" (dry-run)" if dry else ""))
    return index_items


def regenerate_index_stats(book: Path, all_items: list[dict], dry: bool) -> None:
    dir02 = book / "02"
    all_items = sorted(all_items, key=lambda x: (x["round"], x["question_no"]))
    index = {"count": len(all_items), "items": all_items}
    diff = Counter(i["difficulty"] for i in all_items)
    subj = Counter(i["subject"] for i in all_items)
    ans = Counter(i["answer"] for i in all_items)
    by_round: dict[str, dict] = {}
    for it in all_items:
        r = str(it["round"])
        b = by_round.setdefault(r, {"count": 0, "difficulty": Counter(), "subject": Counter(),
                                    "with_figure": 0, "with_sql": 0})
        b["count"] += 1
        b["difficulty"][it["difficulty"]] += 1
        b["subject"][it["subject"]] += 1
        b["with_figure"] += 1 if it["has_figure"] else 0
        b["with_sql"] += 1 if it["has_sql"] else 0
    for r, b in by_round.items():
        b["difficulty"] = dict(b["difficulty"])
        b["subject"] = dict(b["subject"])
    stats = {
        "total": len(all_items),
        "overall": {"difficulty": dict(diff), "subject": dict(subj), "answer": dict(ans)},
        "by_round": by_round,
    }
    if not dry:
        dir02.mkdir(parents=True, exist_ok=True)
        (dir02 / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        (dir02 / "difficulty_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[index] {len(all_items)}문항 · 난이도 {dict(diff)} · 정답분포 {dict(ans)}" + (" (dry-run)" if dry else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="exam-forge build helper")
    ap.add_argument("--book", required=True, help="책 루트 (예: D:/00work/ocr-output-260723)")
    ap.add_argument("--rounds-dir", default=None, help="회차 데이터 폴더 (기본: <book>/_rounds)")
    ap.add_argument("--round", default=None, help="특정 회차코드만 (예: m01)")
    ap.add_argument("--dry-run", action="store_true", help="파일 쓰지 않고 계획만 출력")
    args = ap.parse_args()

    book = Path(args.book).resolve()
    rounds_dir = Path(args.rounds_dir).resolve() if args.rounds_dir else (book / "_rounds")
    if not rounds_dir.exists():
        print(f"회차 데이터 폴더가 없습니다: {rounds_dir}", file=sys.stderr)
        return 2

    files = sorted(rounds_dir.glob("m*.json"))
    if args.round:
        files = [f for f in files if f.stem == args.round]
    if not files:
        print(f"처리할 회차 데이터가 없습니다: {rounds_dir} (round={args.round})", file=sys.stderr)
        return 2

    all_items: list[dict] = []
    for f in files:
        all_items.extend(process_round(f, book, args.dry_run))
    regenerate_index_stats(book, all_items, args.dry_run)
    print("완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
