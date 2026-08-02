"""axexam 필수 패치 3건 — 멱등. 두 번 돌려도 안전하다.

왜 이 세 개만인가: 나머지는 데이터·문서 상수이고, 이 셋은 **코드를 안 고치면
사고가 나거나 잘못된 파일이 나오는** 것들이다.

  1) --youtube-map 플래그 신설
     지금은 ROOT/data/youtube_map.json 하나를 모든 책이 공유한다. 번들 키가
     SQLD 의 m01-1…m06-5 와 우리 m01-1…m03-8 구간에서 **정면 충돌**한다.
     한 책을 빌드하면 다른 책의 영상 ID 를 덮어쓰거나 잘못 붙인다.

  2) 상세 페이지 출력 파일명 하드코딩 제거
     emit(DETAIL, "sqld.html") → emit(DETAIL, f"{args.pd}.html")
     지금 우리 책을 빌드하면 SQLD 마케팅 문구가 든 06/sqld.html 이 나오고,
     그걸 올리면 기존 SQLD 상세 페이지를 덮어쓴다.

  3) detail_template.html 파라미터화
     제목·문항수·회차수·과목 목록·모든 링크의 ?pd= 가 하드코딩돼 있다.
     치환 토큰으로 바꾸고 빌드가 값을 주입한다.

사용:
    venv\\Scripts\\python -m tools.patch_axexam            # 적용
    venv\\Scripts\\python -m tools.patch_axexam --check    # 상태만 확인
    venv\\Scripts\\python -m tools.patch_axexam --revert   # .xam.bak 에서 되돌리기
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

from core.constants import AXEXAM_DIR

BAK = ".xam.bak"


def _p(*parts: str) -> str:
    return os.path.join(AXEXAM_DIR, *parts)


def _read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write(path: str, text: str) -> None:
    if not os.path.isfile(path + BAK):
        shutil.copy2(path, path + BAK)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


# ── 패치 1: --youtube-map ────────────────────────────────────────────────────
P1_ARG_ANCHOR = ('    ap.add_argument("--init-youtube-map", action="store_true", '
                 'help="data/youtube_map.json 골격 1회 생성")\n')
P1_ARG_NEW = (
    '    ap.add_argument("--youtube-map", default="",\n'
    '                    help="품목별 유튜브 매핑 경로 (기본: data/youtube_map.json). "\n'
    '                         "★ 번들 키가 책마다 겹치므로 2개 이상 품목을 다루면 필수")\n'
)

P1_MAIN_ANCHOR = "    args = ap.parse_args(argv)\n"
P1_MAIN_NEW = (
    "    args = ap.parse_args(argv)\n"
    "\n"
    "    # ★ 품목별 유튜브 매핑. 공용 파일 하나를 쓰면 번들 키(m01-1 …)가 책마다\n"
    "    #   겹쳐서 서로의 영상 ID 를 덮어쓴다. 경로는 저장소 기준 상대경로도 받는다.\n"
    "    if args.youtube_map:\n"
    "        global YOUTUBE_MAP\n"
    "        _ym = Path(args.youtube_map)\n"
    "        YOUTUBE_MAP = _ym if _ym.is_absolute() else (ROOT / _ym)\n"
    "        print(f\"[youtube] 매핑 파일: {YOUTUBE_MAP}\")\n"
)


def patch1(check: bool) -> tuple[bool, str]:
    path = _p("scripts", "build_check.py")
    if not os.path.isfile(path):
        return False, f"없음: {path}"
    src = _read(path)
    if "--youtube-map" in src:
        return True, "이미 적용됨"
    if check:
        return False, "미적용"
    if P1_ARG_ANCHOR not in src:
        return False, "앵커를 찾지 못했습니다(--init-youtube-map 인자 줄). 수동 확인 필요."
    if P1_MAIN_ANCHOR not in src:
        return False, "앵커를 찾지 못했습니다(args = ap.parse_args). 수동 확인 필요."
    src = src.replace(P1_ARG_ANCHOR, P1_ARG_ANCHOR + P1_ARG_NEW, 1)
    src = src.replace(P1_MAIN_ANCHOR, P1_MAIN_NEW, 1)
    _write(path, src)
    return True, "적용"


# ── 패치 2: {pd}.html ───────────────────────────────────────────────────────
P2_OLD = 'if emit(DETAIL, "sqld.html"):    n_pages += 1'
P2_NEW = ('if emit(DETAIL, f"{args.pd}.html"):  n_pages += 1   '
          '# ★ 품목별 파일명 (예전엔 sqld.html 고정)')


def patch2(check: bool) -> tuple[bool, str]:
    path = _p("scripts", "build_check.py")
    if not os.path.isfile(path):
        return False, f"없음: {path}"
    src = _read(path)
    if 'f"{args.pd}.html"' in src:
        return True, "이미 적용됨"
    if check:
        return False, "미적용"
    if P2_OLD not in src:
        return False, "앵커를 찾지 못했습니다(emit(DETAIL, \"sqld.html\")). 수동 확인 필요."
    _write(path, src.replace(P2_OLD, P2_NEW, 1))
    return True, "적용"


# ── 패치 3: detail_template.html 파라미터화 ─────────────────────────────────
# 치환 토큰 → build_check.py 가 주입한다.
P3_SUBS = [
    ("<title>SQLD 문제집 — AXEXAM</title>", "<title>{{PD_LABEL}} 문제집 — AXEXAM</title>"),
    ("<h1>SQLD 문제집</h1>", "<h1>{{PD_LABEL}} 문제집</h1>"),
    ("모의고사 6회차 300문제.", "모의고사 {{ROUNDS}}회차 {{QUESTIONS}}문제."),
    ("<p>회차당 50문제.", "<p>회차당 {{PER_ROUND}}문제."),
    ('<div class="dt-fact"><b>2</b><span>과목</span></div>',
     '<div class="dt-fact"><b>{{SUBJECTS}}</b><span>과목</span></div>'),
]
# 과목 링크 2줄 → 자리표시자 1개
P3_SUBJ_OLD = (
    '      <a href="/exam/check.html?pd=sqld&m=theory">'
    '<svg class="ic"><use href="#i-book"></use></svg>1과목 · 데이터 모델링의 이해</a>\n'
    '      <a href="/exam/check.html?pd=sqld&m=theory">'
    '<svg class="ic"><use href="#i-book"></use></svg>2과목 · SQL 기본 및 활용</a>\n'
)
P3_SUBJ_NEW = "{{SUBJECT_LINKS}}\n"

# build_check.py 의 emit() 에 토큰 치환을 더한다.
P3_EMIT_OLD = """    def emit(tpl: Path, name: str):
        if not tpl.exists():
            return False
        h = tpl.read_text(encoding="utf-8")
        if inject:
            h = h.replace("</head>", inject + "</head>", 1)
        (out / name).write_text(h, encoding="utf-8")
        return True
"""
P3_EMIT_NEW = '''    # ★ 상세 페이지 치환 토큰. 품목마다 제목·문항수·과목 목록이 다르다.
    _subj = load_subjects(meta)
    _n_rounds = len({p["round_num"] for p in probs}) or 1
    _links = "\\n".join(
        f'      <a href="/exam/check.html?pd={args.pd}&m=theory">'
        f'<svg class="ic"><use href="#i-book"></use></svg>'
        f'{s["sj_no"]}과목 · {s["sj_name"]}</a>'
        for s in _subj)
    _tokens = {
        "{{PD}}": args.pd,
        "{{PD_LABEL}}": _pd_label(args.pd),
        "{{QUESTIONS}}": str(len(probs)),
        "{{ROUNDS}}": str(_n_rounds),
        "{{PER_ROUND}}": str(len(probs) // _n_rounds if _n_rounds else len(probs)),
        "{{SUBJECTS}}": str(len(_subj)),
        "{{SUBJECT_LINKS}}": _links,
    }

    def emit(tpl: Path, name: str):
        if not tpl.exists():
            return False
        h = tpl.read_text(encoding="utf-8")
        if inject:
            h = h.replace("</head>", inject + "</head>", 1)
        for k, v in _tokens.items():
            h = h.replace(k, v)
        # 남은 ?pd=sqld 하드코딩도 현재 품목으로 맞춘다(랜딩·상세 공통).
        if args.pd != "sqld":
            h = h.replace("pd=sqld", f"pd={args.pd}")
        (out / name).write_text(h, encoding="utf-8")
        return True
'''

P3_LABEL_FN = '''

# 품목 코드 → 사람이 읽는 이름. 상세 페이지 제목에 쓴다.
# 새 품목을 넣을 때 여기 한 줄만 더한다(없으면 코드를 대문자로 보여준다).
_PD_LABELS = {
    "sqld": "SQLD",
    "bigdata": "빅데이터분석기사 필기",
    "adsp": "ADSP",
    "gisa-w": "정보처리기사 필기",
}


def _pd_label(pd: str) -> str:
    return _PD_LABELS.get(pd, pd.upper())
'''


def patch3(check: bool) -> tuple[bool, str]:
    tpl = _p("scripts", "detail_template.html")
    bc = _p("scripts", "build_check.py")
    if not (os.path.isfile(tpl) and os.path.isfile(bc)):
        return False, "파일 없음"
    t = _read(tpl)
    s = _read(bc)
    done_t = "{{PD_LABEL}}" in t
    done_s = "_pd_label" in s
    if done_t and done_s:
        return True, "이미 적용됨"
    if check:
        return False, f"미적용 (템플릿 {'O' if done_t else 'X'} / 빌드 {'O' if done_s else 'X'})"

    if not done_t:
        missing = [old for old, _new in P3_SUBS if old not in t]
        if missing:
            return False, f"템플릿 앵커 {len(missing)}개를 찾지 못했습니다: {missing[0][:40]}…"
        for old, new in P3_SUBS:
            t = t.replace(old, new, 1)
        if P3_SUBJ_OLD in t:
            t = t.replace(P3_SUBJ_OLD, P3_SUBJ_NEW, 1)
        else:
            # 줄바꿈/공백이 다를 수 있다 — 개별 줄로 시도
            import re
            t2, n = re.subn(
                r'[ \t]*<a href="/exam/check\.html\?pd=sqld&m=theory">.*?</a>\n',
                "", t, flags=re.S)
            if n:
                t = t2.replace("{{SUBJECTS}}</span></div>",
                               "{{SUBJECTS}}</span></div>", 1)
                # 자리표시자를 이론 섹션에 넣는다
                t = t.replace("</section>", P3_SUBJ_NEW + "</section>", 1)
            else:
                return False, "과목 링크 앵커를 찾지 못했습니다. 수동 확인 필요."
        _write(tpl, t)

    if not done_s:
        if P3_EMIT_OLD not in s:
            return False, "build_check.py 의 emit() 앵커를 찾지 못했습니다. 수동 확인 필요."
        s = s.replace(P3_EMIT_OLD, P3_EMIT_NEW, 1)
        # _pd_label 을 main 위쪽 모듈 레벨에 넣는다
        anchor = "\ndef main("
        if anchor not in s:
            return False, "build_check.py 의 main() 을 찾지 못했습니다."
        s = s.replace(anchor, P3_LABEL_FN + anchor, 1)
        _write(bc, s)

    return True, "적용"


PATCHES = [
    ("1. --youtube-map 플래그 (품목별 매핑 — 번들 키 충돌 방지)", patch1),
    ("2. 상세 페이지 출력 파일명 {pd}.html", patch2),
    ("3. detail_template.html 파라미터화", patch3),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="patch_axexam")
    ap.add_argument("--check", action="store_true", help="상태만 확인(쓰지 않음)")
    ap.add_argument("--revert", action="store_true", help=f"{BAK} 에서 되돌리기")
    args = ap.parse_args(argv)

    print(f"axexam: {AXEXAM_DIR}")
    if not os.path.isdir(AXEXAM_DIR):
        print("[error] axexam 저장소가 없습니다.\n"
              "  git clone https://github.com/leedonwoo2827-ship-it/axexam "
              f'"{AXEXAM_DIR}"')
        return 2

    if args.revert:
        n = 0
        for root, _d, files in os.walk(_p("scripts")):
            for f in files:
                if f.endswith(BAK):
                    src = os.path.join(root, f)
                    shutil.copy2(src, src[: -len(BAK)])
                    os.remove(src)
                    print(f"  되돌림: {f[:-len(BAK)]}")
                    n += 1
        print(f"{n}개 파일을 되돌렸습니다." if n else "되돌릴 백업이 없습니다.")
        return 0

    fails = 0
    for label, fn in PATCHES:
        ok, msg = fn(args.check)
        mark = "OK  " if ok else "FAIL"
        print(f"  [{mark}] {label} — {msg}")
        if not ok:
            fails += 1

    if args.check:
        print("\n확인만 했습니다. 적용하려면 --check 없이 다시 실행하세요.")
        return 1 if fails else 0

    if fails:
        print(f"\n{fails}개 패치를 적용하지 못했습니다. 위 메시지를 확인하세요.")
        return 1

    # 문법 확인 — 우리가 고친 파일이 실제로 import 가능한지
    import py_compile
    try:
        py_compile.compile(_p("scripts", "build_check.py"), doraise=True)
        print("\nbuild_check.py 문법 확인 OK")
    except py_compile.PyCompileError as e:
        print(f"\n[error] 패치 후 문법 오류: {e}")
        return 2

    print(f"\n적용 완료. 원본은 *{BAK} 로 남아 있습니다.\n"
          "되돌리려면: python -m tools.patch_axexam --revert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
