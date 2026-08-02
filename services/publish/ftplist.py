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

from core.constants import SITE_BASE, SITE_PATH
from services.book import paths

# 올릴 것 — 06/ 안의 파일·폴더
UPLOAD_FILES = ("check.html", "index.html", "problems.js", "videos.js",
                "theory.js", "theory_content.js")
UPLOAD_DIRS = ("assets", "figs", "theory")

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

    def add_file(rel: str, abs_path: str) -> None:
        rec = {
            "path": rel.replace("\\", "/"),
            "server_path": SITE_PATH + rel.replace("\\", "/"),
            "url": SITE_BASE + SITE_PATH + rel.replace("\\", "/"),
            "bytes": os.path.getsize(abs_path),
        }
        if with_hash:
            rec["sha256"] = _sha256(abs_path)
        upload.append(rec)

    for name in UPLOAD_FILES:
        p = os.path.join(out, name)
        if os.path.isfile(p):
            add_file(name, p)
    # 품목 상세 페이지 — axexam 패치 2번 이후 {pd}.html 로 나온다.
    from core.constants import PD_CODE
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
        {"key": "youtube", "label": "영상 24편을 유튜브에 업로드",
         "where": "youtube.com",
         "detail": ("먼저 '미등록(unlisted)' 으로 올리고 확인한 뒤 공개로 바꾼다. "
                    "영상 ID 는 그대로이므로 매핑 파일을 다시 고칠 필요가 없다. "
                    "⚠ 지웠다 다시 올리면 ID 가 바뀐다 — 내리지 말고 미등록으로 둔다.")},
        {"key": "youtube_map", "label": f"youtube_map.{PD_CODE}.json 에 ID 24개 입력",
         "where": f"_ref/axexam/data/youtube_map.{PD_CODE}.json",
         "detail": "유튜브 URL 의 v= 값을 각 번들 항목의 id 에 넣는다. 입력 후 다시 빌드한다."},
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
         "detail": "기대값 — 신규 240 · 갱신 0 · 변경없음 0 · 건너뜀 0 · 실패 0 · 회차 3행."},
        {"key": "verify", "label": "웹에서 최종 확인",
         "where": SITE_BASE + SITE_PATH,
         "detail": (f"api/products.php 에 {PD_CODE} 가 open:1 · problems:240 · rounds:3 으로 "
                    f"보이고, check.html?pd={PD_CODE} 가 240문항·4과목 필터로 떠야 한다.")},
    ]
