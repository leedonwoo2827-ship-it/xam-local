#!/usr/bin/env python3
"""코드가 참조하는 DB 컬럼이 스키마에 실제로 있는지 검사한다.

왜 필요한가
  php -l 은 문법만 본다. `edited_by = '...'` 처럼 **없는 컬럼**을 쓰는 것은
  런타임에 "Unknown column" 으로 터지고, 그누보드 코어가 없는 로컬에서는 재현되지 않는다.
  실제로 이 검사로 ex_qna.edited_by 누락을 잡았다.

사용
  python scripts/check_columns.py

한계 (일부러 느슨하게 만들었다)
  · 정규식 기반이다. SQL 을 파싱하지 않는다
  · 컬럼 접두어(qa_ · lot_ · od_ …)로 테이블을 추정한다. 접두어가 없는 컬럼(mb_id 등)은 건너뛴다
  · 오탐이 있으면 아래 IGNORE 에 넣는다. **미탐보다 오탐이 낫다**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 윈도우 콘솔 기본 코드페이지(cp949)가 '—' 같은 문자를 못 쓴다.
# 검사기가 결과를 못 찍고 죽으면 검사기가 없는 것과 같다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SQL = [ROOT / "web/exam/sql/schema.sql", ROOT / "web/exam/sql/migrate-001-multipd.sql"]
SRC_DIRS = [ROOT / "web", ROOT / "_probe"]

# 실측한 오탐 목록. 컬럼처럼 생겼지만 컬럼이 아닌 것들이다.
IGNORE = {
    "pd_config",            # 실제로 있다. TEXT NULL 이라 아래 타입 정규식이 놓친다
    "lo_act", "lo_ref", "lo_ip",
    "has_draft",            # SQL 별칭: `qa_draft is not null as has_draft`
    "lo_location", "lo_url",        # 그누보드 내부 $g5[...]
}
# JSON 출력 키라서 컬럼이 아닌 이름 (ex_qna_row() 등이 만드는 응답 필드)
IGNORE |= {"answer", "answered_at", "question", "chosen", "status", "refunded",
           "wrong", "correct", "total", "skipped"}   # 성적표 집계 배열의 키

# ★ 접두어 단위 제외 — **그누보드 코어 테이블**의 컬럼이다.
#   ex_qna 에 bo_table · wr_id 를 넣은 순간 'bo_' · 'wr_' 접두어가 ex_qna 로 추정돼
#   g5_board.bo_category_list · g5_write_*.wr_subject 같은 코어 컬럼이 전부 오탐이 됐다.
#   우리 스키마에는 이 접두어로 시작하는 '우리 것'이 그 둘뿐이므로 접두어를 통째로 뺀다.
IGNORE_PREFIX = {"bo_", "wr_", "mb_", "cf_", "g5_", "od_v", "sca"}

TYPE = r"(VARCHAR|INT|TINYINT|SMALLINT|BIGINT|CHAR|TEXT|MEDIUMTEXT|LONGTEXT|DATETIME|DATE|TIME|DECIMAL|FLOAT|DOUBLE|BLOB|ENUM)"


def load_schema() -> dict[str, set[str]]:
    cols: dict[str, set[str]] = {}
    for path in SQL:
        if not path.exists():
            continue
        sql = path.read_text(encoding="utf-8")

        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\)", sql, re.S):
            tbl, body = m.group(1), m.group(2)
            cols.setdefault(tbl, set())
            for line in body.splitlines():
                cm = re.match(rf"^\s+([a-z_]+)\s+{TYPE}\b", line, re.I)
                if cm:
                    cols[tbl].add(cm.group(1))

        # 마이그레이션이 추가하는 컬럼
        for m in re.finditer(r"ALTER TABLE (\w+)\s+ADD COLUMN IF NOT EXISTS (\w+)", sql, re.I):
            cols.setdefault(m.group(1), set()).add(m.group(2))
    return cols


def main() -> int:
    cols = load_schema()
    if not cols:
        print("스키마를 읽지 못했습니다.", file=sys.stderr)
        return 2

    # 컬럼 접두어 → 테이블. 'qa_' → ex_qna 처럼 유일할 때만 쓴다.
    pref_to_tbl: dict[str, set[str]] = {}
    for tbl, cs in cols.items():
        for c in cs:
            if "_" in c:
                pref_to_tbl.setdefault(c.split("_")[0] + "_", set()).add(tbl)
    unique_pref = {p: next(iter(t)) for p, t in pref_to_tbl.items() if len(t) == 1}

    files: list[Path] = []
    for d in SRC_DIRS:
        if d.is_dir():
            files.extend(sorted(d.rglob("*.php")))

    findings: list[tuple[str, int, str, str]] = []
    for f in files:
        src = f.read_text(encoding="utf-8", errors="replace")
        rel = f.relative_to(ROOT).as_posix()
        for i, line in enumerate(src.splitlines(), 1):
            # $row['col'] 참조와  col = / col, 형태의 SQL 컬럼 사용
            for m in re.finditer(r"\['([a-z][a-z0-9_]{2,})'\]|(?<![\w.$'\"])([a-z]+_[a-z0-9_]+)\s*=", line):
                c = m.group(1) or m.group(2)
                if not c or c in IGNORE:
                    continue
                if any(c.startswith(p) for p in IGNORE_PREFIX):
                    continue
                pref = c.split("_")[0] + "_"
                tbl = unique_pref.get(pref)
                if tbl and c not in cols[tbl]:
                    findings.append((rel, i, tbl, c))

    # 같은 (테이블, 컬럼) 은 첫 발견만 보고한다
    seen: set[tuple[str, str]] = set()
    uniq = []
    for rel, ln, tbl, c in findings:
        if (tbl, c) in seen:
            continue
        seen.add((tbl, c))
        uniq.append((rel, ln, tbl, c))

    if uniq:
        print("스키마에 없는 컬럼을 쓰고 있습니다:")
        for rel, ln, tbl, c in uniq:
            print(f"  {tbl}.{c}")
            print(f"      {rel}:{ln}")
        print()
        print(f"의심 {len(uniq)}건 — 오탐이면 scripts/check_columns.py 의 IGNORE 에 넣습니다.")
        return 1

    print(f"컬럼 참조 OK · 테이블 {len(cols)}개 · 파일 {len(files)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
