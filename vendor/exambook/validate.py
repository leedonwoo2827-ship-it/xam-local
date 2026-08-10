#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exam-forge validate helper.

회차 데이터(rounds/mNN.json)의 스키마·품질을 점검한다. build 전에 실행 권장.
표준 라이브러리만 사용. Python 3.11+.

점검 항목:
  - 필수 필드 존재(question_no, subject, subject_no, difficulty, tags, derived_from,
    question, choices, answer_index, explanation)
  - choices 정확히 4개, answer_index 0~3
  - question_no 1..N 연속·유일
  - subject_no 1..K 연속(정수), difficulty ∈ {상,중,하}, tags 1개 이상
  - 과목 비율(SQLD 10/40 등) 및 난이도/정답 분포 리포트(경고 수준)

사용 예:
  python validate.py --rounds-dir D:/00work/ocr-output-260723/_rounds
  python validate.py --rounds-dir ./rounds --round m01
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# 콘솔 인코딩(cp949 등)에서 한글/기호 출력 시 크래시 방지
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

DIFF = {"상", "중", "하"}
REQUIRED = ["question_no", "subject", "subject_no", "difficulty", "tags",
            "derived_from", "question", "choices", "answer_index", "explanation"]


def check_round(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"{path.name}: JSON 파싱 실패 — {e}"], []

    code = data.get("round_code", path.stem)
    for k in ("round_code", "round", "round_label", "questions"):
        if k not in data:
            errors.append(f"{code}: 루트 필드 누락 '{k}'")
    qs = data.get("questions", [])
    if not qs:
        errors.append(f"{code}: questions 비어있음")
        return errors, warns

    nos = []
    ans = Counter()
    diffc = Counter()
    subjc = Counter()
    for i, q in enumerate(qs):
        tag = f"{code} #{q.get('question_no', f'idx{i}')}"
        for f in REQUIRED:
            if f not in q:
                errors.append(f"{tag}: 필드 누락 '{f}'")
        ch = q.get("choices", [])
        if len(ch) != 4:
            errors.append(f"{tag}: choices 개수 {len(ch)} (4개여야 함)")
        ai = q.get("answer_index")
        if not isinstance(ai, int) or not (0 <= ai < 4):
            errors.append(f"{tag}: answer_index 잘못됨 ({ai})")
        else:
            ans[["①", "②", "③", "④"][ai]] += 1
        if q.get("difficulty") not in DIFF:
            errors.append(f"{tag}: difficulty 잘못됨 ({q.get('difficulty')})")
        else:
            diffc[q["difficulty"]] += 1
        sn = q.get("subject_no")
        if not isinstance(sn, int) or sn < 1:
            errors.append(f"{tag}: subject_no 잘못됨 ({sn}) — 1 이상의 정수여야 함")
        else:
            subjc[q.get("subject", "?")] += 1
        if not q.get("tags"):
            warns.append(f"{tag}: tags 비어있음")
        if not q.get("derived_from"):
            warns.append(f"{tag}: derived_from 비어있음")
        nos.append(q.get("question_no"))

    n = len(qs)
    expected = list(range(1, n + 1))
    if sorted(x for x in nos if isinstance(x, int)) != expected:
        errors.append(f"{code}: question_no가 1..{n} 연속·유일이 아님 ({sorted(nos)})")

    # subject_no 는 1..K 연속이어야 한다(웹 성적표·이론 링크의 축 — exam-web-contract.md §1)
    sns = sorted({q["subject_no"] for q in qs if isinstance(q.get("subject_no"), int)})
    if sns and sns != list(range(1, len(sns) + 1)):
        errors.append(f"{code}: subject_no가 1..{len(sns)} 연속이 아님 ({sns})")

    # 분포 경고(품질 가이드; 실패 아님)
    s1 = subjc.get("데이터 모델링의 이해", 0)
    s2 = subjc.get("SQL 기본 및 활용", 0)
    if n == 50 and (s1, s2) != (10, 40):
        warns.append(f"{code}: 과목 비율 {s1}:{s2} (권장 10:40)")
    # ★ 정답 분포 기준을 **문항 수에 비례**해 잡는다.
    #
    #   예전에는 8~17 이 하드코딩이었다. 50문항(각 12.5 기대)용 값이라 80문항 책에서는
    #   각 20 이 기대인데도 17 을 넘어 **항상** 경고가 떴다. 항상 뜨는 경고는 읽지 않게
    #   되고, 그러면 정말 편중된 회차도 같이 지나간다 — 경고가 무의미해지는 쪽이 문제다.
    #   기대치 n/4 에 ±36% 를 둔다(50문항이면 8~17 로 기존과 같고, 80문항이면 13~27).
    if ans:
        lo, hi = round(n / 4 * 0.64), round(n / 4 * 1.36)
        if any(v > hi or v < lo for v in ans.values()):
            warns.append(f"{code}: 정답 분포 편중 {dict(ans)} (각 {lo}~{hi} 권장)")
    print(f"[{code}] {n}문항 · 난이도 {dict(diffc)} · 정답 {dict(ans)} · 과목 {dict(subjc)}")
    return errors, warns


def main() -> int:
    ap = argparse.ArgumentParser(description="exam-forge validate helper")
    ap.add_argument("--rounds-dir", required=True, help="회차 데이터 폴더")
    ap.add_argument("--round", default=None, help="특정 회차코드만 (예: m01)")
    args = ap.parse_args()

    rd = Path(args.rounds_dir).resolve()
    files = sorted(rd.glob("m*.json"))
    if args.round:
        files = [f for f in files if f.stem == args.round]
    if not files:
        print(f"검증할 회차 데이터가 없습니다: {rd}", file=sys.stderr)
        return 2

    all_err: list[str] = []
    all_warn: list[str] = []
    for f in files:
        e, w = check_round(f)
        all_err += e
        all_warn += w

    for w in all_warn:
        print(f"  [warn] {w}")
    for e in all_err:
        print(f"  [error] {e}", file=sys.stderr)
    if all_err:
        print(f"\n검증 실패: 오류 {len(all_err)}건, 경고 {len(all_warn)}건", file=sys.stderr)
        return 1
    print(f"\n검증 통과 (경고 {len(all_warn)}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
