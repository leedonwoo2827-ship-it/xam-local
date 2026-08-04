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
    ymap = f"data/youtube_map.{PD_CODE}.json"
    return [
        {"key": "ex_product", "label": f"ex_product 에 pd_id='{PD_CODE}' 행 추가",
         "where": "phpMyAdmin",
         "detail": ("임포트가 이 행을 먼저 확인한다. 없으면 "
                    f"\"ex_product 에 pd_id='{PD_CODE}' 가 없습니다\" 로 중단된다."),
         "sql": ("INSERT INTO ex_product\n"
                 "  (pd_id, pd_name, pd_open, tier, model_id, provider, cost_units, cost_cap, pd_sort)\n"
                 f"VALUES ('{PD_CODE}', '{PD_LABEL}', 1, 'T1', 'deepseek-v4-flash',\n"
                 "        'openai_compat', 10, 3.0000, 20)\n"
                 "ON DUPLICATE KEY UPDATE pd_name = VALUES(pd_name);")},
        {"key": "youtube", "label": f"영상 {n_b}편을 올린다 (구글 드라이브 또는 유튜브)",
         "where": "drive.google.com / youtube.com",
         "detail": ("★ 지웠다 다시 올리면 ID 가 바뀐다 — 내리지 말고 비공개로 둔다. "
                    "유튜브면 '미등록(unlisted)' 으로 올리고 확인 후 공개로 바꾼다 "
                    "(ID 가 그대로라 매핑을 다시 고칠 필요가 없다). "
                    "드라이브면 '링크가 있는 모든 사용자' 로 공유해야 재생된다.")},
        {"key": "youtube_map", "label": f"영상 매핑에 링크 {n_b}개 입력",
         "where": ymap,
         "detail": ("발행 화면의 [영상 매핑 만들기] 로 골격을 만들고, 공유 URL 을 각 항목의 "
                    "id 에 붙여넣는다 — URL 그대로 넣어도 된다(빌더가 ID 만 뽑는다). "
                    "★ 드라이브·link·file 은 min_level 을 5 로 둔다. 1 이면 링크가 "
                    "videos.js(정적 파일)에 구워져 누구나 내려받는다 — 링크 자체가 권한이다. "
                    "입력 후 다시 빌드한다.")},
        {"key": "ftp", "label": "06/ 산출물을 /www/exam/ 로 FTP 업로드",
         "where": "FileZilla",
         "detail": ("전송 유형은 **바이너리**. 동시 전송 2개 이하. 파일명 인코딩 UTF-8 강제"
                    "(요약노트 파일명이 한글이다). problems.json 과 mp4 는 올리지 않는다.")},
        {"key": "import", "label": "problems.json 을 관리자 화면에서 업로드",
         "where": "/adm/exam_import.php",
         "detail": ("파일 선택 필드 이름은 jsonfile. 그누보드 최고관리자로 로그인해야 한다. "
                    "1회용 관리자 토큰 때문에 스크립트로는 못 부른다 — 브라우저 단계다. "
                    "서버는 처리 후 업로드 파일을 즉시 지운다.")},
        {"key": "report", "label": "임포트 리포트 확인",
         "where": "/adm/exam_import.php",
         "detail": (f"첫 발행이면 신규 {n_q} · 갱신 0 · 회차 {n_r}행. "
                    f"두 번째부터는 신규 0 · 갱신(고친 수) · 변경없음(나머지) 로 나온다. "
                    "실패·건너뜀은 항상 0 이어야 한다.")},
        {"key": "verify", "label": "웹에서 최종 확인",
         "where": SITE_BASE + SITE_PATH,
         "detail": (f"api/products.php 에 {PD_CODE} 가 open:1 · problems:{n_q} · rounds:{n_r} 로 "
                    f"보이고, check.html?pd={PD_CODE} 가 {n_q}문항·{n_s}과목 필터로 떠야 한다. "
                    "영상은 로그인 레벨이 min_level 이상일 때만 보인다(드라이브는 5로 두었다).")},
        # ★ 여기부터는 '나중에 고칠 때' 절차다. 초기 세팅보다 이쪽이 훨씬 자주 일어난다.
        {"key": "revise_video", "label": "[나중] 영상만 바꿀 때 — 파일 1개",
         "where": f"{ymap} → 빌드 → FTP",
         "detail": ("영상 교체·삭제·추가는 **가장 싼 변경**이다. 매핑의 id 를 고치고 빌드한 뒤 "
                    f"`pd/{PD_CODE}/videos.private.json` **한 파일만** 올리면 끝난다 "
                    "(api/videos.php 가 그 파일을 요청마다 다시 읽는다 — 캐시도 DB도 없다). "
                    "problems.json 재임포트도, 관리자 화면도 필요 없다. "
                    "min_level 이 1 이면 대신 `videos.js` 를 올린다.")},
        {"key": "revise_question", "label": "[나중] 문항을 고칠 때 — 임포트까지",
         "where": "#/questions → 빌드 → FTP → 관리자 화면",
         "detail": ("문항은 서버 DB 에 들어가 있으므로 problems.json 재임포트가 필요하다. "
                    "리포트의 '갱신' 수가 고친 문항 수와 같은지 확인한다. "
                    "pr_key 가 같은 행을 UPDATE 하므로 회차·번호를 바꾸면 새 행이 생긴다.")},
    ]
