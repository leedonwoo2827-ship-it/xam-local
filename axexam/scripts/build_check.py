"""05 lesson JSON(또는 02 집필 MD) + 02 메타 → 정적 웹(06) + DB 임포트용 problems.json.

<book>/05/*/source/lesson_*.json 을 모아 <book>/06/ 생성:
  06/check.html         WOWPASS 디자인 문제풀이+채점 화면
  06/problems.js        window.PROBLEMS  (정적 폴백 전용 — 서버에선 api/problems.php 가 이긴다)
  06/videos.js          window.VIDEOS    (유튜브 {provider,id} — mp4 복사 안 함)
  06/assets/            디자인 자산 (폰트는 CDN 이라 번들하지 않는다)
  06/figs/              문제 도식 SVG
  06/theory/            이론 요약노트

문제의 진짜 과목·검수상태는 05 가 아니라 `02/` 에 있다 → exam_meta.py 참조.

## 문제 본문의 출처가 둘이다 (`--src`)

| `--src` | 읽는 곳 | 언제 |
|---|---|---|
| `05` | `05/*/source/lesson_*.json` | 영상 대본·번들까지 만든 문제집 (SQLD) |
| `02` | `02/m*.md` 본문 직접 파싱 | **집필(02)·요약노트(03)만 나온 문제집** |
| `auto` (기본) | 05 가 있으면 05, 없으면 02 | |

`--src 02` 가 있는 이유: 영상은 문제집의 필수 부품이 아니다. 빅데이터분석기사 필기처럼
`04/`·`05/` 를 아직 안 돌린 문제집도 문제풀이·성적표·과목게시판은 전부 동작해야 한다.
예전에는 본문이 05 에만 있어서 **영상 대본을 만들기 전에는 문제집을 열 수 없었다.**

사용:
  python scripts/build_check.py                       # 정적 폴백 빌드
  python scripts/build_check.py --emit-json           # problems.json (adm/exam_import.php 업로드용)
  python scripts/build_check.py --emit-json --pd adsp # 품목 지정
  python scripts/build_check.py --api-base ./api/     # check.html 에 EXAM_API 주입 (서버 배포용)
  python scripts/build_check.py --init-youtube-map    # data/youtube_map.json 골격 1회 생성

  # 영상 없이 (02/ 집필 결과만으로) 새 문제집 빌드
  python scripts/build_check.py --book D:/00work/ocr-output-260730 \
         --pd bdae-w --pd-name "빅데이터분석기사 필기" --emit-json --prune
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml  # pyyaml>=6.0 — requirements.txt 에 이미 있다 (02/ frontmatter 파싱)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exam_meta import load_meta, load_rounds, load_subjects, src_id  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# check_template.html 은 더 이상 굽지 않는다.
# 문제풀이 화면은 web/exam/check.php + assets/check.css + assets/check.js 로 옮겼다
# (과목게시판이 그누보드 게시판이라 정적 HTML 안에 들어가지 않는다).
# 템플릿 파일은 이력 참고용으로만 남겨둔다 — 빌드는 읽지 않는다.
LANDING  = Path(__file__).with_name("landing_template.html")   # → 06/index.html  (포털 메인)
DETAIL   = Path(__file__).with_name("detail_template.html")    # → 06/detail.html (문제집 상세, ?pd= 로 N품목)
PRESENT_ASSETS = ROOT / "assets" / "present"
YOUTUBE_MAP = ROOT / "data" / "youtube_map.json"
BRAND_JSON = ROOT / "data" / "brand.json"
KST = timezone(timedelta(hours=9))
_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")

# 브랜드가 없을 때의 최소 기본값. 파일을 지워도 빌드가 죽지 않게 한다.
BRAND_FALLBACK = {
    "brand": "XAMpass",
    "brand_html": "<i>XAM</i>pass",
    "tagline": "자격증 문제은행",
    "intro": "자격증 문제은행과 1:1 질문 서비스.",
}


def load_brand() -> dict:
    """data/brand.json — 브랜드 단일 출처.

    형제 사이트(어학XAMpass·금융XAMpass)를 만들 때 고치는 유일한 파일이다.
    `_comment` 키는 설명용이라 걸러낸다.
    """
    if not BRAND_JSON.exists():
        print(f"[경고] {BRAND_JSON.name} 이 없어 기본 브랜드로 굽습니다.")
        return dict(BRAND_FALLBACK)
    try:
        raw = json.loads(BRAND_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"[브랜드] {BRAND_JSON} 파싱 실패: {e}")

    b = dict(BRAND_FALLBACK)
    for k, v in raw.items():
        if k.startswith("_") or not isinstance(v, str):
            continue
        b[k] = v
    for k in BRAND_FALLBACK:
        if not b.get(k):
            raise SystemExit(f"[브랜드] {BRAND_JSON.name} 의 '{k}' 가 비어 있습니다.")
    return b


def php_str(s: str) -> str:
    """PHP 홑따옴표 문자열 리터럴. 홑따옴표와 백슬래시만 이스케이프하면 된다."""
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _parse_bundle(bundle: str) -> tuple[int, int]:
    """m01-3 → (round=1, part=3). part 없으면 0."""
    m = re.search(r"m0*(\d+)(?:-(\d+))?", bundle or "")
    if not m:
        return 0, 0
    return int(m.group(1)), int(m.group(2) or 0)


# 번들 1개 = 문제 10개. 05/ 의 편성 규칙(`m01-1` = 1회 1~10번)과 같은 값이다.
PART_SIZE = 10


def bundle_of(rn: int, num, part_size: int = PART_SIZE) -> str:
    """(1, 7) → 'm01-1'. 05/ 번들 디렉터리명과 같은 규칙.

    `--src 02` 에는 번들 디렉터리가 없으므로 번호에서 계산한다.
    05 경로는 디렉터리명을 그대로 쓰므로 이 함수를 타지 않는다 — 두 경로가
    같은 이름을 만들어야 `pr_key` 가 갈리지 않는다.
    """
    if not rn:
        return ""
    try:
        part = (int(num) - 1) // int(part_size) + 1
    except (TypeError, ValueError):
        part = 0
    return f"m{int(rn):02d}-{part}" if part > 0 else f"m{int(rn):02d}"


def pr_key_of(bundle: str, num) -> str:
    """임포트 upsert 축 — `UNIQUE (pd_id, pr_key)`.

    ⚠ 형식이 바뀌면 같은 문제가 새 행으로 들어가고 `pr_id` 가 갈려서
      `ex_attempt_item`·`ex_wrong` 의 참조가 조용히 끊긴다. **되돌릴 수 없다.**
      규칙을 여기 한 곳에만 둔다 — check.js 의 `keyOf()` 와 같은 규칙이다.
    """
    return f"{bundle}#{num}"


# 도식 파일 확장자. SQLD 는 전부 SVG 지만 OCR 산출물은 PNG 스크린샷이다
# (`01/images/01-14_1.png`) — SVG 만 찾으면 그림이 조용히 사라진다.
FIG_EXT = ("*.svg", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif")


def _svg_index(book: Path) -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for sub in ("02/assets", "04/assets", "03/assets", "02/images", "01/images"):
        d = book / sub
        if d.is_dir():
            for pat in FIG_EXT:
                for f in d.glob(pat):
                    idx.setdefault(f.name, f)
    return idx


# 해설로 되돌리는 그림 줄의 경로 앞머리. check.js 는 파일 이름만 떼어 쓰므로
# 어떤 앞머리든 되지만, 02/*.md 원본과 같은 모양으로 둔다.
FIG_DIR_MD = "assets"


def _inline(text: str) -> set[str]:
    return {Path(u).name for u in _IMG_RE.findall(text or "")}


def _hash(p: dict) -> str:
    """콘텐츠 md5 — 임포트가 이걸로 변경분만 UPDATE 한다.

    표시용 메타(subject 라벨 등)는 넣지 않는다. 본문이 안 바뀌었는데
    해시가 흔들리면 매번 전건 UPDATE 가 나간다.
    """
    payload = json.dumps([
        p.get("question") or "", p.get("passage") or "", p.get("sql") or "",
        p.get("table"), p.get("choices") or [], p.get("answer_index"),
        p.get("explanation") or "",
    ], ensure_ascii=False, sort_keys=True)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _figs_copier(book: Path, figs_dir: Path):
    """도식 SVG 를 06/pd/<pd>/figs/ 로 복사하는 클로저. (ensure, copied, missing)

    05·02 두 수집 경로가 같은 규칙으로 복사해야 한다 — 한쪽만 고치면
    한 문제집에서만 도식이 사라지고, 그건 배포 후에나 보인다.
    """
    svg_idx = _svg_index(book)
    figs_dir.mkdir(parents=True, exist_ok=True)
    copied: set[str] = set()
    missing: set[str] = set()

    def ensure(name: str):
        base = Path(name).name
        if base in copied or base in missing:
            return
        src = svg_idx.get(base)
        if src:
            shutil.copy2(src, figs_dir / base)
            copied.add(base)
        else:
            missing.add(base)

    return ensure, copied, missing


def collect(book: Path, figs_dir: Path, meta: dict[str, dict], strict: bool = True):
    """05 의 lesson 블록 + 02 의 메타를 조인해 문제 목록을 만든다.

    ⚠ subject 는 lesson 블록에 **없다**(전부 None). 반드시 meta 에서 가져온다.
       예전 `b.get("subject") or subj` 는 lesson 최상위 'SQLD' 로 폴백해
       300문제를 전부 'SQLD' 로 채웠다.
    """
    ensure, copied, missing = _figs_copier(book, figs_dir)

    probs: list[dict] = []
    no_meta: list[str] = []
    for lj in sorted((book / "05").glob("*/source/lesson_*.json")):
        try:
            d = json.loads(lj.read_text(encoding="utf-8"))
        except Exception:
            continue
        bundle = lj.parent.parent.name
        rn, _part = _parse_bundle(bundle)
        for b in d.get("blocks") or []:
            if b.get("kind") != "problem" and not b.get("question"):
                continue
            num = b.get("number")
            sid = src_id(rn, num) if (rn and num is not None) else ""
            m = meta.get(sid) or {}
            if not m:
                no_meta.append(f"{bundle}#{num} (src_id={sid or '?'})")

            q = b.get("question") or ""
            passage = b.get("passage") or ""
            expl = b.get("explanation") or ""
            inl_q = _inline(q) | _inline(passage)
            inl_e = _inline(expl)
            asset_field = {Path(a).name for a in (b.get("assets") or [])}
            # ★ 그림이 **어디 것인지**를 지킨다. 05/lesson 은 본문에서 그림 줄을 지우고
            #   이름만 `assets` 로 옮기므로, 그것만 보면 해설 그림도 문제 칸에 그려진다.
            #   실제로 그렇게 나갔다 — 빅분기 235문항의 그림이 전부 해설 것인데 보기
            #   위에 걸렸고, "옳지 않은 것" 문항은 그림이 답을 그대로 보여줬다.
            #   lesson.py 가 지문 쪽만 `passage_assets` 로 남겨 두므로(집필 규약:
            #   「지문의 그림은 답을 가리고, 해설의 그림은 온전하게」), **남은 것은
            #   해설 것**이다. 실측으로 `question` 에 그림 줄이 있는 문항은 두 책 다 0 이다.
            pass_field = {Path(a).name for a in (b.get("passage_assets") or [])}
            # 문제 칸에 그릴 것 — 지문이 가리킨 그림뿐. 본문에 줄이 살아 있으면
            # mdLines() 가 이미 그리므로 여기서 뺀다.
            figures = sorted((asset_field & pass_field) - inl_q)
            # 해설 것 — 해설 본문에 그림 줄을 되돌린다. check.js 가 해설을 mdb() 로
            # 그리므로 그 안에서 렌더된다. DB 스키마를 늘리지 않아도 된다.
            expl_only = sorted(asset_field - pass_field - inl_q - inl_e)
            if expl_only:
                expl = (expl.rstrip() + "\n\n"
                        + "\n".join(f"![]({FIG_DIR_MD}/{n})" for n in expl_only))
            for name in (asset_field | inl_q | inl_e):
                ensure(name)

            rec = {
                "round_num": rn, "round": f"{rn}회" if rn else bundle, "bundle": bundle,
                "src_id": sid,
                "src_from": str(m.get("derived_from") or ""),
                # ★ meta 에서만 온다. lesson 폴백 없음.
                "subject": m.get("subject") or "",
                "subject_no": m.get("subject_no") or 0,
                "number": num,
                "difficulty": b.get("difficulty") or m.get("difficulty") or "",
                "question": q, "passage": passage,
                "sql": b.get("sql") or "", "table": b.get("table") or None,
                "figures": figures,
                "choices": [str(c) for c in (b.get("choices") or [])],
                "answer_index": b.get("answer_index"),
                "answer": b.get("answer") or m.get("answer") or "",
                "explanation": expl,
                "tags": b.get("tags") or m.get("tags") or [],
                # 검수 상태 — 02/*.md frontmatter 에만 있다
                "verified": bool(m.get("verified")),
                "reviewed": bool(m.get("reviewed")),
                "needs_review": bool(m.get("needs_review")),
            }
            rec["n_choices"] = m.get("n_choices") or len(rec["choices"])
            rec["has_figure"] = bool(figures or inl_q or inl_e)
            rec["has_sql"] = bool(rec["sql"])
            rec["has_table"] = bool(rec["table"])
            rec["pr_hash"] = _hash(rec)
            probs.append(rec)

    probs.sort(key=lambda p: (p["round_num"], p.get("number") or 0))

    if no_meta:
        head = ", ".join(no_meta[:8]) + (" …" if len(no_meta) > 8 else "")
        msg = f"02/ 메타를 못 찾은 문제 {len(no_meta)}건: {head}"
        if strict:
            raise SystemExit(f"[error] {msg}\n"
                             "        --no-strict-meta 로 무시할 수 있지만 그러면 과목이 빈 채로 나간다.")
        print(f"[warn] {msg}")

    return probs, copied, missing


# ── 02/ 집필 MD 직접 파싱 (영상 없는 문제집) ──────────────────────────────
#
# 섹션 순서는 `ocr-output-*/README.md` 가 정한 규칙이다:
#   ## 문제 → ## 지문 → ## 보기 → ## 해설
# 표·SQL·도식은 `지문` 안의 마크다운으로 온다. check.js 의 `mdb()` 가
# 표(`|`)·펜스(```)·불릿·`![](assets/x.svg)` 를 전부 렌더하므로 **본문을 그대로 넘긴다.**
# `sql`/`table` 필드로 쪼개면 두 벌 렌더가 되어 같은 표가 두 번 나온다.

_SEC_RE = re.compile(r"^##[ \t]+(문제|지문|보기|해설)[ \t]*$", re.M)
_CHOICE_RE = re.compile(r"^[ \t]*(?:([①-⑳])|(\d{1,2})[.)])[ \t]*(.*)$")


def _md_split(text: str) -> tuple[dict, dict[str, str]]:
    """`02/mNN-NN.md` → (frontmatter, {'문제':…, '지문':…, '보기':…, '해설':…})"""
    parts = text.split("---", 2)
    fm: dict = {}
    body = text
    if len(parts) >= 3:
        try:
            fm = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            fm = {}
        body = parts[2]

    sec: dict[str, str] = {}
    marks = [(m.group(1), m.start(), m.end()) for m in _SEC_RE.finditer(body)]
    for i, (name, _s, end) in enumerate(marks):
        nxt = marks[i + 1][1] if i + 1 < len(marks) else len(body)
        sec[name] = body[end:nxt].strip()
    return fm, sec


def _md_choices(sec: str) -> list[str]:
    """`① 보기 문구` 또는 `1. 보기 문구` → ['보기 문구', ...] (번호 표식 제거)

    보기 번호는 화면이 `CIRC[ci]` 로 다시 붙인다. 본문에 남기면 '① ① 문구' 가 된다.

    ⚠ **표식만 있고 내용이 다음 줄에 오는 형태가 실제로 있다** (SQLD 300문제 중 11건):

        ## 보기
        ①

        ```sql
        SELECT ... FROM ...;
        ```

        ②
        ...

    이때 05 경로의 lesson JSON 은 펜스를 버리고 코드 본문만 `\\n` 포함해 담았다
    (실측: `'SELECT e.사원명, d.부서명\\nFROM 사원 e CROSS JOIN 부서 d;'`).
    두 경로가 다른 문자열을 만들면 `pr_hash` 가 갈려 재임포트가 전건 UPDATE 를 낸다.
    """
    out: list[str] = []
    for line in (sec or "").splitlines():
        m = _CHOICE_RE.match(line)
        if m:
            out.append((m.group(3) or "").strip())
            continue
        if not out:
            continue                      # 첫 표식 이전의 잡텍스트
        s = line.strip()
        if s.startswith("```"):
            continue                      # 펜스는 버린다 (위 주석)
        out[-1] = (out[-1] + "\n" + line.rstrip()).strip()
    return out


def collect_02(book: Path, figs_dir: Path, meta: dict[str, dict],
               strict: bool = True, part_size: int = PART_SIZE):
    """02/m*.md 본문을 직접 읽어 05 경로와 같은 형태의 문제 목록을 만든다.

    05 경로와 반환 형태가 **완전히 같아야 한다** — 이후 단계(problems.js·
    problems.json·화면)가 어느 경로로 수집됐는지 알 필요가 없어야 한다.
    """
    ensure, copied, missing = _figs_copier(book, figs_dir)

    probs: list[dict] = []
    bad: list[str] = []
    for md_path in sorted((book / "02").glob("m*.md")):
        fm, sec = _md_split(md_path.read_text(encoding="utf-8"))
        mid = str(fm.get("id") or "")
        rn = fm.get("round")
        num = fm.get("question_no")
        rn = int(rn) if isinstance(rn, int) else 0
        m = meta.get(mid) or {}

        q = sec.get("문제", "")
        passage = sec.get("지문", "")
        expl = sec.get("해설", "")
        choices = _md_choices(sec.get("보기", ""))
        ai = fm.get("answer_index")

        # ── 검증. 여기서 죽는 게 낫다 ────────────────────────────────
        # 조용히 통과하면 빈 문제·정답 없는 문제가 DB 에 upsert 되고,
        # 그때는 회원 채점 기록이 이미 붙어 있어 지우기가 어려워진다.
        where = md_path.name
        if not rn or not isinstance(num, int):
            bad.append(f"{where}: round/question_no 가 정수가 아니다 ({rn!r}/{num!r})")
        elif mid != src_id(rn, num):
            bad.append(f"{where}: id={mid!r} 가 규칙과 다르다 (기대 {src_id(rn, num)!r})")
        if not q:
            bad.append(f"{where}: '## 문제' 가 비었다")
        if len(choices) < 2:
            bad.append(f"{where}: '## 보기' 를 {len(choices)}개만 읽었다 (①②③④ 또는 1. 형식)")
        if not isinstance(ai, int) or not (0 <= ai < max(len(choices), 1)):
            bad.append(f"{where}: answer_index={ai!r} 가 보기 범위(0~{len(choices) - 1}) 밖이다")
        if not fm.get("subject") or not isinstance(fm.get("subject_no"), int):
            bad.append(f"{where}: subject/subject_no 가 없다 — 과목 필터·성적표가 죽는다")

        inline = _inline(q) | _inline(passage) | _inline(expl)
        for name in inline:
            ensure(name)

        bundle = bundle_of(rn, num, part_size)
        rec = {
            "round_num": rn, "round": f"{rn}회" if rn else bundle, "bundle": bundle,
            "src_id": mid,
            "src_from": str(fm.get("derived_from") or ""),
            "subject": fm.get("subject") or m.get("subject") or "",
            "subject_no": fm.get("subject_no") or m.get("subject_no") or 0,
            "number": num,
            "difficulty": fm.get("difficulty") or "",
            "question": q, "passage": passage,
            # 지문 마크다운을 쪼개지 않는다 (위 주석) — 화면이 통째로 렌더한다.
            "sql": "", "table": None,
            "figures": [],          # 도식은 본문 안에 인라인으로 있다
            "choices": choices,
            "answer_index": ai if isinstance(ai, int) else None,
            "answer": str(fm.get("answer") or ""),
            "explanation": expl,
            "tags": fm.get("tags") or [],
            "verified": bool(fm.get("verified")),
            "reviewed": bool(fm.get("reviewed")),
            "needs_review": bool(fm.get("needs_review")),
        }
        rec["n_choices"] = fm.get("n_choices") or len(choices)
        rec["has_figure"] = bool(inline)
        rec["has_sql"] = bool(re.search(r"```sql|^\s*SELECT\b", passage, re.M | re.I))
        rec["has_table"] = bool(re.search(r"^\s*\|.*\|", passage, re.M))
        rec["pr_hash"] = _hash(rec)
        probs.append(rec)

    probs.sort(key=lambda p: (p["round_num"], p.get("number") or 0))

    if not probs:
        raise SystemExit(f"[error] 02/ 에서 문제를 못 읽었다: {book / '02'}\n"
                         "        파일명이 'mNN-NN.md' 여야 한다 (OCR 산출물 '01-01.md' 는 잡히지 않는다).\n"
                         "        → docs/편지-프로덕트2-3.md 의 #2 계약 참조")
    if bad:
        head = "\n        ".join(bad[:12]) + (f"\n        … 그리고 {len(bad) - 12}건" if len(bad) > 12 else "")
        msg = f"02/ 본문 검증 실패 {len(bad)}건:\n        {head}"
        if strict:
            raise SystemExit(f"[error] {msg}\n"
                             "        --no-strict-meta 로 무시할 수 있지만 그러면 깨진 문제가 그대로 임포트된다.")
        print(f"[warn] {msg}")

    return probs, copied, missing


def _num_range(bundle_dir: Path) -> tuple[int, int] | None:
    """번들의 문제 번호 min~max (라벨 'N회 1~10번' 용)."""
    for lj in (bundle_dir / "source").glob("lesson_*.json"):
        try:
            d = json.loads(lj.read_text(encoding="utf-8"))
        except Exception:
            continue
        nums = [b.get("number") for b in (d.get("blocks") or []) if isinstance(b.get("number"), int)]
        if nums:
            return min(nums), max(nums)
    return None


def _bundles(book: Path) -> list[tuple[str, int, int, str]]:
    """[(bundle, round, part, label)] — 05 의 번들 목록. 라벨은 문제번호 범위."""
    out = []
    for d in sorted((book / "05").glob("*/")):
        if not d.is_dir():
            continue
        bundle = d.name
        rn, part = _parse_bundle(bundle)
        if not rn:
            continue
        rng = _num_range(d)
        label = f"{rn}회 {rng[0]}~{rng[1]}번" if rng else (f"{rn}회 {part}부" if part else f"{rn}회")
        out.append((bundle, rn, part, label))
    return out


def _bundles_from_probs(probs: list[dict]) -> list[tuple[str, int, int, str]]:
    """05/ 가 없는 문제집의 번들 목록 — 수집된 문제에서 만든다.

    영상을 나중에 붙일 때 `youtube_map` 골격이 05 경로와 같은 이름·라벨이어야
    한다. 그래야 `04/`·`05/` 를 나중에 돌려도 매핑이 그대로 맞는다.
    """
    agg: dict[str, list[int]] = {}
    for p in probs:
        b = p.get("bundle") or ""
        n = p.get("number")
        if b and isinstance(n, int):
            agg.setdefault(b, []).append(n)
    out = []
    for bundle in sorted(agg, key=lambda b: _parse_bundle(b)):
        rn, part = _parse_bundle(bundle)
        nums = agg[bundle]
        out.append((bundle, rn, part, f"{rn}회 {min(nums)}~{max(nums)}번"))
    return out


def _bundles_from_meta(meta: dict[str, dict],
                       part_size: int = PART_SIZE) -> list[tuple[str, int, int, str]]:
    """문제를 수집하지 않고 메타만으로 번들 목록. `--init-youtube-map` 전용."""
    return _bundles_from_probs([
        {"bundle": bundle_of(m.get("round") or 0, m.get("question_no"), part_size),
         "number": m.get("question_no")}
        for m in meta.values()
        if isinstance(m.get("round"), int) and isinstance(m.get("question_no"), int)
    ])


def has_lessons(book: Path) -> bool:
    """05/ 에 lesson JSON 이 실제로 있는가. 폴더만 있고 비어 있으면 False."""
    return any((book / "05").glob("*/source/lesson_*.json"))


def youtube_map_path(pd_id: str) -> Path | None:
    """품목별 영상 매핑 파일. 없으면 None (영상 없이 빌드).

    ⚠ `youtube_map.json` 의 키는 번들명(`m01-1`)이라 **품목 간에 충돌한다.**
      SQLD 1회 1~10번과 빅분기 1회 1~10번이 같은 `m01-1` 이므로 한 파일에 두면
      한쪽 영상이 다른 문제집에 붙는다. 그래서 품목별 파일로 가른다.

      기존 `data/youtube_map.json` 은 SQLD 것이다(그 시절 품목이 하나였다).
      다른 품목은 `data/youtube_map.<pd_id>.json` 을 쓴다 — 없으면 영상 없음.
    """
    per = ROOT / "data" / f"youtube_map.{pd_id}.json"
    if per.exists():
        return per
    if pd_id == "sqld" and YOUTUBE_MAP.exists():
        return YOUTUBE_MAP
    return None


def init_youtube_map(book: Path, pd_id: str = "sqld",
                     bundles: list[tuple[str, int, int, str]] | None = None) -> Path:
    """영상 매핑 골격을 1회 생성한다. 이미 있으면 건드리지 않는다.

    이 파일은 **수동 관리 입력 파일**이고 빌드가 절대 덮어쓰지 않는다.
    유튜브에 올린 뒤 URL 의 v= 값을 `id` 에 붙여 넣으면 된다.
    """
    dest = youtube_map_path(pd_id)
    if dest:
        print(f"[youtube] 이미 있음 — 덮어쓰지 않는다: {dest}")
        return dest
    dest = (YOUTUBE_MAP if pd_id == "sqld" else ROOT / "data" / f"youtube_map.{pd_id}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "_note": "수동 관리 파일. 빌드가 덮어쓰지 않는다. id 에 유튜브 URL 의 v= 값을 넣는다.",
        "_provider": "youtube",
        "videos": {b: {"id": "", "label": lab, "sec": 0}
                   for b, _rn, _p, lab in (bundles if bundles is not None else _bundles(book))},
    }
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[youtube] 골격 생성 {len(data['videos'])}개 → {dest}")
    return dest


# 화면(`check.js` 의 `embedUrl()`)이 아는 provider 전부.
#
# ⚠ `embedUrl()` 은 모르는 provider 를 **유튜브로 간주한다**(마지막 줄 폴백).
#   `provider: "mybox"` 라고 쓰면 `youtube-nocookie.com/embed/https://mybox…` 가 되어
#   빈 iframe 이 뜨고 원인이 안 보인다. 그래서 빌드에서 죽인다.
#
#   youtube  youtube-nocookie embed
#   drive    drive.google.com/…/preview embed (구글 드라이브는 embed 가 된다)
#   vimeo    player.vimeo.com embed
#   file     서버 파일 직접 재생 (<video src>)
#   link     ★ embed 하지 않고 새 창으로 보낸다 — **네이버 마이박스는 이것을 쓴다**
#            (마이박스는 embed 엔드포인트가 없다. 공유 페이지를 열어야 한다)
PROVIDERS = ("youtube", "drive", "vimeo", "file", "link")


def video_id(raw: str, provider: str) -> str:
    """사람이 붙여넣은 값에서 실제 ID 만 뽑는다.

    공유 버튼으로 복사한 **URL 을 그대로 붙여넣는 게 정상적인 사용**이다.
    그걸 ID 로 오인하면 embed 가 조용히 깨지고(빈 iframe), 원인 찾기가 짜증난다.

      드라이브  https://drive.google.com/file/d/1AbC.../view?usp=sharing  → 1AbC...
      유튜브    https://youtu.be/dQw4w9WgXcQ                              → dQw4w9WgXcQ
                https://www.youtube.com/watch?v=dQw4w9WgXcQ               → dQw4w9WgXcQ
    """
    s = (raw or "").strip()
    if not s or "/" not in s:
        return s                                   # 이미 ID 다

    if provider == "drive":
        m = re.search(r"/file/d/([A-Za-z0-9_-]{10,})", s)
        if m:
            return m.group(1)
        m = re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", s)   # 옛 형식 open?id=
        if m:
            return m.group(1)
    elif provider == "youtube":
        m = re.search(r"(?:youtu\.be/|[?&]v=|/embed/|/shorts/)([A-Za-z0-9_-]{11})", s)
        if m:
            return m.group(1)
    elif provider == "vimeo":
        m = re.search(r"vimeo\.com/(?:video/)?(\d+)", s)
        if m:
            return m.group(1)

    return s        # provider=file 이거나 못 알아본 형식 — 그대로 쓴다


def map_videos(book: Path, pd_id: str = "sqld",
               bundles: list[tuple[str, int, int, str]] | None = None) -> tuple[dict, int, int, dict]:
    """품목별 영상 매핑 → VIDEOS 맵. **mp4 를 복사하지 않는다.**

    반환 {'1회': [{label, part, provider, id, sec}, ...]}.
    `id` 가 빈 항목은 아직 업로드 전이므로 제외한다(화면에 죽은 버튼이 생기지 않게).
    """
    entries: dict[str, dict] = {}
    provider = "youtube"
    dflt_lv = 0
    ymap = youtube_map_path(pd_id)
    if ymap:
        try:
            raw = json.loads(ymap.read_text(encoding="utf-8"))
            entries = raw.get("videos") or {}
            provider = raw.get("_provider") or "youtube"
            dflt_lv = int(raw.get("_min_level") or 0)
        except Exception as e:
            print(f"[warn] {ymap.name} 파싱 실패({e}) — 영상 없이 빌드한다")

    vids: dict[str, list] = {}       # 공개 — videos.js 로 구워진다
    priv: dict[str, list] = {}       # 레벨 제한 — videos.private.json (서버가 읽는다)
    filled = 0
    total = 0
    for bundle, rn, part, label in (bundles if bundles is not None else _bundles(book)):
        total += 1
        e = entries.get(bundle) or {}
        vid = str(e.get("id") or "").strip()
        if not vid:
            continue
        filled += 1
        # 항목별 provider 가 전역 _provider 를 이긴다 →
        # "검토 끝난 회차만 유튜브, 나머지는 아직 마이박스 링크" 혼용이 된다.
        # 완성품으로 한 번에 넘기려면 _provider 만 youtube 로 바꾸면 된다.
        prov = e.get("provider") or provider
        lv = int(e.get("min_level", dflt_lv) or 0)

        # 모르는 provider 는 화면이 유튜브로 간주해 빈 iframe 을 띄운다 → 여기서 죽인다
        if prov not in PROVIDERS:
            raise SystemExit(
                f"[error] {ymap.name if ymap else 'youtube_map'} 의 '{bundle}': "
                f"provider={prov!r} 를 화면이 모른다.\n"
                f"        쓸 수 있는 값: {', '.join(PROVIDERS)}\n"
                "        · 네이버 마이박스 → 'link' (embed 가 안 되므로 새 창으로 연다)\n"
                "        · 구글 드라이브   → 'drive' (embed 된다)\n"
                "        모르는 값을 그대로 두면 화면이 유튜브 embed 로 만들어 빈 iframe 이 뜬다.")

        # 검토용 외부 링크가 공개로 나가는 것 — 링크 자체가 접근 권한이라 유출이다
        if prov in ("link", "drive", "file") and lv <= 1:
            print(f"[WARN]  '{bundle}' provider={prov} 인데 min_level={lv} 다 —"
                  " 링크가 videos.js(정적 파일)에 구워져 **누구나 내려받는다.**")
            print("        검토 단계라면 min_level 을 5 로 둔다"
                  " (강사 계정 레벨 5 이상만 api/videos.php 로 받는다).")

        item = {
            "label": e.get("label") or label,
            "part": part,
            "provider": prov,
            "id": video_id(vid, prov),      # 붙여넣은 URL 에서 ID 를 뽑는다
            "sec": int(e.get("sec") or 0),
        }

        # ★ 레벨 제한이 있으면 videos.js 에 **넣지 않는다.**
        #   videos.js 는 정적 파일이라 누구나 내려받을 수 있다 — JS 에서 버튼만 숨겨도
        #   링크는 파일 안에 그대로 남는다. 가리려면 브라우저에 아예 안 내려가야 한다.
        #   api/videos.php 가 로그인 레벨을 보고 내려준다.
        if lv > 1:
            item["min_level"] = lv
            priv.setdefault(f"{rn}회", []).append(item)
        else:
            vids.setdefault(f"{rn}회", []).append(item)

    for m in (vids, priv):
        for k in m:
            m[k].sort(key=lambda v: v.get("part") or 0)
    return vids, filled, total, priv


def theory_videos(pd_id: str) -> dict[int, dict]:
    """이론 요약노트에 붙는 **과목별 강의 영상**. `youtube_map.<pd>.json` 의 `theory` 를 읽는다.

    회차 영상(`videos`)과 **같은 파일**에 둔다 — 발행 때 챙길 파일이 늘지 않게.
    키는 과목 번호다(요약노트 `<h1>N과목` 의 그 번호). `t1` 처럼 써도 받는다:

        "theory": { "1": {"id": "<드라이브 ID 또는 공유 URL>", "label": "1과목 이론 강의"} }

    `id` 가 빈 항목은 버린다 — 화면에 죽은 버튼이 생기지 않게(회차 영상과 같은 규칙).

    ★ 레벨 제한(min_level)은 지원하지 않는다. 이론 영상 링크는 공개 `theory.js` 에 실린다.
      가리려면 회차 영상처럼 별도 비공개 파일 + api/videos.php 통로가 필요한데 이론 탭에는
      그 통로가 없다. 비공개가 필요해지면 videos.private.json 방식을 그대로 옮긴다.
    """
    ymap = youtube_map_path(pd_id)
    if not ymap:
        return {}
    try:
        raw = json.loads(ymap.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[warn] {ymap.name} 파싱 실패({e}) — 이론 영상 없이 빌드한다")
        return {}

    dflt = raw.get("_provider") or "youtube"
    out: dict[int, dict] = {}
    for k, e in (raw.get("theory") or {}).items():
        e = e or {}
        try:
            sub = int(str(k).strip().lstrip("tT") or 0)
        except ValueError:
            print(f"[warn] {ymap.name} 의 theory '{k}' — 과목 번호로 읽을 수 없다. 건너뛴다")
            continue
        vid = str(e.get("id") or "").strip()
        if not sub or not vid:
            continue
        prov = e.get("provider") or dflt
        # 모르는 provider 는 화면이 유튜브로 간주해 빈 iframe 을 띄운다 → 여기서 죽인다
        if prov not in PROVIDERS:
            raise SystemExit(
                f"[error] {ymap.name} 의 theory '{k}': provider={prov!r} 를 화면이 모른다.\n"
                f"        쓸 수 있는 값: {', '.join(PROVIDERS)}")
        out[sub] = {"provider": prov, "id": video_id(vid, prov),
                    "label": e.get("label") or f"{sub}과목 이론 강의"}
    return out


def build_theory(book: Path, out: Path,
                 tvids: dict[int, dict] | None = None) -> tuple[list[dict], dict]:
    """03 요약노트 → 이론 탭 목록 + 내용(JS 에 구워넣을 dict) 반환.

    fetch/iframe 없이 file://·서버 둘 다 되도록, 각 요약 HTML 의 <style>+<body> 를 추출해
    theory_content.js(window.THEORY_HTML)로 굽는다.

    `tvids` 가 있으면 과목별 강의 영상을 항목에 `vid` 로 얹는다(`theory_videos()` 참조).
    """
    src = book / "03"
    if not src.is_dir():
        return [], {}
    tdir = out / "theory"
    tdir.mkdir(parents=True, exist_ok=True)
    if (src / "assets").is_dir():
        shutil.copytree(src / "assets", tdir / "assets", dirs_exist_ok=True)

    files = sorted(src.glob("summary_*.html"))
    name_map: dict[str, str] = {}
    i = 0
    for f in files:
        if f.name.isascii():
            name_map[f.name] = f.name
        else:
            i += 1
            name_map[f.name] = f"summary_ko{i}.html"

    def subject_of(html: str) -> tuple[int, str]:
        m = re.search(r"<h1[^>]*>([^<]*)</h1>", html) or re.search(r"<title>([^<]*)</title>", html)
        t = (m.group(1) if m else "").strip()
        mm = re.search(r"(\d+)\s*과목\s*[·:\-—\s]*(.*)", t)
        return (int(mm.group(1)), mm.group(2).strip(" —-·")) if mm else (99, t)

    content: dict[str, str] = {}
    items: list[dict] = []
    for f in files:
        raw = f.read_text(encoding="utf-8")
        styles = "".join(re.findall(r"<style[^>]*>(.*?)</style>", raw, re.S))
        # ★ 본문을 찾기 전에 <style> 을 떼어낸다. 요약노트 CSS 주석에 설명용으로 적힌
        #   `<body>` 가 진짜 본문보다 먼저 나오기 때문이다(authoring/theory.py 의 _FOLD_CSS).
        #   원문 그대로 찾으면 CSS 조각이 본문으로 잘려 나간다 — 2026-08-13 에 4개 과목이
        #   전부 이렇게 깨져 있었다(첫 <body> 1703~2128, 진짜 본문 3218~3643). 화면에는
        #   주석 한 줄만 뜨고 h2 15개·h3 136개가 사라진다.
        naked = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.S)
        mb = re.search(r"<body[^>]*>(.*?)</body>", naked, re.S)
        body = mb.group(1) if mb else naked
        for old, new in name_map.items():
            if old != new:
                body = body.replace(old, new)
        body = re.sub(r'(src|href)="(?!https?:|data:|#|/|theory/)([^"]+)"', r'\1="theory/\2"', body)
        styles = re.sub(r'(^|[^-\w.#])body\b', r'\1:host', styles)
        key = f"theory/{name_map[f.name]}"
        content[key] = "<style>:host{display:block;background:#fff}</style><style>" + styles + "</style>" + body
        if f.stem != "summary_index":
            n, name = subject_of(raw)
            lab = f"{n}과목 · {name}" if n != 99 else (f.stem.replace("summary_", "") + " 요약")
            it = {"label": lab, "href": key, "sub": n}
            v = (tvids or {}).get(n)
            if v:
                it["vid"] = v      # 영상이 없는 과목은 키 자체를 넣지 않는다 → 버튼도 안 생긴다
            items.append(it)
    items.sort(key=lambda x: x["sub"])
    return items, content


#: `theory_content.js` 의 첫 줄. PHP 쪽(`adm/exam_lib/deploy.php`)이 이 줄을 알아본다.
THEORY_HTML_GUARD = "window.THEORY_HTML = window.THEORY_HTML || {};"


def theory_unit_line(key: str, html: str) -> str:
    """과목 하나를 담은 **한 줄**. 이것이 과목별 갈음의 최소 단위다.

    `window.THEORY_HTML["theory/summary_explore.html"] = "…";`
    """
    return (f"window.THEORY_HTML[{json.dumps(key, ensure_ascii=False)}] = "
            f"{json.dumps(html, ensure_ascii=False)};")


def write_theory_content(pdir: Path, theory_html: dict[str, str]) -> None:
    """이론 본문을 쓴다 — 합본 한 장 + **과목당 자립 파일 한 개.**

    ★ 왜 한 덩이가 아니라 과목마다 한 줄인가
      예전에는 4과목을 `json.dumps` 한 덩이로 구웠다. 그러면 과목 하나만 고쳐도
      `theory_content.js` 를 통째로 갈아야 하고, 아직 안 만든 과목이 옛 것으로
      덮인다(빅분기에서 실제로 막힌 지점 — 4과목 중 3과목만 새로 만들었다).
      과목 하나 = 한 줄로 두면 `adm/exam_deploy.php` 가 **그 한 줄만** 바꿔 쓸 수 있고,
      손대지 않은 과목은 바이트가 그대로 남는다.

    ★ 전역 이름(`window.THEORY_HTML`)과 `<script src="theory_content.js">` 한 장은
      그대로다. 그래서 `exam/check.php` · `assets/check.js` 는 이 변경을 모른다.

    `theory/summary_<key>.js` 는 갈음의 단위이자 「어느 과목을 언제 갈았나」의 기록이다
    (과목별 mtime 이 여기 생긴다). 화면이 읽는 파일은 아니다.
    """
    tdir = pdir / "theory"
    tdir.mkdir(parents=True, exist_ok=True)

    body = [
        "/* 과목 하나가 한 줄이다 — adm/exam_deploy.php 의 과목별 갈음이 그 한 줄만",
        "   바꿔 쓴다. 전역 이름은 그대로라 check.js 는 이 형식을 모른다.",
        "   같은 줄이 theory/summary_<key>.js 에도 한 개씩 들어 있다. */",
        THEORY_HTML_GUARD,
    ]
    for key in sorted(theory_html):
        line = theory_unit_line(key, theory_html[key])
        body.append(line)
        # 자립 파일 — 가드를 함께 담아 그것만 올려도 문법이 성립한다.
        (pdir / key).with_suffix(".js").write_text(
            THEORY_HTML_GUARD + "\n" + line + "\n", encoding="utf-8", newline="\n")

    # ★ newline="\n" 을 못 박는다. 윈도우에서 기본값은 CRLF 인데 서버(PHP)가 과목 한 줄을
    #   갈아끼울 때는 LF 로 쓴다. 그대로 두면 갈음 한 번에 파일 전체의 줄끝이 뒤집혀
    #   「무엇이 실제로 바뀌었나」를 바이트로 비교할 수 없게 된다.
    (pdir / "theory_content.js").write_text("\n".join(body) + "\n",
                                            encoding="utf-8", newline="\n")


def write_upload_set(out: Path, pdir: Path, pd: str) -> Path:
    """올릴 것을 한 곳에 모은다 — `06/_올릴것/`.

    ★ 왜 이 폴더가 필요한가
      빌드 산출물은 `06/` 안에 흩어져 있다(품목 것은 `pd/<pd>/`, 껍데기는 뿌리).
      그런데 웹 관리자 화면(`adm/exam_deploy.php`)에 올릴 때 사람이 매번
      "무엇을 어디서 골라야 하나" 를 다시 판단해야 했다. 그래서 **올릴 것만**
      한 폴더에 모아둔다. 목표는 하나다 — 만든 것을 그대로 끌어다 놓는다.

    ★ 규칙: 폴더가 끼는 것만 ZIP, 나머지는 파일 그대로.
      `figs/` 는 479개까지 가고 `assets/` 도 여러 개다. 그건 낱개 업로드로
      올리면 서버 실행 시간(카페24 실측 30초)에 걸린다. 반대로 파일 하나짜리를
      ZIP 으로 싸면 사람이 압축을 풀 이유가 없는데 한 단계가 늘어난다.

    ★ 이름을 바꾸지 않는다. 반입 화면이 파일 **이름으로** 갈 자리를 정하기 때문이다
      (`ex_deploy_add_rel()`). `problems.js` 를 `1-문항.js` 로 바꾸면 갈 곳을 잃는다.

    ★ `06/` 의 FTP 업로드 목록(`services/publish/ftplist.py`)에는 이 폴더가 없다.
      `UPLOAD_FILES`(이름 목록) · `UPLOAD_DIRS`(assets·figs·theory) · `pd/` 만 올라가므로
      `_올릴것/` 은 서버로 가지 않는다. `--prune` 도 건드리지 않는다.
    """
    dest = out / "_올릴것"
    if dest.exists():
        shutil.rmtree(dest)          # 지난 빌드의 잔재가 섞이면 무엇이 새것인지 알 수 없다
    dest.mkdir(parents=True)

    loose: list[str] = []
    zips: list[tuple[str, int]] = []

    # ── 주제마다 폴더 하나 (2026-08-26 지시)
    #
    # ★ 왜. 반입 화면의 박스가 다섯인데 파일은 한 폴더에 아홉 개가 섞여 있었다.
    #   「어느 파일이 어느 박스로 가나」 를 사람이 매번 다시 맞춰야 했다.
    #   폴더 하나가 박스 하나면 그 폴더를 통째로 열어 끌어다 놓으면 끝난다.
    # ★ **파일 이름은 그대로 둔다.** 반입 화면이 이름으로 갈 자리를 정한다
    #   (`ex_deploy_add_rel()`). 폴더 이름은 사람만 보는 것이라 바꿔도 안전하다.
    BOX = {
        "problems.js": "1_문항",
        "videos.js": "2_해설영상링크",
        "videos.private.json": "2_해설영상링크",
        "theory.js": "3_요약노트",
        "theory_content.js": "3_요약노트",
    }

    def _put(src: Path, box: str, name: str = "") -> str:
        d = dest / box
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, d / (name or src.name))
        return f"{box}/{name or src.name}"

    # ── 파일 그대로 — 하나짜리들 (품목)
    for n in ("problems.js", "videos.js", "videos.private.json",
              "theory.js", "theory_content.js"):
        if (pdir / n).is_file():
            loose.append(_put(pdir / n, BOX[n]))

    # 과목별 단위 파일 — 한 과목만 갈아끼울 때 쓴다. 처음 올릴 때는 안 쓴다.
    for p in sorted((pdir / "theory").glob("*.js")):
        loose.append(_put(p, "3_요약노트/과목별_갈음용"))

    def _zip(name: str, box: str, members: list[tuple[Path, str]]) -> None:
        if not members:
            return
        d = dest / box
        d.mkdir(parents=True, exist_ok=True)
        z = d / name
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
            for src, arc in members:
                f.write(src, arc)
        zips.append((f"{box}/{name}", z.stat().st_size))

    # ── ZIP — 폴더가 끼는 것
    figs = sorted((pdir / "figs").glob("*")) if (pdir / "figs").is_dir() else []
    _zip("문제도식.zip", "4_문제도식", [(p, f"figs/{p.name}") for p in figs if p.is_file()])

    shell: list[tuple[Path, str]] = []
    for n in ("index.html", "detail.html", "check.html"):
        if (out / n).is_file():
            shell.append((out / n, n))
    if (out / "assets").is_dir():
        for p in sorted((out / "assets").rglob("*")):
            if p.is_file():
                shell.append((p, str(p.relative_to(out)).replace("\\", "/")))
    _zip("공용껍데기.zip", "5_공용껍데기", shell)

    (dest / "올리는순서.txt").write_text(
        "\n".join([
            f"품목 {pd} — /adm/exam_deploy.php?pd={pd}",
            "",
            "폴더 하나가 반입 화면의 박스 하나다.",
            "폴더를 열어 안의 것을 그대로 끌어다 놓으면 된다.",
            "파일 이름은 바꾸지 않는다 — 반입 화면이 이름으로 갈 자리를 정한다.",
            "",
            "[파일 그대로]",
            *(f"     {n}" for n in loose),
            "",
            "[ZIP 으로]",
            *(f"     {n}  ({b:,}B)" for n, b in zips),
            "     ※ 5_공용껍데기 는 대상을 「공용 껍데기」로 바꿔 올린다.",
            "       모든 문제집이 같이 쓰므로 바뀌었을 때만 올린다.",
            "",
            "[파일이 아니라 DB]",
            f"     06/pd/{pd}/problems.json → /adm/exam_import.php",
            "     문항을 고쳤으면 1_문항 과 함께 해야 한다.",
            "     .htaccess 가 .json 을 403 으로 막아 반입으로는 안 올라간다.",
            "",
            "3_요약노트/과목별_갈음용 은 처음 올릴 때 쓰지 않는다 —",
            "한 과목만 고쳤을 때 그 파일 하나만 올리는 자리다.",
        ]) + "\n",
        encoding="utf-8", newline="\n")

    print(f"\n[올릴것] {dest}")
    print(f"         파일 그대로 {len(loose)}개 · ZIP {len(zips)}개")
    for n, b in zips:
        print(f"           {n}  {b:,}B")
    return dest


def emit_json(probs: list[dict], meta: dict[str, dict], pd_id: str, dest: Path) -> Path:
    """adm/exam_import.php 가 업로드받아 upsert 할 problems.json 을 만든다.

    ⚠ `pr_key` 규칙은 `pr_key_of()` 한 곳에만 있다. 왜 그런지는 그 함수 주석 참조.
    """
    rd_label = {r["rd_no"]: r["rd_label"] for r in load_rounds(meta)}
    rd_count: dict[int, int] = {}
    for p in probs:
        rd_count[p["round_num"]] = rd_count.get(p["round_num"], 0) + 1

    rows = []
    for p in probs:
        rows.append({
            "pr_key": pr_key_of(p["bundle"], p["number"]),
            "bundle": p["bundle"],
            "rd_no": p["round_num"],
            "pr_no": p["number"],
            "src_id": p["src_id"],
            "src_from": p["src_from"],
            "sj_no": p["subject_no"],
            "sj_name": p["subject"],
            "difficulty": p["difficulty"],
            "question": p["question"],
            "passage": p["passage"],
            "sql_text": p["sql"],
            "table_json": p["table"],
            "figures_json": p["figures"],
            "choices_json": p["choices"],
            "n_choices": p["n_choices"],
            "answer_index": p["answer_index"],
            "answer_label": p["answer"],
            "explanation": p["explanation"],
            "tags_json": p["tags"],
            "has_figure": p["has_figure"],
            "has_sql": p["has_sql"],
            "has_table": p["has_table"],
            "verified": p["verified"],
            "reviewed": p["reviewed"],
            "needs_review": p["needs_review"],
            "pr_hash": p["pr_hash"],
        })

    doc = {
        "pd_id": pd_id,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "rounds": [{"rd_no": rn, "rd_label": rd_label.get(rn, f"{rn}회"), "rd_count": c}
                   for rn, c in sorted(rd_count.items())],
        "subjects": load_subjects(meta),
        "problems": rows,
    }
    dest.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(prog="build_check.py",
                                 description="05 + 02 → 정적 웹(06) + problems.json")
    ap.add_argument("--book", default="D:/00work/ocr-output-260723")
    ap.add_argument("--out", default="")
    ap.add_argument("--pd", default="sqld", help="품목 코드 (ex_product.pd_id)")
    ap.add_argument("--pd-name", default="",
                    help="품목 표시명. file:// 미리보기에만 쓴다 — 서버는 ex_product.pd_name 이 이긴다")
    ap.add_argument("--emit-json", action="store_true", help="problems.json 생성 (DB 임포트용)")
    ap.add_argument("--json-out", default="", help="problems.json 경로 (기본: <out>/problems.json)")
    ap.add_argument("--api-base", default="", help="예: ./api/ — check.html 에 window.EXAM_API 주입")
    ap.add_argument("--src", choices=("auto", "05", "02"), default="auto",
                    help="문제 본문 출처. auto=05 가 있으면 05, 없으면 02 (모듈 docstring 참조)")
    ap.add_argument("--part-size", type=int, default=PART_SIZE,
                    help=f"--src 02 에서 번들 1개에 넣을 문제 수 (기본 {PART_SIZE}). "
                         "pr_key 에 들어가므로 임포트 후에는 바꾸지 않는다")
    ap.add_argument("--init-youtube-map", action="store_true", help="영상 매핑 골격 1회 생성")
    ap.add_argument("--prune", action="store_true",
                    help="예전 빌드가 남긴 06/videos/*.mp4 삭제 (원본은 05/*/draft/ 에 있다)")
    ap.add_argument("--no-strict-meta", dest="strict_meta", action="store_false",
                    help="02/ 메타 미발견을 경고로만 처리 (기본은 빌드 실패)")
    ap.set_defaults(strict_meta=True)
    args = ap.parse_args(argv)

    book = Path(args.book).resolve()

    if args.init_youtube_map:
        init_youtube_map(book, args.pd,
                         None if has_lessons(book)
                         else _bundles_from_meta(load_meta(book), args.part_size))
        return 0

    out = Path(args.out).resolve() if args.out else (book / "06")
    out.mkdir(parents=True, exist_ok=True)

    # ★ 문제집별 데이터 디렉터리 — 06/pd/<pd_id>/
    #
    #   왜 나누는가: 06/ 은 /www/exam/ 에 **납작하게** 복사된다(DEPLOY.md).
    #   두 번째 문제집을 빌드하면 problems.js · theory_content.js · videos.js · figs/ ·
    #   theory/ 가 전부 같은 이름이라 **첫 번째 문제집의 데이터를 덮어쓴다.**
    #   품목이 늘어나는 순간 터지는데, 덮어쓴 뒤에는 원인이 안 보인다.
    #
    #   공용(06/ 루트): index.html · detail.html · assets/ · brand.php
    #   문제집별(06/pd/<pd>/): problems.js · videos.js · theory.js · theory_content.js
    #                          · figs/ · theory/ · problems.json
    pdir = out / "pd" / args.pd
    pdir.mkdir(parents=True, exist_ok=True)

    if not PRESENT_ASSETS.is_dir():
        raise SystemExit(f"[error] 디자인 자산 없음: {PRESENT_ASSETS}")

    # 0) 02/ 메타 (과목·검수상태의 유일한 출처)
    meta = load_meta(book)
    if not meta:
        n_md = len(list((book / "02").glob("*.md")))
        raise SystemExit(
            f"[error] 02/ 메타를 못 읽었다: {book / '02'}\n"
            f"        그 폴더의 .md 파일 {n_md}개\n"
            "        · 0개면 #2(집필)가 아직 안 돌았다\n"
            "        · 있는데도 0건이면 **파일명이 'mNN-NN.md' 가 아니다** —\n"
            "          exam_meta.load_meta() 가 02/m*.md 만 읽는다.\n"
            "          OCR 산출물 이름('01-01.md')은 한 건도 잡히지 않는다.\n"
            "        → docs/편지-프로덕트2-3.md 의 #2 계약 참조")

    # 1) 디자인 자산 (fonts 는 CDN 이라 여기 없다)
    #    copytree(dirs_exist_ok=True) 는 소스에 없어진 파일을 지우지 않는다 →
    #    예전 빌드의 assets/fonts/PretendardVariable.woff2(2.06MB)가 남아서 그대로 배포된다.
    #    assets/ 는 빌드가 전적으로 소유하므로 매번 새로 만든다.
    if (out / "assets").exists():
        shutil.rmtree(out / "assets")
    shutil.copytree(PRESENT_ASSETS, out / "assets")

    # 2) 문제 수집 + 도식 SVG  → 06/pd/<pd>/figs/
    #
    #    출처가 둘이다. 05(영상 번들)가 있으면 그쪽이 우선 — SQLD 는 그 경로로
    #    300문제가 이미 DB 에 들어가 있고 `pr_key` 가 그 번들명에 묶여 있다.
    src = args.src if args.src != "auto" else ("05" if has_lessons(book) else "02")
    if src == "05":
        if not has_lessons(book):
            raise SystemExit(f"[error] --src 05 인데 lesson JSON 이 없다: {book / '05'}/*/source/")
        probs, copied, missing = collect(book, pdir / "figs", meta, strict=args.strict_meta)
        vbundles = None
    else:
        probs, copied, missing = collect_02(book, pdir / "figs", meta,
                                           strict=args.strict_meta, part_size=args.part_size)
        vbundles = _bundles_from_probs(probs)

    # 3) 영상 — 유튜브/링크 매핑. mp4 를 복사하지 않는다.
    vids, vfilled, vtotal, vpriv = map_videos(book, args.pd, vbundles)

    # 4) 이론(03 요약노트)  → 06/pd/<pd>/theory/
    theory, theory_html = build_theory(book, pdir, theory_videos(args.pd))

    # 5) 데이터 파일 — 전부 문제집별 디렉터리로
    (pdir / "problems.js").write_text(
        "window.PROBLEMS = " + json.dumps(probs, ensure_ascii=False) + ";\n", encoding="utf-8")
    (pdir / "videos.js").write_text(
        "window.VIDEOS = " + json.dumps(vids, ensure_ascii=False) + ";\n", encoding="utf-8")

    # 레벨 제한 영상 — **정적 파일로 내보내지 않는다.**
    # api/videos.php 가 파일시스템으로 읽어 로그인 레벨을 보고 내려준다.
    # /exam/.htaccess 의 <FilesMatch "\.(json|...)$"> 가 직접 조회를 이미 막고 있다.
    if vpriv:
        (pdir / "videos.private.json").write_text(
            json.dumps(vpriv, ensure_ascii=False, indent=1), encoding="utf-8")
    elif (pdir / "videos.private.json").exists():
        # 전부 공개로 바뀌었으면 남겨두지 않는다 — 낡은 링크가 서버에 계속 살아 있게 된다
        (pdir / "videos.private.json").unlink()
    (pdir / "theory.js").write_text(
        "window.THEORY = " + json.dumps(theory, ensure_ascii=False) + ";\n", encoding="utf-8")
    write_theory_content(pdir, theory_html)

    # 6) 화면
    #
    # ★ EXAM_CFG 를 **항상** 주입한다. 예전에는 --api-base 가 있을 때만 넣어서,
    #   로컬 미리보기(file://)가 어떤 품목을 빌드해도 템플릿의 'sqld' 폴백으로 떨어졌다.
    #   즉 로컬에서는 다른 문제집을 확인하는 것이 구조적으로 불가능했다.
    brand = load_brand()
    cfg = {
        "api":   args.api_base or "",
        "pd":    args.pd,
        "data":  f"pd/{args.pd}/",     # 정적 데이터 기준 경로. check.php 도 같은 값을 준다
        "brand": brand,
        # file:// 폴백용. 서버에서는 API 가 이긴다.
        "product": {
            "pd_id":    args.pd,
            "pd_name":  args.pd_name or args.pd.upper(),
            "problems": len(probs),
            "rounds":   len(set(p["round_num"] for p in probs if p["round_num"])),
            "subjects": [{"sj_no": i + 1, "sj_name": s}
                         for i, s in enumerate(sorted({p["subject"] for p in probs if p["subject"]}))],
        },
    }
    inject = ("<script>window.EXAM_CFG=" + json.dumps(cfg, ensure_ascii=False) + ";"
              # 구 이름 별칭 — 템플릿이 아직 이 둘을 참조한다. 한 릴리스만 유지한다.
              "window.EXAM_API=EXAM_CFG.api;window.EXAM_PD=EXAM_CFG.pd;</script>\n")

    # 브랜드 토큰. <title> 과 로고 마크업은 JS 로 바꿀 수 없다(바꿔도 깜빡인다).
    tokens = {
        "{{BRAND}}":      brand["brand"],
        "{{BRAND_HTML}}": brand["brand_html"],
        "{{TAGLINE}}":    brand["tagline"],
        "{{INTRO}}":      brand["intro"],
        # 정적 페이지의 상단 nav·CTA 가 가리킬 기본 문제집.
        # index.html·detail.html 은 공용 페이지라 DB 를 못 본다 — 빌드한 품목을 쓴다.
        # (품목별 링크는 카드/회차 목록이 데이터에서 만든다. nav 는 일반 진입점이다)
        "{{PD}}":         args.pd,
    }

    def emit(tpl: Path, name: str):
        if not tpl.exists():
            return False
        h = tpl.read_text(encoding="utf-8")
        for k, v in tokens.items():
            h = h.replace(k, v)
        # 오타 난 토큰이 그대로 배포되면 이용자가 {{BRND}} 를 본다. 빌드에서 죽인다.
        if "{{" in h:
            leftover = re.findall(r"\{\{[A-Z_]{2,}\}\}", h)
            if leftover:
                raise SystemExit(f"[브랜드] {tpl.name} 에 치환되지 않은 토큰: {sorted(set(leftover))}")
        h = h.replace("</head>", inject + "</head>", 1)
        (out / name).write_text(h, encoding="utf-8")
        return True

    n_pages = 0
    # 랜딩·상세는 있으면 굽는다 (없어도 빌드가 죽지 않게)
    if emit(LANDING, "index.html"):   n_pages += 1

    # ★ check.html 은 더 이상 굽지 않는다 — web/exam/check.php 로 옮겼다.
    #   과목게시판이 그누보드 게시판(PHP)이라 정적 HTML 안에 들어가지 않는다.
    #   예전 URL 이 문서·북마크·체크리스트에 남아 있으므로 리다이렉트만 남긴다.
    (out / "check.html").write_text(
        "<!DOCTYPE html><meta charset=\"utf-8\">"
        "<meta http-equiv=\"refresh\" content=\"0;url=check.php\">\n"
        "<p><a href=\"check.php\">문제풀이 화면으로 이동</a></p>\n",
        encoding="utf-8")
    n_pages += 1

    # ★ 상세는 품목별 파일이 아니라 detail.html 하나가 ?pd= 로 렌더한다.
    #   build_check.py 는 DB 를 못 보므로 품목 목록을 모른다(--pd 하나뿐).
    #   품목별로 구우려면 ex_product 의 사본을 로컬에 또 둬야 하고, 그러면
    #   "품목 추가 = DB 1행" 이라는 원칙이 깨진다.
    if emit(DETAIL, "detail.html"):   n_pages += 1

    # 예전 URL 보존 — /exam/sqld.html 이 문서·북마크·체크리스트에 남아 있다.
    # 파일명이 코드가 아니라 args.pd 로 정해지므로 품목이 늘어도 그대로 동작한다.
    if (out / "detail.html").exists():
        (out / f"{args.pd}.html").write_text(
            "<!DOCTYPE html><meta charset=\"utf-8\">"
            f"<meta http-equiv=\"refresh\" content=\"0;url=detail.html?pd={args.pd}\">\n"
            f"<p><a href=\"detail.html?pd={args.pd}\">이동</a></p>\n",
            encoding="utf-8")
        n_pages += 1

    # PHP 쪽 브랜드. 06/ → /www/exam/ 업로드에 같이 실려 간다.
    (out / "brand.php").write_text(
        "<?php\n"
        "/* build_check.py 가 data/brand.json 에서 생성한다. 손으로 고치지 않는다. */\n"
        f"$EX_BRAND      = {php_str(brand['brand'])};\n"
        f"$EX_BRAND_HTML = {php_str(brand['brand_html'])};\n"
        f"$EX_TAGLINE    = {php_str(brand['tagline'])};\n"
        f"$EX_INTRO      = {php_str(brand['intro'])};\n",
        encoding="utf-8")

    # 7) problems.json
    json_path = None
    if args.emit_json:
        # 문제집별 디렉터리에 둔다. 예전엔 06/problems.json 이라 두 번째 문제집이 덮어썼다.
        # (FTP 로 올리지 않는다 — adm/exam_import.php 화면 업로드다. DEPLOY.md §70)
        dest = Path(args.json_out).resolve() if args.json_out else (pdir / "problems.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        json_path = emit_json(probs, meta, args.pd, dest)

    # ── 옛 납작 레이아웃 잔존물 ─────────────────────────────
    #
    # 예전 빌드는 problems.js · figs/ 등을 06/ 루트에 만들었다. 이제 pd/<pd>/ 로 내려갔지만
    # **예전 파일이 그대로 남는다.** 그걸 두면:
    #   · FTP 업로드가 낡은 사본까지 올려 /www/exam/problems.js 가 공개 상태로 남는다
    #   · 상대경로로 떨어지는 버그가 조용히 낡은 데이터를 읽는다(정답이 다를 수 있다)
    # mp4 경고(아래)와 같은 부류이므로 같은 방식으로 처리한다.
    FLAT = ["problems.js", "videos.js", "theory.js", "theory_content.js", "problems.json"]
    FLAT_DIRS = ["figs", "theory"]
    flat_hit = [f for f in FLAT if (out / f).is_file()]
    flat_dir = [d for d in FLAT_DIRS if (out / d).is_dir()]

    if flat_hit or flat_dir:
        if args.prune:
            for f in flat_hit:
                (out / f).unlink()
            for d in flat_dir:
                shutil.rmtree(out / d)
            print(f"[flat]  옛 납작 파일 정리: {len(flat_hit)}개 + 폴더 {len(flat_dir)}개 삭제")
            print( "        ⚠ 서버에도 남아 있다. FTP 업로드는 지우지 않는다 —")
            print( "          /www/exam/ 의 problems.js · videos.js · theory.js ·")
            print( "          theory_content.js · figs/ · theory/ 를 손으로 지운다.")
        else:
            print(f"\n[FLAT]  옛 레이아웃 파일이 {out} 루트에 남아 있다:")
            if flat_hit: print(f"        파일 {', '.join(flat_hit)}")
            if flat_dir: print(f"        폴더 {', '.join(d + '/' for d in flat_dir)}")
            print( "        이제 정적 데이터는 pd/<품목>/ 아래에 있다. 위 사본은 낡은 것이다.")
            print( "        → 지우려면: python scripts/build_check.py --prune")

    write_upload_set(out, pdir, args.pd)

    # ── 리포트 ──────────────────────────────────────────────
    subj = sorted({p["subject"] for p in probs if p["subject"]})
    n_rounds = len(set(p["round_num"] for p in probs if p["round_num"]))
    n_vid = sum(len(v) for v in vids.values())
    print(f"[check] {len(probs)}문제 · {n_rounds}회 · 화면 {n_pages}개 → {out}")
    print(f"        본문 출처 {src}/"
          + ("  (05 lesson JSON)" if src == "05" else "  (집필 MD 직접 파싱 — 영상 없음)"))
    print(f"        과목 {len(subj)}종: {', '.join(subj) or '(없음)'}")
    # 브랜드·품목을 찍는다 — --pd-name 을 잘못 줘도 업로드 전에 눈에 보이게
    print(f"[brand] {brand['brand']}  ·  {brand['tagline']}")
    print(f"        품목 {args.pd} = {cfg['product']['pd_name']}"
          f"   → detail.html?pd={args.pd}  ({args.pd}.html 은 리다이렉트)")
    print(f"[data]  정적 데이터 → {pdir.relative_to(out).as_posix()}/  "
          f"(problems.js · videos.js · theory*.js · figs/ · theory/)")
    print( "        문제풀이 화면은 web/exam/check.php 다 — 이 빌드가 굽지 않는다.")
    print( "        06/check.html 은 check.php 로 보내는 리다이렉트만 남는다.")
    print(f"        지문 {sum(1 for p in probs if p['passage'])} · SQL {sum(1 for p in probs if p['sql'])}"
          f" · 표 {sum(1 for p in probs if p['table'])} · SVG {len(copied)}")
    print(f"        영상 {n_vid}개 매핑 ({vfilled}/{vtotal} 유튜브 ID 입력됨) · mp4 복사 없음")
    if args.api_base:
        print(f"        EXAM_API = {args.api_base}  (ApiDS 모드)")
    else:
        print("        EXAM_API 없음 → StaticDS (file:// 로컬 검수용)")
    if json_path:
        size_kb = json_path.stat().st_size / 1024
        print(f"[json]  {len(probs)}문제 → {json_path}  ({size_kb:,.0f} KB)")
        print("        adm/exam_import.php 에 업로드하면 upsert 된다.")
    if missing:
        print(f"[warn]  SVG 못 찾음 {len(missing)}: {', '.join(sorted(missing))}")
    if vfilled < vtotal:
        ymap = youtube_map_path(args.pd) or (ROOT / "data" / f"youtube_map.{args.pd}.json")
        print(f"[warn]  유튜브 ID 미입력 {vtotal - vfilled}개 — {ymap} 를 채운다"
              " (--init-youtube-map 으로 골격 생성)")

    # 예전 빌드가 남긴 mp4 — 이 빌드는 만들지 않지만 폴더가 남아 있으면 그대로 배포된다.
    # 카페24 뉴아우토반 일반형은 하드 1,400MB · 트래픽 4,000MB 다. 411MB 가 올라가면 끝난다.
    vdir = out / "videos"
    stale = sorted(vdir.glob("*.mp4")) if vdir.is_dir() else []
    if stale:
        mb = sum(f.stat().st_size for f in stale) / 1024 / 1024
        orig = len(list((book / "05").glob("*/draft/*.static.mp4")))
        print(f"\n[STALE] {out / 'videos'} 에 예전 빌드의 mp4 {len(stale)}개 ({mb:,.0f}MB)가 남아 있다.")
        print(f"        이 빌드는 mp4 를 복사하지 않는다. 그대로 두면 FTP 업로드 때 같이 올라간다.")
        print(f"        원본은 05/*/draft/ 에 {orig}개 그대로 있다"
              f"{' (전부 확인됨)' if orig >= len(stale) else ' ⚠ 개수 불일치 — 지우기 전에 확인할 것'}.")
        if args.prune:
            for f in stale:
                f.unlink()
            try:
                vdir.rmdir()
            except OSError:
                pass
            print(f"        → --prune: {len(stale)}개 삭제함. {mb:,.0f}MB 회수.")
        else:
            print("        → 지우려면: python scripts/build_check.py --prune")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
