"""02/ 원본 메타 로더 — 문제의 진짜 과목·검수상태가 사는 유일한 곳.

왜 필요한가
-----------
05 의 lesson JSON 블록에는 `subject` 키가 **아예 없다**(실측: `b.get('subject')` → None).
그래서 build_check.py 의 `b.get("subject") or subj` 가 lesson 파일 최상위의
`subject: "SQLD"` 로 폴백해 300문제 전부를 "SQLD" 로 채웠고, 화면 과목 필터에
선택지가 하나뿐이었다.

진짜 과목은 `02/_index.json` 에 있다 — **데이터 모델링의 이해 60 / SQL 기본 및 활용 240**.
`verified` / `needs_review` / `authored_by` / `round_label` 은 `_index.json` 에 없고
`02/m*.md` 의 YAML frontmatter 에만 있어서 둘을 합쳐야 한다.

조인 키
-------
    src_id = f"m{round:02d}-{number:02d}"      # 'm01-07'

lesson 번들 `m01-1` 의 블록 `number` 1..10 과 `_index.json` 의 `id` 가 이 규칙으로
정확히 맞는다. 300/300 무손실 매칭이 확인됐다.

사용:
    from exam_meta import load_meta, load_rounds
    META = load_meta(Path("D:/00work/ocr-output-260723"))
    META["m01-07"]["subject"]   # '데이터 모델링의 이해'
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml  # pyyaml>=6.0 — requirements.txt 에 이미 있다

# .md frontmatter 에서 읽는 것들.
#
# `round`·`question_no` 는 `_index.json` 에도 있지만 여기에 함께 둔다 —
# `_index.json` 이 없는 문제집(집필 앱이 아직 안 만든 경우)에서도
# `load_rounds()`·`load_subjects()` 가 서야 한다. 없으면 회차 라벨이
# '1회' 로 떨어져 화면에 그대로 노출된다. 값이 겹칠 때는 .md 가 이긴다.
_MD_ONLY = ("subject", "subject_no", "verified", "reviewed", "needs_review",
            "authored_by", "round", "round_label", "question_no",
            "difficulty", "answer", "answer_index",
            "n_choices", "derived_from", "tags")


def load_meta(book: Path) -> dict[str, dict]:
    """'m01-07' → {subject, subject_no, verified, reviewed, needs_review, ...}

    `_index.json` 을 바탕으로 깔고 `.md` frontmatter 로 덮어쓴다.
    .md 가 더 최신이고 `verified`/`needs_review`/`round_label` 을 가진 유일한 소스다.
    """
    out: dict[str, dict] = {}

    idx_path = book / "02" / "_index.json"
    if idx_path.exists():
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        for it in idx.get("items") or []:
            if it.get("id"):
                out[it["id"]] = dict(it)

    for md in sorted((book / "02").glob("m*.md")):
        parts = md.read_text(encoding="utf-8").split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            continue
        mid = fm.get("id")
        if not mid:
            continue
        row = out.setdefault(mid, {"id": mid})
        for k in _MD_ONLY:
            if k in fm:
                row[k] = fm[k]
        row.setdefault("path", f"02/{md.name}")

    return out


# 회차 라벨에서 걷어낼 접두어.
# `02/` 원본에는 '자사 모의고사 01회' 로 들어 있는데 노출 문구에서 '자사'를 빼기로 했다.
# 원본(02/)을 고치지 않고 여기서 정규화하는 이유: 원본은 제작 파이프라인의 산물이고
# 표기 규칙은 서비스 쪽 결정이라 서로 다른 속도로 바뀐다.
LABEL_STRIP = ("자사 ",)


def _clean_label(s: str) -> str:
    s = str(s or "").strip()
    for p in LABEL_STRIP:
        if s.startswith(p):
            s = s[len(p):].lstrip()
    return s


def load_rounds(meta: dict[str, dict]) -> list[dict]:
    """회차 목록 → [{'rd_no':1, 'rd_label':'모의고사 01회', 'rd_count':50}, ...]

    `rd_label` 은 `.md` frontmatter 의 `round_label` 에서만 나온다.
    없으면 'N회' 로 폴백하고, `LABEL_STRIP` 접두어는 걷어낸다.
    """
    agg: dict[int, dict] = {}
    for m in meta.values():
        rn = m.get("round")
        if not isinstance(rn, int):
            continue
        r = agg.setdefault(rn, {"rd_no": rn, "rd_label": "", "rd_count": 0})
        r["rd_count"] += 1
        if not r["rd_label"] and m.get("round_label"):
            r["rd_label"] = _clean_label(m["round_label"])
    for rn, r in agg.items():
        if not r["rd_label"]:
            r["rd_label"] = f"{rn}회"
    return [agg[k] for k in sorted(agg)]


def load_subjects(meta: dict[str, dict]) -> list[dict]:
    """과목 목록 → [{'sj_no':1,'sj_name':'데이터 모델링의 이해'}, ...] (sj_no 오름차순)"""
    agg: dict[int, str] = {}
    for m in meta.values():
        no, name = m.get("subject_no"), m.get("subject")
        if isinstance(no, int) and name:
            agg.setdefault(no, str(name))
    return [{"sj_no": k, "sj_name": agg[k]} for k in sorted(agg)]


def src_id(round_num: int, number) -> str:
    """(1, 7) → 'm01-07'. lesson 블록과 02/ 를 잇는 조인 키."""
    return f"m{int(round_num):02d}-{int(number):02d}"


if __name__ == "__main__":  # 자체 점검: python scripts/exam_meta.py
    import collections
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    book = Path(sys.argv[1] if len(sys.argv) > 1 else "D:/00work/ocr-output-260723")
    meta = load_meta(book)
    print(f"[meta] {len(meta)}건  ({book})")
    print("  과목:", dict(collections.Counter(m.get("subject") for m in meta.values())))
    print("  verified:", dict(collections.Counter(m.get("verified") for m in meta.values())))
    print("  needs_review:", dict(collections.Counter(m.get("needs_review") for m in meta.values())))
    for r in load_rounds(meta):
        print(f"  회차 {r['rd_no']}: {r['rd_label']} · {r['rd_count']}문제")
    print("  subjects:", load_subjects(meta))
