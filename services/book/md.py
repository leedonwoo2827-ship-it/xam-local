"""02/mNN-KK.md 렌더러 · 파서 — 바이트 단위로 원본을 재현해야 한다.

이 240개 파일은 원격 Claude 세션에서 만들어졌고 로컬에 생성 스크립트가 없다.
렌더러가 한 글자라도 어긋나면 한 문항을 저장할 때 나머지 239개까지 조용히 바뀐다.
그래서 services/book/verify.py 의 왕복 검증(240/240 바이트 동일)을 통과하기
전에는 저장 경로를 열지 않는다.

실측한 형식 (02/m01-01.md 1095 bytes / 02/m01-02.md 1216 bytes):
  · 개행 LF 전용, BOM 없음, EOF 는 개행 하나로 끝난다
  · front matter 18키, 순서 고정
  · tags 만 인라인 flow 목록  `tags: [데이터거버넌스, 조직관리]`
  · 각 `## ` 섹션 앞에 빈 줄 하나
  · 보기는 `"① "` 접두 4줄, 사이 빈 줄 없음
  · 그림이 있으면 맨 끝에 빈 줄 하나 + `![{name} 참고 그림](assets/{name}.svg)`

PyYAML 로 덤프하지 않고 손으로 조립한다. 기본 덤퍼는 인라인 flow 목록도, 한글
무인용부호 스칼라도, 이 키 순서도 그대로 내지 못한다.
"""
from __future__ import annotations

import os
import re

import yaml

from core.constants import ANSWER_GLYPHS
from services.book import derive

# front matter 키 순서 — 이 순서가 곧 파일 형식이다. 바꾸면 240개가 전부 달라진다.
FM_ORDER = (
    "id", "round", "round_label", "subject", "subject_no", "question_no",
    "answer", "answer_index", "difficulty", "tags", "derived_from",
    "has_figure", "has_sql", "has_table",
    "authored_by", "verified", "reviewed", "needs_review",
)

# 인라인 flow 목록으로 내보낼 키. 01/ 의 source_pages 는 블록 목록이지만
# 우리가 쓰는 02/ 에는 tags 뿐이다.
FM_FLOW_LIST = ("tags",)

SECTION_QUESTION = "## 문제"
SECTION_CHOICES = "## 보기"
SECTION_EXPLAIN = "## 해설"

# YAML 무인용부호 스칼라로 낼 수 없는 값 — 조용히 깨진 YAML 을 내보내지 않기 위한 가드.
_UNSAFE_SCALAR = re.compile(r"^[\s>|@`%*&!\[\]{}#,'\"]|:\s|\s#|[\n\r\t]|\s$")


def _scalar(value: str, key: str) -> str:
    s = str(value)
    if _UNSAFE_SCALAR.search(s):
        raise ValueError(
            f"front matter 값이 YAML 무인용부호 스칼라로 안전하지 않습니다 "
            f"(key={key!r}, value={s!r}). 원본 240개는 전부 안전한 값이라 "
            f"이 오류는 입력이 잘못됐다는 뜻입니다."
        )
    return s


def _fm_line(key: str, value) -> str:
    if isinstance(value, bool):
        return f"{key}: {'true' if value else 'false'}\n"
    if isinstance(value, int):
        return f"{key}: {value}\n"
    if key in FM_FLOW_LIST:
        items = [_scalar(v, key) for v in (value or [])]
        return f"{key}: [{', '.join(items)}]\n"
    return f"{key}: {_scalar(value, key)}\n"


def front_matter(fm: dict) -> str:
    """dict → front matter 본문(구분선 제외). 누락 키는 오류로 낸다."""
    missing = [k for k in FM_ORDER if k not in fm]
    if missing:
        raise ValueError(f"front matter 키 누락: {missing}")
    return "".join(_fm_line(k, fm[k]) for k in FM_ORDER)


def build_front_matter(question: dict, round_meta: dict, flags: dict) -> dict:
    """_rounds 의 질문 + 회차 메타 + 보존 플래그 → front matter dict.

    flags 는 기존 md 에서 읽어 온 값이다 — has_sql / has_table / authored_by /
    verified / reviewed / needs_review 는 _rounds 에 없어서 보존해야 한다.
    """
    round_no = int(round_meta["round"])
    qno = int(question["question_no"])
    return {
        "id": f"m{round_no:02d}-{qno:02d}",
        "round": round_no,
        "round_label": round_meta["round_label"],
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
        "authored_by": flags.get("authored_by") or "claude",
        "verified": bool(flags.get("verified", True)),
        "reviewed": bool(flags.get("reviewed", False)),
        "needs_review": bool(flags.get("needs_review", True)),
    }


def render(question: dict, round_meta: dict, flags: dict) -> str:
    """문항 하나 → 02/mNN-KK.md 전문."""
    fm = build_front_matter(question, round_meta, flags)

    choices = question.get("choices") or []
    if len(choices) > len(ANSWER_GLYPHS):
        raise ValueError(f"보기가 너무 많습니다: {len(choices)}")

    out = ["---\n", front_matter(fm), "---\n"]
    out.append("\n" + SECTION_QUESTION + "\n")
    out.append((question.get("question") or "").strip() + "\n")
    out.append("\n" + SECTION_CHOICES + "\n")
    for i, c in enumerate(choices):
        out.append(f"{ANSWER_GLYPHS[i]} {(c or '').strip()}\n")
    out.append("\n" + SECTION_EXPLAIN + "\n")
    # ★ 그림 줄을 여기서 붙이지 않는다.
    #   실측: _rounds 의 explanation 자체가 이미 `\n\n![{name} 참고 그림](assets/…)` 로
    #   끝난다. assets[] 는 SVG 본문(파일로 쓸 내용)만 들고 있는 별개 필드다.
    #   붙이면 이미지 줄이 두 번 나온다(첫 검증에서 76문항이 이걸로 걸렸다).
    #   axexam 의 build_check.py 도 같은 전제다 —
    #   `figures = sorted(asset_field - inl_q - inl_e)` 로 인라인된 것을 빼므로
    #   이 문항들의 figures_json 은 빈 배열이고 마크다운 렌더가 그림을 그린다.
    out.append((question.get("explanation") or "").strip() + "\n")

    return "".join(out)


# ── 파서 ────────────────────────────────────────────────────────────────────
def parse(text: str) -> dict:
    """02/*.md → {"fm": dict, "question": str, "choices": [...], "explanation": str,
                  "assets": [name, ...]}

    front matter 는 PyYAML 로 읽는다(읽기는 관대해도 된다 — 쓰기만 엄격하다).
    """
    if not text.startswith("---"):
        raise ValueError("front matter 구분선(---)으로 시작하지 않습니다.")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("front matter 를 닫는 --- 를 찾지 못했습니다.")
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2]

    out = {"fm": fm, "question": "", "choices": [], "explanation": "", "assets": []}

    def section(name: str, nxt: str | None) -> str:
        i = body.find(name)
        if i < 0:
            return ""
        start = i + len(name)
        end = body.find(nxt, start) if nxt else len(body)
        if end < 0:
            end = len(body)
        return body[start:end].strip()

    out["question"] = section(SECTION_QUESTION, SECTION_CHOICES)
    raw_choices = section(SECTION_CHOICES, SECTION_EXPLAIN)
    for line in raw_choices.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line[0] in ANSWER_GLYPHS:
            out["choices"].append(line[1:].strip())
        else:
            out["choices"].append(line)

    # ★ 해설은 그림 줄을 **포함한 채로** 둔다. _rounds 의 explanation 이 그렇게
    #   생겼고, 여기서 떼어내면 왕복이 깨진다. 인라인된 파일명만 따로 보고한다.
    expl = section(SECTION_EXPLAIN, None)
    img_re = re.compile(r"!\[(?P<alt>[^\]]*)\]\(assets/(?P<file>[^)]+)\)")
    for m in img_re.finditer(expl):
        f = m.group("file")
        out["assets"].append(f[:-4] if f.endswith(".svg") else f)
    out["explanation"] = expl
    return out


def read_flags(md_path: str) -> dict:
    """기존 md 에서 보존해야 하는 플래그를 읽는다.

    ★ has_sql / has_table 은 _rounds 에 없다(실측 240문항 전부 false). 파일이
      있으면 그 값을 그대로 다시 쓴다. 없을 때만 추정하고, 추정했다는 사실을
      `estimated` 로 알려서 화면이 '추정' 배지를 달 수 있게 한다.
    """
    if os.path.isfile(md_path):
        try:
            fm = parse(open(md_path, encoding="utf-8").read())["fm"]
            return {
                "has_sql": bool(fm.get("has_sql", False)),
                "has_table": bool(fm.get("has_table", False)),
                "authored_by": fm.get("authored_by") or "claude",
                "verified": bool(fm.get("verified", True)),
                "reviewed": bool(fm.get("reviewed", False)),
                "needs_review": bool(fm.get("needs_review", True)),
                "source": "preserved",
            }
        except Exception:
            pass   # 손상된 md — 아래 추정으로 내려간다
    return {"source": "estimated"}


def flags_for(question: dict, md_path: str) -> dict:
    """보존 우선, 없으면 추정."""
    flags = read_flags(md_path)
    if flags.get("source") == "estimated":
        flags.update({
            "has_sql": derive.guess_has_sql(question),
            "has_table": derive.guess_has_table(question),
            "authored_by": "claude",
            "verified": True,
            "reviewed": False,
            "needs_review": True,
        })
    return flags
