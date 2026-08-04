"""FTP 업로드 목록 — 06/ 중 올릴 것과 올리지 않을 것.

docs/DEPLOY.md 의 경로 매핑과 "올리면 안 되는 것" 을 그대로 따른다.

★ problems.json 은 FTP 로 올리지 않는다. /adm/exam_import.php 화면 업로드다
  (서버가 처리 후 즉시 지운다). 게다가 /exam/.htaccess 가 .json 을 403 으로 막아서
  올려도 읽히지 않는다.
★ mp4 는 올리지 않는다. 영상은 유튜브 embed 로 나간다 — 카페24 뉴아우토반 일반형은
  하드 1,400MB · 트래픽 4,000MB 라서 411MB 를 올리면 사이트가 정지한다.
"""
from __future__ import annotations

import hashlib
import os
import re

from core.constants import BASE_DIR, SITE_BASE, SITE_PATH
from services.book import paths

# 올릴 것 — 06/ 안의 파일·폴더
# 공용(품목 무관) — 06/ 바로 아래.
# `detail.html`·`brand.php` 가 빠져 있었다 — 상세 페이지와 브랜드 조각이라
# 없으면 문제집 상세가 404 다. 빌드 산출물을 실측해 채웠다.
UPLOAD_FILES = ("index.html", "detail.html", "check.html", "brand.php",
                "problems.js", "videos.js", "theory.js", "theory_content.js")
UPLOAD_DIRS = ("assets", "figs", "theory")

# ★ 품목별 데이터는 `06/pd/<pd>/` 에 있다 — 이 트리를 빠뜨리면 **문항도 영상도 안 올라간다.**
#
#   빌더가 품목별로 갈라 두었다(problems.js · videos.js · videos.private.json ·
#   theory.js · theory_content.js · figs/ · theory/). 품목이 하나였던 시절에는 전부
#   06/ 바로 아래(평면)에 있었고 위 두 상수가 그 시절 이름이다. 지금 빌더는 평면 사본을
#   오히려 지우라고 경고한다 — 두 문제집이 서로를 덮어쓰기 때문이다.
#   그래서 위 목록만 올리면 check.html·index.html·assets/ 만 올라가고 데이터가 빠진다.
UPLOAD_PD_DIR = "pd"

# `pd/<pd>/` 안에서도 이건 올리지 않는다 — 관리자 화면으로 임포트하는 파일이다.
PD_SKIP_NAMES = ("problems.json",)

# 올리지 않을 것 (이유를 함께 보여준다)
SKIP_REASONS = {
    "problems.json": "FTP 아님 — /adm/exam_import.php 화면에서 업로드합니다. "
                     "게다가 .htaccess 가 .json 을 403 으로 막습니다.",
    ".mp4": "영상은 유튜브 embed 로 나갑니다. 서버에 mp4 를 두지 않습니다.",
    "videos": "예전 빌드의 mp4 폴더입니다. --prune 이 정리합니다.",
}


def _sha256(path: str, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def build(*, with_hash: bool = False) -> dict:
    out = paths.out_dir()
    if not os.path.isdir(out):
        return {"ok": False, "out": out, "error": "06/ 가 없습니다. 먼저 빌드하세요.",
                "upload": [], "skip": []}

    upload, skip = [], []

    def add_file(rel: str, abs_path: str, *, server: str = "", source: str = "06/") -> None:
        r = rel.replace("\\", "/")
        sp = server or (SITE_PATH + r)
        rec = {
            "path": r,
            "server_path": sp,
            "url": SITE_BASE + sp,
            "bytes": os.path.getsize(abs_path),
            "source": source,        # 어느 로컬 트리에서 오는지 (06/ 인가 axexam/web/ 인가)
            "local": abs_path,
        }
        if with_hash:
            rec["sha256"] = _sha256(abs_path)
        upload.append(rec)

    for name in UPLOAD_FILES:
        p = os.path.join(out, name)
        if os.path.isfile(p):
            add_file(name, p)
    # ★ 품목 코드는 **활성 폴더**에서 읽는다. core.constants.PD_CODE 는 .env 값이라
    #   폴더를 바꿨을 때 갈린다 — 그러면 엉뚱한 품목 트리를 올린다.
    from services.publish import buildcheck
    PD_CODE = buildcheck.active_pd()
    # 품목 상세 페이지 — axexam 패치 2번 이후 {pd}.html 로 나온다.
    for name in (f"{PD_CODE}.html", "sqld.html"):
        p = os.path.join(out, name)
        if not os.path.isfile(p):
            continue
        if name == "sqld.html" and PD_CODE != "sqld":
            skip.append({"path": name, "bytes": os.path.getsize(p),
                         "reason": "SQLD 마케팅 문구가 든 파일입니다. axexam 패치 2번"
                                   "(출력 파일명을 {pd}.html 로) 이 적용되지 않았습니다. "
                                   "올리면 기존 SQLD 상세 페이지를 덮어씁니다."})
            continue
        add_file(name, p)

    for d in UPLOAD_DIRS:
        base = os.path.join(out, d)
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for f in sorted(files):
                p = os.path.join(root, f)
                add_file(os.path.relpath(p, out), p)

    # 품목별 트리 — 이게 실제 데이터다(문항·영상·이론·그림).
    pd_base = os.path.join(out, UPLOAD_PD_DIR, PD_CODE)
    if os.path.isdir(pd_base):
        for root, _dirs, files in os.walk(pd_base):
            for f in sorted(files):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, out)
                if f in PD_SKIP_NAMES:
                    skip.append({"path": rel.replace("\\", "/"),
                                 "bytes": os.path.getsize(p),
                                 "reason": SKIP_REASONS["problems.json"]})
                    continue
                add_file(rel, p)
    else:
        skip.append({"path": f"{UPLOAD_PD_DIR}/{PD_CODE}/", "bytes": 0,
                     "reason": ("빌드 산출물에 이 품목 폴더가 없습니다. "
                                f"--pd {PD_CODE} 로 빌드했는지 확인하세요 — "
                                "이 트리가 없으면 문항도 영상도 서버에 올라가지 않습니다.")})

    # 다른 품목 폴더는 건드리지 않는다(SQLD 등). 알려만 준다.
    all_pd = os.path.join(out, UPLOAD_PD_DIR)
    if os.path.isdir(all_pd):
        for other in sorted(os.listdir(all_pd)):
            if other == PD_CODE or not os.path.isdir(os.path.join(all_pd, other)):
                continue
            skip.append({"path": f"{UPLOAD_PD_DIR}/{other}/", "bytes": 0,
                         "reason": f"다른 품목({other})입니다. 이번 발행 대상이 아니므로 "
                                   "올리지 않습니다 — 올리면 그 품목을 덮어씁니다."})

    # ── ② axexam/web/ — 사이트를 실제로 돌리는 PHP ─────────────────────────
    #
    # ★ 06/ 만 올리면 사이트가 돌지 않는다. 빌드는 **데이터와 랜딩**만 만든다 —
    #   빌드 로그가 직접 말한다: "문제풀이 화면은 web/exam/check.php 다 — 이 빌드가
    #   굽지 않는다. 06/check.html 은 check.php 로 보내는 리다이렉트만 남는다."
    #   성적표·마이페이지·오답노트·api/*.php·관리자 화면도 전부 이쪽이다.
    #
    #   서버 경로는 SITE_PATH 아래가 아니다. `web/` 를 벗겨 웹루트에 그대로 얹는다:
    #     web/exam/check.php      → /exam/check.php
    #     web/adm/exam_import.php → /adm/exam_import.php     (SITE_PATH 밖)
    #     web/theme/axexam/…      → /theme/axexam/…
    web_root = os.path.join(BASE_DIR, "axexam", "web")
    if os.path.isdir(web_root):
        for root, dirs, files in os.walk(web_root):
            dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
            for f in sorted(files):
                # 비밀은 저장소에 없어야 하지만, 있어도 올리지 않는다(방어).
                low = f.lower()
                if "secret" in low or low.endswith("dbconfig.php"):
                    skip.append({"path": f, "bytes": 0,
                                 "reason": "비밀 파일입니다. 서버의 것을 그대로 둡니다."})
                    continue
                p_abs = os.path.join(root, f)
                rel = os.path.relpath(p_abs, web_root).replace("\\", "/")
                add_file(rel, p_abs, server="/" + rel, source="axexam/web/")
    else:
        skip.append({"path": "axexam/web/", "bytes": 0,
                     "reason": ("axexam 트리가 없습니다. git subtree 로 합쳐져 있어야 "
                                "합니다 — 없으면 사이트의 PHP 를 올릴 수 없습니다.")})

    # 올리지 않을 것
    pj = paths.problems_json()
    if os.path.isfile(pj):
        skip.append({"path": "problems.json", "bytes": os.path.getsize(pj),
                     "reason": SKIP_REASONS["problems.json"]})
    vdir = os.path.join(out, "videos")
    if os.path.isdir(vdir):
        n = sum(len(fs) for _r, _d, fs in os.walk(vdir))
        total = sum(os.path.getsize(os.path.join(r, f))
                    for r, _d, fs in os.walk(vdir) for f in fs)
        skip.append({"path": "videos/", "bytes": total, "count": n,
                     "reason": SKIP_REASONS["videos"]})

    total_bytes = sum(u["bytes"] for u in upload)
    return {
        "ok": True,
        "out": out,
        "site": SITE_BASE + SITE_PATH,
        "upload": upload,
        "skip": skip,
        "totals": {"files": len(upload), "bytes": total_bytes},
    }


def _board_table(pd_id: str) -> str:
    """과목게시판의 `bo_table` — `api/board.php` 의 `ex_board_table()` 과 **같은 규칙**이다.

    소문자·`[a-z0-9_]` 로 바꾸고 `_sj` 를 붙여 20자로 자른다.
      sqld → sqld_sj · bigdata → bigdata_sj · bdae-w → bdae_w_sj (하이픈은 `_`)

    ★ 이름이 틀리면 게시판을 못 찾아 **에러 없이 빈 목록**이 된다. 사람이 못 잡는 종류의
      고장이라, 손으로 만들라고 하지 않고 여기서 계산해 보여 준다.
    """
    t = re.sub(r"[^a-z0-9_]", "_", (pd_id or "").lower())
    return (t + "_sj")[:20]


def server_checklist() -> list[dict]:
    """서버 쪽 순서 — 우리가 대신 할 수 없는 단계들.

    임포트는 브라우저 단계다. adm/exam_import.php 가 check_admin_token() 을 쓰고
    그 토큰이 1회용이라 curl -F 로 스크립트할 수 없다.
    """
    from core.constants import PD_CODE, PD_LABEL
    from services.book import shape

    # ★ 숫자를 상수로 두지 않는다. 이 체크리스트가 곧 작업 절차라서, 낡은 숫자가
    #   적혀 있으면 사람이 그 숫자를 기준으로 검증하고 "맞다" 고 판단해 버린다.
    #   실제로 3회차·240문항·24편 시절 값이 굳어 있었다 — 9회차로 늘자 전부 틀렸다.
    sh = shape.summary()
    n_q = sh["total_questions"]
    n_r = sh["round_count"]
    n_b = sh["total_bundles"]
    n_s = sh["subject_count"]
    ymap = f"axexam/data/youtube_map.{PD_CODE}.json"
    bo = _board_table(PD_CODE)
    site = SITE_BASE.rstrip("/")
    book = paths.book_dir()
    # ★ 순서는 **실제로 하는 순서**다. 번호와 순서가 다르면 처음 보는 사람이 그대로
    #   따라가다 막힌다(seed_pd.php 는 FTP 로 올라간 뒤에야 열린다).
    return [
        {"key": "start", "label": "0.1  앱을 띄우고 품목·작업 폴더를 확인한다",
         "where": f"run.bat  →  {SITE_BASE and 'http://127.0.0.1:8870/'}",
         "detail": (f"좌하단 칩에 품목({PD_CODE})과 작업 폴더가 맞는지 본다: {book}\n"
                    "다른 품목을 발행하려면 칩 → 작업 폴더 패널에서 폴더를 바꾼다. "
                    "폴더가 곧 품목이라, 여기가 틀리면 그 뒤 전부가 틀린다.")},

        {"key": "youtube", "label": f"0.2  영상 {n_b}편을 올려 둔다 (구글 드라이브 또는 유튜브)",
         "where": "drive.google.com / youtube.com",
         "detail": (f"올릴 파일: {book}\\05\\<번들>\\draft\\*.static.mp4 ({n_b}개)\n"
                    "탐색기 검색창에 *.static.mp4 를 넣으면 한 번에 잡힌다.\n"
                    "★ 드라이브면 **폴더를 '링크가 있는 모든 사용자' 로 공유**해야 재생된다.\n"
                    "★ 지웠다 다시 올리면 ID 가 바뀐다 — 내리지 말고, 교체할 때는 드라이브의 "
                    "'버전 관리' 로 덮어쓰면 ID 가 유지된다.\n"
                    "유튜브면 '미등록(unlisted)' 으로 올리고 확인 후 공개로 바꾼다.")},

        {"key": "youtube_map", "label": f"0.3  영상 링크 {n_b}개를 매핑에 넣는다",
         "where": f"발행 화면 ②  →  {ymap}",
         "detail": ("[영상 매핑 만들기] → [링크 붙여넣기] 에 '파일명 + 링크' 목록을 그대로 "
                    "붙여넣는다. URL 이든 ID 든 잡고, 형식이 느슨해도 된다.\n"
                    "드라이브 링크를 한 번에 뽑으려면 script.google.com 에서 폴더의 "
                    "(파일명, 파일ID) 를 출력해 붙여넣는다.\n"
                    "★ 드라이브·link·file 은 min_level 이 5 로 들어간다(앱이 자동). 1 이면 "
                    "링크가 videos.js(정적 파일)에 구워져 누구나 내려받는다 — 링크 자체가 "
                    "접근 권한이다.\n"
                    f"끝나면 칩이 '링크 {n_b} / {n_b}' 가 되어야 한다.")},

        {"key": "build", "label": "0.4  빌드 — 06/ 산출물을 만든다",
         "where": "발행 화면 ③  →  [빌드 실행]",
         "detail": ("사전점검 **오류가 0** 이어야 시작한다. 경고는 한 번 더 누르면 진행한다.\n"
                    f"로그에서 확인: '영상 {n_b}개 매핑 ({n_b}/{n_b} 유튜브 ID 입력됨)' 과 "
                    f"'{n_q}문제 · {n_r}회'.\n"
                    "★ --book 과 --pd 는 항상 명시된다. 둘 다 기본값이 SQLD 라서 하나라도 "
                    "빠지면 라이브 SQLD 문제은행을 덮어쓰고 되돌릴 수 없다.")},

        {"key": "stage", "label": "0.5  업로드 폴더를 만든다",
         "where": f"발행 화면 ⑤  →  [업로드 폴더 만들기]",
         "detail": (f"{book}\\_upload 이 만들어진다. 안이 **서버와 같은 모양**"
                    "(exam/ adm/ theme/ extend/ index.php .htaccess)이라 어디로 갈지 생각할 "
                    "것이 없다.\n"
                    "★ **빌드한 뒤에는 반드시 다시 만든다.** 안 하면 옛 산출물이 올라간다 — "
                    "화면이 빨간 배너로 알려주지만, 그 배너를 못 보면 문제·영상이 예전 것으로 "
                    "나간다.\n"
                    "problems.json 과 mp4 는 이 폴더에 없다(각각 3번·0.2번에서 처리한다).")},

        # ── 여기부터 서버. 앱 밖에서 사람이 한다. ─────────────────────────────
        {"key": "ftp", "label": "1.  FileZilla 로 /www/ 에 올린다",
         "where": f"{book}\\_upload   →   /www/",
         "detail": ("왼쪽(로컬)에 그 폴더, 오른쪽(서버)에 /www/ 를 놓고 **왼쪽 전체 선택 → "
                    "끌어놓기**. 337개 2.3MB 라 몇 분이다.\n"
                    "FileZilla 설정(한 번만): 전송 유형 **바이너리** · 동시 전송 2 · "
                    "문자셋 **UTF-8 강제**(요약노트 파일명이 한글이다).\n"
                    "덮어쓰기를 물으면 [덮어쓰기] + '항상 이 동작 사용' 체크.\n"
                    "★ FileZilla 는 폴더를 **합친다** — 서버의 기존 파일을 지우지 않고 같은 "
                    "이름만 덮어쓴다. 다른 품목(pd/sqld 등)은 이 폴더에 없으니 안전하다.\n"
                    "끝나면 앱에서 [다 올렸습니다 — 지우기].")},

        # ★ FTP 뒤에 온다 — 이 파일이 서버에 올라가야 열린다.
        {"key": "ex_product", "label": f"2.1  품목 등록 — ex_product 에 pd_id='{PD_CODE}'",
         "where": f"{site}/adm/seed_pd.php",
         "detail": ("**최고관리자로 로그인한 브라우저**에서 연다(부관리자는 안 된다).\n"
                    f"pd_id={PD_CODE} · 이름 확인 → [등록]. 표에 그 품목이 추가되면 성공.\n"
                    "★ 이게 없으면 다음 단계가 "
                    f"\"ex_product 에 pd_id='{PD_CODE}' 가 없습니다\" 로 중단된다.\n"
                    "★ 카페24에는 phpMyAdmin 이 없다 — 이 화면이 그 자리다.\n"
                    "★ 이 화면을 닫지 말고 **2.2 까지 한 다음** /www/adm/seed_pd.php 를 "
                    "FTP 로 지운다(1회용). 2.2 가 같은 화면이다.\n"
                    "404 가 뜨면 1번 업로드가 안 된 것이다(지웠다면 다시 올린다)."),
         "sql": ("-- 직접 SQL 을 쓸 수 있는 환경이라면 이것과 같다\n"
                 "INSERT INTO ex_product\n"
                 "  (pd_id, pd_name, pd_open, tier, model_id, provider,\n"
                 "   cost_units, cost_cap, pd_sort)\n"
                 f"VALUES ('{PD_CODE}', '{PD_LABEL}', 1, 'T1', 'deepseek-v4-flash',\n"
                 "        'openai_compat', 10, 3.0000, 20)\n"
                 "ON DUPLICATE KEY UPDATE pd_name = VALUES(pd_name);")},

        # ★ 이 단계를 빼먹으면 **문제는 다 보이는데 신청서만 없다.** 문항·영상·성적표가
        #   전부 정상이라 "다 됐다" 고 판단하게 되는 종류의 누락이다. 실제로 그렇게 걸렸다:
        #   SQLD 는 신청서가 뜨고 빅분기는 "등록된 과정이 없습니다" 만 떴다.
        #   원인은 마이그레이션이 과정 3종을 옛 pd_id(bdae-w)에 심어 뒀던 것이었다.
        #   그래서 품목 등록과 **같은 화면·같은 방문**에 두고, 체크박스를 따로 준다.
        {"key": "ex_plan", "label": "2.2  수강 과정 등록 — [＋과정 3종] 한 번",
         "where": f"{site}/adm/seed_pd.php",
         "detail": ("같은 화면 아래쪽 <수강 과정> 이다. 품목 표에서 이 품목 줄의 **과정** 열이 "
                    "빨간 0 이면 [＋과정 3종] 을 누른다 — 1·3·12개월 × 매월 질문 100개가 "
                    "SQLD 와 같은 구성으로 들어간다.\n"
                    f"확인: {site}{SITE_PATH}buy.php?pd={PD_CODE} 에 과정 3개와 [신청하기] 가 "
                    "보이면 끝이다.\n"
                    "★ 과정이 0 이면 신청서 자리에 '등록된 과정이 없습니다' 만 나오고 "
                    "**[신청하기] 버튼이 아예 없다.** 문제풀이·영상·성적표는 다 정상이라 "
                    "이 누락만 눈에 안 띈다 — 그래서 반드시 buy.php 를 열어 본다.\n"
                    "★ 과정은 **품목별**이다(ex_plan.pd_id). 다른 품목의 과정이 이 품목에 "
                    "쓰이지 않는다.\n"
                    "★ 값을 바꿀 때는 고치지 말고 **새 과정 + 옛것 숨기기**. 가격·기간을 "
                    "고치면 이미 결제한 주문의 뜻이 달라진다."),
         "sql": ("-- 직접 SQL 을 쓸 수 있는 환경이라면 이것과 같다\n"
                 "INSERT INTO ex_plan\n"
                 "  (pd_id, pl_name, pl_price, pl_months, pl_quota, pl_open, pl_sort)\n"
                 "VALUES\n"
                 f"  ('{PD_CODE}', '1개월 · 매월 질문 100개',   1100,  1, 1000, 1, 10),\n"
                 f"  ('{PD_CODE}', '3개월 · 매월 질문 100개',   3000,  3, 1000, 1, 20),\n"
                 f"  ('{PD_CODE}', '12개월 · 매월 질문 100개', 11000, 12, 1000, 1, 30);\n"
                 "\n"
                 "-- 확인 — 품목마다 과정이 몇 개인가 (0 인 품목이 신청 불가 상태다)\n"
                 "SELECT d.pd_id, d.pd_name, COUNT(p.pl_id) AS plans\n"
                 "  FROM ex_product d\n"
                 "  LEFT JOIN ex_plan p ON p.pd_id = d.pd_id AND p.pl_open = 1\n"
                 " GROUP BY d.pd_id, d.pd_name ORDER BY d.pd_sort;")},

        # 라벨을 관리자 화면의 제목과 같게 둔다 — 화면을 열었을 때 "여기가 맞나" 를
        # 다시 묻지 않게 된다(실제로 그 질문이 나왔다).
        {"key": "import", "label": "3.  문제 임포트",
         "where": f"{site}/adm/exam_import.php",
         "detail": (f"올릴 파일: {book}\\06\\pd\\{PD_CODE}\\problems.json\n"
                    "파일 선택 필드 이름은 jsonfile. 그누보드 관리자 권한(600400)이 필요하다 "
                    "— 부관리자에게 위임할 수 있다.\n"
                    "1회용 관리자 토큰 때문에 스크립트로는 못 부른다 — 브라우저 단계다. "
                    "서버는 처리 후 업로드 파일을 즉시 지운다.\n"
                    "★ 고친 문항만 올릴 때는 발행 화면 ④ [부분 임포트] 로 잘라 "
                    "'또는 붙여넣기' 에 붙여넣는다(문항 하나 2.6KB · 회차 하나 92KB).\n"
                    "★ FTP 로는 올려도 읽히지 않는다 — .htaccess 가 .json 을 403 으로 막는다.")},

        {"key": "report", "label": "4.  임포트 리포트를 읽는다",
         "where": f"{site}/adm/exam_import.php",
         "detail": (f"첫 발행이면 **신규 {n_q} · 갱신 0 · 회차 {n_r}행**.\n"
                    "두 번째부터는 신규 0 · 갱신(고친 수) · 변경없음(나머지).\n"
                    "★ **실패·건너뜀은 항상 0** 이어야 한다.\n"
                    "★ skip_edited 가 0 이 아니면 그 문항을 전에 웹에서 고친 것이다 — "
                    f"{site}/adm/exam_problem_form.php 에서 [원본 복원] 후 다시 임포트한다.\n"
                    "회차는 rd_free 기본값 1(무료)로 들어온다. 재임포트가 그 값을 건드리지 "
                    "않으므로 나중에 바꾼 공개 정책은 유지된다.")},

        {"key": "verify", "label": "5.  웹에서 확인한다",
         "where": SITE_BASE + SITE_PATH,
         "detail": (f"① {site}{SITE_PATH}api/products.php — {PD_CODE} 가 "
                    f"open:1 · problems:{n_q} · rounds:{n_r} 로 보이고 "
                    "**다른 품목도 그대로** 있어야 한다.\n"
                    f"② {site}{SITE_PATH}check.php?pd={PD_CODE} — "
                    f"{n_q}문항 · {n_s}과목 필터 · 회차 1~{n_r}.\n"
                    f"③ {site}{SITE_PATH} — 품목 카드에 이 품목과 기존 품목이 함께. "
                    "상단 내비에 품목 이름들이 나온다.\n"
                    f"③' {site}{SITE_PATH}buy.php?pd={PD_CODE} — **수강 과정 3개와 "
                    "[신청하기]**. '등록된 과정이 없습니다' 면 2.2 를 안 한 것이다.\n"
                    "④ 영상 — **로그인 레벨이 min_level 이상일 때만** 보인다(드라이브는 5). "
                    "강사 계정으로 하나 재생해 보면 링크·공유·레벨이 한 번에 확인된다. "
                    "일반 회원에게 안 보이는 것이 정상이다.\n"
                    "자동 확인: axexam/scripts/deploy_check.py --pd <품목> --build <06 경로>")},

        {"key": "board", "label": f"6.  [선택] 과목게시판 만들기 — bo_table = {bo}",
         "where": "그누보드 관리자 → 게시판 관리 → 추가",
         "detail": ("게시판은 **문제집당 1개**이고 과목은 말머리로 구분한다 — 과목이 4개라고 "
                    f"게시판 4개를 만들지 않는다.\n"
                    "\n"
                    "[게시판 추가] 화면에서 채울 것 — 나머지는 기본값 그대로 둔다:\n"
                    f"  · 테이블 이름   {bo}                ★ 이것만 틀리면 안 된다\n"
                    f"  · 게시판 제목   {PD_LABEL} 과목게시판\n"
                    "  · 스킨          basic (기본)         사이트는 api/board.php 로 읽는다.\n"
                    "                                       스킨은 관리자 열람용이다\n"
                    "  · 분류 사용     건드리지 않아도 된다 — 다음 단계(말머리 동기화)가\n"
                    "                  bo_use_category=1 을 직접 켜고 분류를 채운다\n"
                    "  · 글쓰기 권한   회원 이상 (기본)      질문은 회원이 쓴다\n"
                    "  · 읽기 권한     모두 (기본)          문제·해설이 전면 공개라 질문도 공개다\n"
                    "\n"
                    f"★ 테이블 이름이 `{bo}` 가 아니면 게시판을 못 찾아 **에러 없이 빈 목록**이 "
                    "된다. 규칙은 pd_id 를 소문자·[a-z0-9_] 로 바꿔 `_sj` 를 붙이고 20자로 자른 "
                    "것이다(api/board.php 의 ex_board_table()).\n"
                    "문제풀이·성적표·영상과 무관하다 — 질문 게시판만 이게 없으면 비어 보인다.")},

        {"key": "board_sync", "label": "7.  [선택] 과목 말머리 동기화",
         "where": f"{site}/adm/exam_board_sync.php",
         "detail": ("ex_problem 의 과목 목록을 게시판 말머리로 맞춘다. 과목명 오타 하나로 "
                    "api/board.php 의 필터가 에러 없이 빈 목록을 돌려주기 때문에 이것만 "
                    "자동화했다. 과목이 늘거나 이름이 바뀌면 다시 돌린다.")},

        # ── 여기부터는 '나중에 고칠 때'. 초기 세팅보다 훨씬 자주 일어난다.
        {"key": "revise_video", "label": "[나중] 영상만 바꿀 때 — 파일 1개",
         "where": f"{ymap}  →  빌드  →  업로드 폴더  →  FTP",
         "detail": ("영상 교체·삭제·추가는 **가장 싼 변경**이다. 매핑의 id 를 고치고 빌드한 뒤 "
                    f"`pd/{PD_CODE}/videos.private.json` **한 파일만** 올리면 끝난다 — "
                    "api/videos.php 가 그 파일을 요청마다 다시 읽는다(캐시도 DB도 없다).\n"
                    "problems.json 재임포트도, 관리자 화면도 필요 없다.\n"
                    "min_level 이 1 이면 대신 videos.js 를 올린다.")},

        {"key": "revise_question", "label": "[나중] 문항을 고칠 때 — 임포트까지",
         "where": "#/questions  →  빌드  →  ④ 부분 임포트  →  관리자 화면",
         "detail": ("문항은 서버 DB 에 있으므로 재임포트가 필요하다. 고친 문항만 잘라 올리면 "
                    "리포트가 '갱신 1' 만 찍어 확인이 쉽다.\n"
                    "★ 임포트는 DELETE 를 하지 않는다 — 로컬에서 문항을 빼도 서버에 남는다. "
                    f"숨기려면 {site}/adm/exam_problem_list.php 의 [숨기기](pr_open=0).\n"
                    "해설·보기가 영상에 나오면 #/video 에 '재렌더' 로 뜬다 — 그 번들만 다시 "
                    "만들고 드라이브에서 그 mp4 만 교체한다(버전 관리로 ID 유지).\n"
                    "pr_key 가 같은 행을 UPDATE 하므로 회차·번호를 바꾸면 새 행이 생긴다.")},
    ]
