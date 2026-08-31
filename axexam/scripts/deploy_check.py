"""서버에 뭐가 올라갔고 뭐가 안 올라갔나 — 공개 URL 만으로 판정한다.

왜 있는가
---------
"어제 업로드를 끝냈나?" 를 손으로 확인하면 30분이 걸리고, 빠뜨린 파일은
**증상이 나중에 다른 얼굴로 나타난다**(성적표 버튼이 안 보이는데 원인은 check.php 다).
FTP 는 "올렸다"는 기록을 남기지 않으므로 서버에 물어보는 것이 유일한 진실이다.

세 가지를 본다.

1. **있어야 할 것 / 없어야 할 것** — HTTP 상태코드
   삭제해야 하는 것(옛 납작 사본·`exam_migrate.php`)이 남아 있는 것도 잡는다.
   FTP 업로드는 지워주지 않으므로 이쪽이 실제로 자주 틀린다.
2. **정적 파일 md5 대조** — 로컬 ↔ 서버.
   FileZilla 가 CRLF→LF 로 바꿔 올리므로 **`\\r` 을 지우고 비교한다.**
   크기 비교로는 판정할 수 없다(줄 수만큼 작아지는 게 정상이다).
3. **PHP 는 소스가 안 나온다** → 렌더 결과에 있어야 할 표식으로 버전을 판정한다.
   예: `check.php` 의 `id="rpLink"` 가 없으면 성적표 이전 버전이다.

사용:
    python scripts/deploy_check.py                    # 전부
    python scripts/deploy_check.py --pd bdae-w        # 다른 문제집
    python scripts/deploy_check.py --only api         # status | md5 | marker | api
    python scripts/deploy_check.py --base http://…    # 다른 서버

종료 코드: 실패가 하나라도 있으면 1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
BUILD = Path("D:/00work/ocr-output-260723/06")     # 06/ 빌드 산출물 (--build 로 변경)
BASE = "https://axexam.mycafe24.com"
TIMEOUT = 20

# ── 1. 상태코드 ─────────────────────────────────────────────────
#
# 200  있어야 한다
# 404  없어야 한다 (지웠어야 하는 것)
# 403  .htaccess 가 막고 있어야 한다
# 30x  리다이렉트가 걸려 있어야 한다
STATUS = [
    # 화면
    ("/",                          (301, 302), "루트 → /exam/ 리다이렉트"),
    ("/exam/",                     (200,),     "랜딩"),
    ("/exam/detail.html",          (200,),     "문제집 상세"),
    ("/exam/check.php",            (200,),     "문제풀이 (4탭)"),
    ("/exam/check.html",           (200,),     "옛 URL → check.php 리다이렉트 문서"),
    ("/exam/buy.php",              (200,),     "수강 신청"),
    ("/exam/mypage.php",           (200, 302), "마이페이지 (비로그인은 302)"),
    ("/exam/report.php",           (200, 302), "★ 성적표 (비로그인은 302)"),
    # API — 파라미터 없이 부르면 400 이 정상이다. 404 면 파일이 없는 것이다.
    ("/exam/api/products.php",     (200,),     "품목 목록"),
    ("/exam/api/problems.php",     (200, 400), "문제"),
    ("/exam/api/me.php",           (200,),     "내 상태"),
    ("/exam/api/board.php",        (200, 400), "과목게시판"),
    ("/exam/api/videos.php",       (200, 400), "해설영상"),
    ("/exam/api/report.php",       (200, 400, 401, 403), "★ 성적표 API"),
    ("/exam/api/grade.php",        (200, 400, 405), "서버 채점"),
    ("/exam/api/wrong.php",        (200, 400, 401, 403), "오답노트"),
    ("/exam/api/attempts.php",     (200, 400, 401, 403), "응시 이력"),
    # 정적 자산
    ("/exam/assets/axnav.css",     (200,),     "공통 헤더"),
    ("/exam/assets/check.css",     (200,),     "문제풀이 CSS"),
    ("/exam/assets/check.js",      (200,),     "문제풀이 JS"),
    ("/exam/assets/mypage.css",    (200,),     "마이페이지 CSS"),
    ("/exam/assets/mypage.js",     (200,),     "마이페이지 JS"),
    ("/exam/assets/report.css",    (200,),     "★ 성적표 CSS"),
    ("/exam/assets/report.js",     (200,),     "★ 성적표 JS"),
    ("/exam/assets/gnuboard-skin.css", (200,), "그누보드 화면 스킨 (푸터 그리드)"),
    # 지워야 했던 것 — FTP 업로드는 지워주지 않는다
    ("/exam/problems.js",          (404, 403), "옛 납작 사본 (정답이 박혀 있다)"),
    ("/exam/videos.js",            (404, 403), "옛 납작 사본"),
    ("/exam/theory.js",            (404, 403), "옛 납작 사본"),
    ("/exam/theory_content.js",    (404, 403), "옛 납작 사본"),
    ("/exam_migrate.php",          (404, 403), "★ 마이그레이션 스크립트 (보안)"),
    ("/exam_demo_qna.php",         (404, 403), "예시글 스크립트 (썼으면 지운다)"),
    # .htaccess 가 막아야 하는 것
    ("/exam/pd/{pd}/problems.json", (403, 404), "문제 JSON 직접 조회 차단"),
    ("/exam/sql/migrate-001-multipd.sql", (403, 404), "SQL 파일 차단"),
    # 품목별 정적 데이터
    ("/exam/pd/{pd}/theory_content.js", (200,), "이론 본문"),
    ("/exam/pd/{pd}/theory.js",    (200,),     "이론 목록"),
    ("/exam/pd/{pd}/videos.js",    (200,),     "영상 매핑"),
]

# ── 2. md5 대조 (로컬 → 서버) ────────────────────────────────────
#
# PHP 는 넣지 않는다 — 응답이 실행 결과라서 소스와 비교할 수 없다. 그건 §3 이 본다.
COMPARE = [
    (WEB / "exam/assets/axnav.css",         "/exam/assets/axnav.css"),
    (WEB / "exam/assets/check.css",         "/exam/assets/check.css"),
    (WEB / "exam/assets/check.js",          "/exam/assets/check.js"),
    (WEB / "exam/assets/mypage.css",        "/exam/assets/mypage.css"),
    (WEB / "exam/assets/mypage.js",         "/exam/assets/mypage.js"),
    (WEB / "exam/assets/report.css",        "/exam/assets/report.css"),
    (WEB / "exam/assets/report.js",         "/exam/assets/report.js"),
    (WEB / "exam/assets/gnuboard-skin.css", "/exam/assets/gnuboard-skin.css"),
    # 테마 CSS 도 본다. 여기 있던 `#hd,#wrapper,#ft{min-width:1200px}` 과
    # `#container{width:930px}` 이 폰에서 오른쪽을 잘라먹던 원인이었다(26-08-31 수정).
    # 목록에 없으면 옛 파일이 서버에 남아도 아무도 모른다 — 화면이 "그냥 작게" 보일 뿐이다.
    (WEB / "theme/axexam/css/default.css",  "/theme/axexam/css/default.css"),
    # features.css·features.php 가 목록에 없었다 — 고쳐도 올렸는지 확인해 줄 장치가
    # 없어서 조용히 옛 파일이 남는다(실제로 캡처 경로 버그가 그렇게 오래 남았다).
    (WEB / "exam/assets/features.css",      "/exam/assets/features.css"),
    (BUILD / "assets/ui.js",                "/exam/assets/ui.js"),
    (BUILD / "index.html",                  "/exam/index.html"),
    (BUILD / "detail.html",                 "/exam/detail.html"),
    (BUILD / "check.html",                  "/exam/check.html"),
    (BUILD / "pd/{pd}/theory.js",           "/exam/pd/{pd}/theory.js"),
    (BUILD / "pd/{pd}/theory_content.js",   "/exam/pd/{pd}/theory_content.js"),
    (BUILD / "pd/{pd}/videos.js",           "/exam/pd/{pd}/videos.js"),
]

# ── 3. 렌더 결과 표식 (PHP 버전 판정) ────────────────────────────
MARKERS = [
    # ★ 이것이 없으면 **모바일 CSS 가 통째로 안 걸린다.**
    #   viewport meta 가 theme/axexam/head.sub.php 의 `if (G5_IS_MOBILE)` 안에 있었고
    #   theme.config.php:13 이 G5_THEME_DEVICE='pc' 로 못박아서, 어느 페이지에도
    #   나가지 않았다(실측: 데스크톱 0건 · iPhone 0건). 폰에서 layout viewport 가
    #   980px 로 잡혀 @media(max-width:920/760/640) 이 한 번도 안 걸렸다.
    #   에러가 안 나고 "그냥 작게 보이는" 것이라 사람이 못 잡는다 — 그래서 여기 둔다.
    ("/exam/check.php?pd={pd}", 'id="meta_viewport"',
     "★ viewport meta — 없으면 모바일 CSS 가 통째로 안 걸린다"),
    ("/exam/check.php?pd={pd}", 'viewport-fit=cover',
     "★ safe-area — 없으면 env(safe-area-inset-*) 가 항상 0px, 하단 시트가 홈 인디케이터에 깔린다"),
    ("/exam/check.php?pd={pd}", 'id="rpLink"',
     "★ 성적표 링크 자리 — 없으면 check.php 가 07-30 13:52 이전 버전"),
    ("/exam/check.php?pd={pd}", "과목게시판", "4탭 (홈·이론·문제집·과목게시판)"),
    ("/exam/check.php?pd={pd}", "성적표 샘플", "상단 nav 샘플 메뉴 (head.php)"),
    ("/exam/", "XAMpass", "브랜딩"),
    ("/exam/", "data-authswap", "정적 헤더 로그인상태 스왑 표식"),
    ("/exam/", "주요 기능", "푸터 자랑 2열 (정적 — landing_template.html)"),
    # ⚠ 푸터가 두 곳에 있다. PHP 화면은 theme/axexam/tail.php 를 쓴다 —
    #   한쪽만 올리면 화면을 옮겨 다니면서 푸터가 달라진다(실제로 그렇게 어긋났다).
    ("/exam/check.php?pd={pd}", "주요 기능", "푸터 자랑 2열 (PHP — theme/axexam/tail.php)"),
    ("/exam/report.php?pd={pd}&sample=1", "rp-demo", "★ 성적표 샘플 — 비로그인도 열려야 한다"),
    ("/exam/mypage.php?pd={pd}&sample=1", "rp-demo", "★ 마이페이지 샘플 — 비로그인도 열려야 한다"),
]

# ── 4. API 응답 단정 ────────────────────────────────────────────
#   "화면이 뜬다" 와 "데이터가 맞다" 는 다르다. 재임포트를 했는지는 회차 라벨로만 안다.


def check_api(get, pd: str) -> list[tuple[bool, str, str]]:
    out: list[tuple[bool, str, str]] = []

    st, body = get(f"/exam/api/products.php")
    try:
        d = json.loads(body)
        items = {i["pd_id"]: i for i in d.get("items") or []}
        out.append((bool(items), "products.php", f"품목 {len(items)}종: {', '.join(items) or '없음'}"))
        me = items.get(pd)
        if me:
            out.append((me.get("problems", 0) > 0, f"products[{pd}].problems",
                        f"{me.get('problems')}문제 · {me.get('rounds')}회 · open={me.get('open')}"))
        else:
            out.append((False, f"products[{pd}]", "그 품목이 목록에 없다 — ex_product 를 확인한다"))
    except (ValueError, KeyError, TypeError) as e:
        out.append((False, "products.php", f"JSON 파싱 실패: {e}"))

    st, body = get(f"/exam/api/problems.php?pd={pd}")
    try:
        d = json.loads(body)
        probs = d.get("problems") or []
        rounds = d.get("rounds") or []
        subs = d.get("subjects") or []
        out.append((len(probs) > 0, f"problems.php?pd={pd}", f"{len(probs)}문제"))
        out.append((len(subs) >= 2, "  과목",
                    f"{len(subs)}종: {', '.join(s.get('sj_name', '') for s in subs)}"))
        labels = [r.get("label", "") for r in rounds]
        # 재임포트를 안 했으면 라벨에 '자사' 가 남아 있다 — 이게 유일한 외부 판별법이다
        stale = [x for x in labels if x.startswith("자사")]
        out.append((not stale, "  회차 라벨",
                    f"{len(rounds)}회 — {', '.join(labels[:3])}{' …' if len(labels) > 3 else ''}"
                    + (f"  ⚠ '자사' 접두어 {len(stale)}건: 재임포트를 아직 안 했다" if stale else "")))
        free = [r.get("no") for r in rounds if r.get("free")]
        out.append((True, "  무료 회차", f"{len(free)}/{len(rounds)}회 무료 (성적표 열람 정책)"))
    except (ValueError, KeyError, TypeError) as e:
        out.append((False, f"problems.php?pd={pd}", f"JSON 파싱 실패: {e}"))

    st, body = get(f"/exam/api/board.php?pd={pd}")
    try:
        d = json.loads(body)
        bt = d.get("bo_table") or ""
        cats = d.get("categories") or []
        made = bool(cats)          # 게시판이 없으면 categories 가 비거나 ok=0 이다
        out.append((made, f"board.php?pd={pd}",
                    f"bo_table={bt or '?'} · 말머리 {len(cats)}개"
                    + ("" if made else "  ⚠ 게시판을 아직 안 만들었다 (adm/board_list.php)")))
        out.append((True, "  게시글", f"{len(d.get('items') or [])}건"))
    except (ValueError, KeyError, TypeError) as e:
        out.append((False, f"board.php?pd={pd}", f"JSON 파싱 실패: {e}"))

    return out


# ── 실행 ────────────────────────────────────────────────────────

def make_get(base: str):
    def get(path: str) -> tuple[int, str]:
        req = urllib.request.Request(base + path, headers={"User-Agent": "deploy_check/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            return 0, f"__NETWORK__ {e.reason}"
    return get


def make_get_raw(base: str):
    """리다이렉트를 따라가지 않는 GET — 30x 자체를 봐야 하는 항목용."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    op = urllib.request.build_opener(NoRedirect)

    def get(path: str) -> tuple[int, bytes]:
        req = urllib.request.Request(base + path, headers={"User-Agent": "deploy_check/1.0"})
        try:
            with op.open(req, timeout=TIMEOUT) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except urllib.error.URLError as e:
            return 0, str(e.reason).encode()
    return get


def norm(b: bytes) -> str:
    """개행 정규화 후 md5. FileZilla 가 CRLF→LF 로 바꿔 올린다."""
    return hashlib.md5(b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="deploy_check.py",
                                description="서버 업로드·삭제 누락을 공개 URL 로 검출한다")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--pd", default="sqld", help="문제집 코드 (ex_product.pd_id)")
    ap.add_argument("--build", default=str(BUILD), help="06/ 빌드 산출물 경로")
    ap.add_argument("--only", choices=("status", "md5", "marker", "api"), action="append",
                    help="일부만 실행 (여러 번 지정 가능)")
    args = ap.parse_args(argv)
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    run = set(args.only or ("status", "md5", "marker", "api"))
    pd = args.pd
    build = Path(args.build)
    get_txt = make_get(args.base)
    get_raw = make_get_raw(args.base)
    fails: list[str] = []
    net_down = False

    print(f"■ {args.base}  ·  문제집 {pd}\n")

    if "status" in run:
        print("── 상태코드 ─────────────────────────────────────────────")
        for path, want, note in STATUS:
            p = path.replace("{pd}", pd)
            code, body = get_raw(p)
            if code == 0:
                net_down = True
            ok = code in want
            mark = "OK  " if ok else "FAIL"
            print(f"{mark} {code:>3}  {p:<44} {note}")
            if not ok:
                fails.append(f"{p} → {code} (기대 {want}) · {note}")
        print()

    if "md5" in run and not net_down:
        print("── 정적 파일 로컬 ↔ 서버 (개행 정규화 md5) ──────────────")
        for lp, path in COMPARE:
            local = Path(str(lp).replace("{pd}", pd))
            p = path.replace("{pd}", pd)
            if not local.exists():
                print(f"SKIP      {p:<44} 로컬에 없다: {local}")
                continue
            code, body = get_raw(p)
            if code != 200:
                print(f"FAIL {code:>3}  {p:<44} 서버에 없다 → 업로드 필요")
                fails.append(f"{p} → {code} · 업로드 필요")
                continue
            same = norm(local.read_bytes()) == norm(body)
            print(f"{'SAME' if same else 'DIFF'}      {p:<44}"
                  f" local={local.stat().st_size:,}B server={len(body):,}B")
            if not same:
                fails.append(f"{p} · 서버가 낡았다 → {local} 를 올린다")
        print()

    if "marker" in run and not net_down:
        print("── 렌더 결과 표식 (PHP 버전 판정) ───────────────────────")
        cache: dict[str, str] = {}
        for path, needle, note in MARKERS:
            p = path.replace("{pd}", pd)
            if p not in cache:
                cache[p] = get_txt(p)[1]
            ok = needle in cache[p]
            print(f"{'OK  ' if ok else 'FAIL'}      {p:<44} '{needle}' — {note}")
            if not ok:
                fails.append(f"{p} 에 '{needle}' 가 없다 · {note}")
        print()

    if "api" in run and not net_down:
        print("── API 응답 ─────────────────────────────────────────────")
        for ok, name, detail in check_api(get_txt, pd):
            print(f"{'OK  ' if ok else 'FAIL'}      {name:<44} {detail}")
            if not ok:
                fails.append(f"{name} · {detail}")
        print()

    if net_down:
        print("⚠ 네트워크에 닿지 않는다 — 서버 확인을 건너뛰었다.")
        return 2
    if fails:
        print(f"■ 실패 {len(fails)}건")
        for f in fails:
            print(f"  · {f}")
        return 1
    print("■ 전부 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
