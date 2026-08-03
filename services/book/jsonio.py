"""BOOK 트리의 JSON 을 **그 파일이 쓰던 형식 그대로** 다시 쓴다.

★ 여기가 왜 있는가 (2026-08-03, 첫 왕복 검증에서 드러남)

업로드본은 BOOK 안 JSON 을 전부 `indent=2` · LF · 끝개행 없음으로 봤다.
이 PC 의 실측은 그렇지 않다:

    260730  _rounds/*.json                  indent=1  LF
    260730  02/_index.json · stats          indent=2  CRLF
    260730  04/lesson_*.json · 05/lesson    indent=2  CRLF
    260723  _rounds/m01~m03.json            indent=2  CRLF
    260723  _rounds/m04.json                indent=2  LF     ← 같은 폴더 안에서 갈린다

`_rounds` 를 indent=2 로 쓰면 111KB 원천 파일이 118KB 로 통째로 재작성된다.
문항 하나를 고쳤을 뿐인데 80문항의 서식이 전부 바뀌고, `.bak` 하나로는 어느 것이
사람의 수정이었는지 분간할 수 없게 된다.

그래서 형식을 상수로 두지 않고 **파일에서 되맞춰(probe) 본다** — 후보 조합으로
직렬화해 원본과 바이트가 같은 것을 고른다. 감지가 곧 자기검증이라서, 못 맞추면
못 맞췄다고 말한다(그때는 저장을 막는 게 옳다).

파일이 없을 때(새 회차 m04~m09)는 같은 폴더 형제의 형식을 따른다.
"""
from __future__ import annotations

import json
import os

from core.atomic_io import CRLF, LF

# 후보 조합 — 실측에 나온 것부터. 먼저 맞는 것을 쓴다.
_INDENTS = (2, 1, 4, 3, None)
_TRAILING = (False, True)
# 한 줄로 붙여 쓰는 배열 키. 실측: 260723 의 _rounds/m05·m06 이
#   "tags": ["엔터티 분류", "행위 엔터티"]   ← indent=2 인데 이 배열만 인라인
# 이다. 같은 폴더의 m04 는 블록이다. json.dumps 로는 낼 수 없는 형식이라
# 후보로 두고 되맞춘다. () 가 먼저다 — 대부분은 표준 dumps 로 맞는다.
#   · 260723 m01·m04  → tags 는 블록 (표준 dumps)
#   · 260723 m05·m06  → tags 인라인, choices 는 블록, table.columns 와 table.rows 의
#                        각 행도 인라인. 같은 폴더 안에서 갈린다.
_INLINE_KEYS = ((), ("tags",), ("tags", "columns", "rows"),
                ("tags", "choices"), ("choices",),
                ("columns", "rows"), ("assets",), ("source_pages",))

# 폭 기준으로 접는 writer 도 섞여 있다. 260723 m06 은 같은 `rows` 키가 짧으면
#   "rows": [["C1"], ["C1"], ["C2"]]          ← 한 줄
# 길면 블록이다. 키가 아니라 **한 줄로 폈을 때의 길이**가 기준이라서 키 목록으로는
# 표현할 수 없다. 흔한 최대폭을 후보로 둔다.
_WIDTHS = (None, 80, 79, 88, 100, 72, 120)

DEFAULT = (2, False, LF, (), None)

# etag 캐시 — 왕복 검증이 24개 lesson 을 돌 때마다 되맞추지 않게.
_CACHE: dict[str, tuple] = {}


def _scalar(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def _is_flat_list(v) -> bool:
    return isinstance(v, list) and not any(isinstance(x, (dict, list)) for x in v)


def _dump(obj, indent: int, depth: int, col: int, inline_keys: tuple,
          width: int | None, inline_self: bool = False) -> str:
    """json.dumps(indent=…) 와 같은 형식 + inline_keys 값만 조건부로 한 줄.

    표준 dumps 의 형식을 그대로 따라야 한다 — 들여쓰기 폭, `": "` 구분자,
    빈 컨테이너 `{}`/`[]`, 항목 사이 `,\\n`.

    한 줄로 두는 조건 (실측에서 되맞춘 규칙):
      · width 가 없으면 — inline_keys 의 **평면 배열**만 한 줄.
      · width 가 있으면 — inline_keys 의 값을 한 줄로 폈을 때 `col + 길이` 가
        width 안에 들어갈 때만 한 줄. 안 들어가면 블록으로 펴고, 그 자식들에게
        같은 판정을 물려준다.

    ★ 마지막 규칙이 260723 m06 을 설명한다. 같은 `rows` 키가
        "rows": [["C1"], ["C1"], ["C2"], ["C3"], ["C3"], ["C3"]]     ← 짧아서 한 줄
      이고, 열이 3개인 다른 표에서는 바깥이 블록 + 각 행만 한 줄이다.
      반면 `choices` 는 짧아도 항상 블록이다 — 그래서 폭만으로는 설명이 안 되고
      키 목록과 폭을 **함께** 봐야 한다.
    """
    if not isinstance(obj, (dict, list)):
        return _scalar(obj)

    one = json.dumps(obj, ensure_ascii=False)
    if inline_self:
        if width is None:
            if _is_flat_list(obj):
                return one
        elif col + len(one) <= width:
            return one

    pad = " " * (indent * (depth + 1))
    cpad = " " * (indent * depth)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        parts = []
        for k, v in obj.items():
            head = f"{_scalar(str(k))}: "
            parts.append(pad + head + _dump(v, indent, depth + 1,
                                            len(pad) + len(head), inline_keys,
                                            width, k in inline_keys))
        return "{\n" + ",\n".join(parts) + "\n" + cpad + "}"
    if not obj:
        return "[]"
    parts = [pad + _dump(x, indent, depth + 1, len(pad), inline_keys, width,
                         inline_self) for x in obj]
    return "[\n" + ",\n".join(parts) + "\n" + cpad + "]"


def dumps(data, indent, trailing_newline: bool, newline: str,
          inline_keys: tuple = (), width: int | None = None) -> str:
    if inline_keys and indent:
        text = _dump(data, indent, 0, 0, inline_keys, width)
    else:
        text = json.dumps(data, ensure_ascii=False, indent=indent)
    if trailing_newline:
        text += "\n"
    return text if newline == LF else text.replace("\n", newline)


def detect(path: str) -> tuple | None:
    """이 파일을 바이트 그대로 재현하는 (indent, trailing_newline, newline).

    되맞추지 못하면 None — 우리가 모르는 형식이라는 뜻이고, 그건 조용히 넘기면
    안 되는 사실이다(호출자가 검증 실패로 올린다).
    """
    from services.book import paths
    key = f"{path}|{paths.etag(path)}"
    if key in _CACHE:
        return _CACHE[key]
    try:
        with open(path, encoding="utf-8", newline="") as f:
            raw = f.read()
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None

    newline = CRLF if CRLF in raw else LF
    for width in _WIDTHS:
        for inline in _INLINE_KEYS:
            for indent in _INDENTS:
                for trailing in _TRAILING:
                    if dumps(data, indent, trailing, newline, inline, width) == raw:
                        _CACHE[key] = (indent, trailing, newline, inline, width)
                        return _CACHE[key]
    return None


def format_for(path: str) -> tuple:
    """이 경로에 써야 하는 형식.

    1) 파일이 있고 되맞춰지면 그 형식.
    2) 없으면 같은 폴더 · 같은 확장자 형제 중 처음 되맞춰지는 것의 형식.
       ★ 새 회차 파일이 형제와 다른 서식으로 태어나면 한 폴더에 두 규약이 섞인다.
    3) 형제도 없으면 DEFAULT.
    """
    got = detect(path)
    if got:
        return got

    d, name = os.path.dirname(path), os.path.basename(path)
    try:
        siblings = sorted(os.listdir(d))
    except OSError:
        return DEFAULT
    for f in siblings:
        if f == name or not f.endswith(".json") or f.endswith(".bak"):
            continue
        got = detect(os.path.join(d, f))
        if got:
            return got
    return DEFAULT


def render(path: str, data) -> str:
    """data → 그 파일에 실제로 들어갈 문자열(개행·indent·끝개행·인라인배열 포함)."""
    return dumps(data, *format_for(path))


def roundtrip(path: str) -> dict:
    """이 파일을 읽어 그대로 다시 찍었을 때 바이트가 같은가 — 왕복 검증용."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            raw = f.read()
    except OSError as e:
        return {"ok": False, "error": f"읽을 수 없습니다: {e}"}
    try:
        data = json.loads(raw.replace(CRLF, LF))
    except ValueError as e:
        return {"ok": False, "error": f"JSON 이 아닙니다: {e}"}
    fmt = detect(path)
    if not fmt:
        return {"ok": False, "error": (
            "이 파일을 만든 JSON writer 의 서식을 되맞추지 못했습니다 "
            "(indent · 개행 · 끝개행 · 인라인 배열 · 최대폭 조합이 후보에 없음). "
            "이 회차를 저장하면 파일 전체의 서식이 바뀝니다 — 그래서 막았습니다. "
            "후보를 늘리려면 services/book/jsonio.py 의 _INLINE_KEYS · _WIDTHS 를 보세요.")}
    text = dumps(data, *fmt)
    if text == raw:
        return {"ok": True, "indent": fmt[0], "trailing_newline": fmt[1],
                "newline": "CRLF" if fmt[2] == CRLF else "LF",
                "inline_keys": list(fmt[3]), "width": fmt[4]}
    return {"ok": False, "error": "되맞춘 서식으로도 바이트가 다릅니다.",
            "bytes_expected": len(raw.encode("utf-8")),
            "bytes_rendered": len(text.encode("utf-8"))}
