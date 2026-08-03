"""02/_index.json · 02/difficulty_stats.json 재생성.

실측한 형식 (byte 단위로 확인함):
  · json.dumps(indent=2, ensure_ascii=False), **끝에 개행 없음**
  · _index.json  = {"count": 240, "items": [...]}, item 키 16개 순서 고정
  · difficulty_stats.json = {"total", "overall", "by_round"}
  · overall.difficulty / overall.subject 의 키 순서는 **첫 등장 순서**다
    (정렬이 아니다 — m01-01 이 '하', m01-02 가 '상' 이라서 하·상·중 순으로 나온다)
  · by_round 의 키는 **문자열** "1" "2" "3"
  · by_round[N] 에는 with_figure · with_sql 이 있고 overall 에는 없다
  · _index.json 의 path 는 BOOK 상대경로("02/m01-01.md") — 폴더 상대가 아니다

관측된 특이점은 정규화하지 않고 그대로 재현한다. 이 파일들은 axexam 의
exam_meta.py 가 읽는 입력이고, 우리가 '더 깔끔하게' 바꾸면 저쪽이 깨진다.
"""
from __future__ import annotations

import os

from core.atomic_io import atomic_write_text, backup_sibling
from services.book import derive, jsonio, md, paths, rounds

# _index.json 의 item 키 순서 — 실측값.
ITEM_ORDER = (
    "id", "round", "subject", "subject_no", "question_no",
    "answer", "answer_index", "difficulty", "tags", "derived_from",
    "has_figure", "has_sql", "has_table", "reviewed", "n_choices", "path",
)


def _first_appearance(values) -> list:
    """첫 등장 순서로 중복을 제거한다. 원본 생성기가 쓴 순서 규칙."""
    out = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def _count_in_order(pairs, order) -> dict:
    """order 순서대로 키를 배치한 카운트 dict."""
    agg = {k: 0 for k in order}
    for v in pairs:
        if v in agg:
            agg[v] += 1
    return agg


def build_item(round_code: str, round_meta: dict, question: dict, flags: dict) -> dict:
    """문항 하나 → _index.json 의 item."""
    round_no = int(round_meta["round"])
    qno = int(question["question_no"])
    qid = paths.qid(round_no, qno)
    return {
        "id": qid,
        "round": round_no,                       # ★ int 여야 한다 — exam_meta.py 가
                                                 #   isinstance(rn, int) 로 걸러 회차를 집계한다
        "subject": question["subject"],
        "subject_no": int(question["subject_no"]),
        "question_no": qno,
        "answer": derive.answer_glyph(question["answer_index"]),
        "answer_index": int(question["answer_index"]),
        "difficulty": question["difficulty"],
        "tags": list(question.get("tags") or []),
        "derived_from": question.get("derived_from") or "",
        "has_figure": derive.has_figure(question),
        "has_sql": bool(flags.get("has_sql", False)),
        "has_table": bool(flags.get("has_table", False)),
        "reviewed": bool(flags.get("reviewed", False)),
        "n_choices": derive.n_choices(question),
        "path": f"02/{qid}.md",                  # BOOK 상대경로
    }


def collect(with_flags: bool = True) -> list[dict]:
    """모든 문항의 item 을 회차·번호 순으로 모은다.

    with_flags=True 면 기존 md 에서 has_sql / has_table / reviewed 를 읽어 보존한다
    (그 세 값은 _rounds 에 없다).
    """
    items = []
    for rc, meta, q in rounds.all_questions():
        qid = paths.qid(int(meta["round"]), int(q["question_no"]))
        flags = md.flags_for(q, paths.q_md(qid)) if with_flags else {}
        items.append(build_item(rc, meta, q, flags))
    return items


def build_index(items: list[dict]) -> dict:
    return {"count": len(items), "items": items}


# ── 목록 화면용 조회 ────────────────────────────────────────────────────────
_CACHE: dict = {"key": None, "items": None}


def _cache_key() -> tuple:
    """_rounds 3개 + 02 색인의 mtime/size. 하나라도 바뀌면 다시 모은다."""
    parts = [paths.etag(paths.rounds_json(rc)) for rc in paths.round_codes()]
    parts.append(paths.etag(paths.q_index()))
    return tuple(parts)


def cached_items(force: bool = False) -> list[dict]:
    """240문항 item 캐시. 목록·필터·사전점검이 전부 이걸 쓴다.

    240개마다 md 를 열어 플래그를 읽으므로(240 파일 open) 매 요청 재수집은 낭비다.
    BOOK 이 외부에서 바뀌면 캐시 키가 달라져 자동으로 무효화된다.
    """
    key = _cache_key()
    if force or _CACHE["key"] != key or _CACHE["items"] is None:
        _CACHE["items"] = collect()
        _CACHE["key"] = key
    return _CACHE["items"]


def invalidate() -> None:
    _CACHE["key"] = None


def query(*, round_code: str = "", subject: str = "", difficulty: str = "",
          unreviewed: bool = False, has_figure: bool | None = None,
          q: str = "", limit: int = 0, offset: int = 0) -> dict:
    """목록 화면의 필터. 검수 상태는 02/*.md 가 원천이다."""
    items = cached_items()
    total = len(items)
    rows = items

    if round_code:
        rn = paths.parse_round_code(round_code)
        if rn is not None:
            rows = [r for r in rows if r["round"] == rn]
    if subject:
        rows = [r for r in rows if r["subject"] == subject]
    if difficulty:
        rows = [r for r in rows if r["difficulty"] == difficulty]
    if unreviewed:
        rows = [r for r in rows if not r["reviewed"]]
    if has_figure is not None:
        rows = [r for r in rows if r["has_figure"] is bool(has_figure)]
    if q:
        needle = q.strip().lower()
        if needle:
            rows = [r for r in rows if needle in r["id"].lower()
                    or needle in r["subject"].lower()
                    or any(needle in t.lower() for t in r["tags"])]

    filtered = len(rows)
    if offset:
        rows = rows[offset:]
    if limit:
        rows = rows[:limit]

    return {
        "total": total,
        "filtered": filtered,
        "count": len(rows),
        "reviewed": sum(1 for i in items if i["reviewed"]),
        "items": [dict(r, bundle=paths.bundle_of(r["round"], r["question_no"])) for r in rows],
        "facets": {
            "rounds": _first_appearance(i["round"] for i in items),
            "subjects": _first_appearance(i["subject"] for i in items),
            "difficulties": _first_appearance(i["difficulty"] for i in items),
        },
    }


def next_unreviewed(after: str = "") -> str | None:
    """다음 미검수 문항 id. after 가 주어지면 그 뒤부터 찾고, 없으면 처음으로 돈다."""
    items = cached_items()
    ids = [i["id"] for i in items if not i["reviewed"]]
    if not ids:
        return None
    if after:
        later = [i for i in ids if i > after]
        if later:
            return later[0]
    return ids[0]


def build_stats(items: list[dict]) -> dict:
    """difficulty_stats.json — 첫 등장 순서를 지킨다."""
    diff_order = _first_appearance(i["difficulty"] for i in items)
    subj_order = _first_appearance(i["subject"] for i in items)
    # ★ 정답 분포도 **첫 등장 순서**다. 업로드본은 ①②③④ 고정으로 봤는데
    #   (`target_index=(qno-1)%4` 라는 생성기 규칙을 가정했다) 실측은 그렇지 않다:
    #   260730 의 difficulty_stats.json 은 ④(60) 부터 시작한다 = m01-01 의 정답.
    #   고정 순서로 내면 이 파일 하나가 매번 어긋난다.
    ans_order = _first_appearance(i["answer"] for i in items)

    overall = {
        "difficulty": _count_in_order((i["difficulty"] for i in items), diff_order),
        "subject": _count_in_order((i["subject"] for i in items), subj_order),
        "answer": _count_in_order((i["answer"] for i in items), ans_order),
    }

    by_round: dict[str, dict] = {}
    for rn in _first_appearance(i["round"] for i in items):
        rows = [i for i in items if i["round"] == rn]
        # ★ by_round 의 키 순서는 그 회차 안의 첫 등장 순서다 — 전체 순서가 아니다.
        #   실측: m01 하·상·중 / m02 중·하·상 / m03 하·중·상. 전체 순서를 쓰면
        #   m02·m03 의 difficulty 블록이 원본과 달라진다.
        by_round[str(rn)] = {                     # ★ 키는 문자열
            "count": len(rows),
            "difficulty": _count_in_order(
                (r["difficulty"] for r in rows),
                _first_appearance(r["difficulty"] for r in rows)),
            "subject": _count_in_order(
                (r["subject"] for r in rows),
                _first_appearance(r["subject"] for r in rows)),
            "with_figure": sum(1 for r in rows if r["has_figure"]),
            "with_sql": sum(1 for r in rows if r["has_sql"]),
        }

    return {"total": len(items), "overall": overall, "by_round": by_round}


def render_index(items: list[dict]) -> str:
    """02/_index.json 전문 — 서식은 그 파일에서 되맞춘다(jsonio)."""
    return jsonio.render(paths.q_index(), build_index(items))


def render_stats(items: list[dict]) -> str:
    return jsonio.render(paths.q_stats(), build_stats(items))


def write(items: list[dict] | None = None) -> dict:
    """_index.json · difficulty_stats.json 을 다시 쓴다.

    ★ md 는 다시 쓰지 않는다. 240개를 통째로 재생성하는 경로는 이 앱에 없다 —
      md 는 편집한 문항 하나만 쓴다(store.py).

    내용이 실제로 바뀐 파일만 쓴다. 안 바뀐 파일의 mtime 을 흔들면 axexam 의
    `stats_fresh` 류 신선도 검사가 헛돌고, 사람도 무엇이 바뀐 건지 못 본다.
    """
    if items is None:
        items = collect()

    changed = {}
    for path, text in ((paths.q_index(), render_index(items)),
                       (paths.q_stats(), render_stats(items))):
        cur = None
        if os.path.isfile(path):
            with open(path, encoding="utf-8", newline="") as f:
                cur = f.read()
        if cur == text:
            changed[os.path.basename(path)] = False
            continue
        backup_sibling(path)
        atomic_write_text(path, text)
        changed[os.path.basename(path)] = True

    invalidate()
    return {"count": len(items), "changed": changed}
