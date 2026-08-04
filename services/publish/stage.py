"""업로드 폴더 만들기 — **서버와 똑같은 모양**으로 한 폴더에 모은다.

★ 왜 필요한가

  올릴 것이 로컬 두 곳에서 서버 세 곳으로 간다:

      06\\                  → /www/exam/
      axexam\\web\\exam\\    → /www/exam/      (같은 자리에 섞인다)
      axexam\\web\\adm\\     → /www/adm/       (/exam/ 밖!)
      axexam\\web\\theme\\   → /www/theme/

  머릿속으로 이 매핑을 하면서 FileZilla 를 쓰면 반드시 틀린다. 특히 `web\\` 을 벗겨야
  하는 것과 `adm\\` 이 `/exam/` 밖이라는 것에서 걸린다. 그리고 틀려도 **업로드는
  성공한 것처럼 보인다** — 웹에서 증상이 엉뚱한 얼굴로 나타날 뿐이다.

  → 그 매핑을 여기서 한 번 해 둔다. 결과 폴더 하나를 `/www/` 에 통째로 끌어놓으면 끝이다.

★ 사본을 만드는 것이 낭비가 아닌 이유
  전부 합쳐 2.3MB 다. 그리고 이 폴더는 "서버에 무엇이 올라갔나" 의 스냅샷이 되어,
  다음에 무엇이 바뀌었는지 비교할 수 있다.
"""
from __future__ import annotations

import filecmp
import os
import shutil

from core.constants import BASE_DIR
from services.book import paths
from services.publish import buildcheck

# 06/ 안에서 올리지 않을 것 — 이유를 결과에 함께 남긴다.
SKIP_IN_06 = {
    "problems.json": "관리자 화면에서 업로드합니다 (.htaccess 가 .json 을 403 으로 막습니다)",
    "videos": "예전 빌드의 mp4 폴더입니다",
    # 부분 임포트로 잘라낸 파일들 — 관리자 화면에 붙여넣는 것이고 서버에 둘 이유가 없다.
    "_partial": "부분 임포트용 파일입니다. 관리자 화면에 붙여넣습니다",
    "_upload": "업로드 폴더 자신입니다",
}
# web/ 안에서 올리지 않을 것
SKIP_NAMES = ("__pycache__",)
# web/ 안에서 서버에 둘 이유가 없는 폴더
SKIP_WEB_DIRS = {
    "sql": "스키마 DDL 입니다. 실행 시점에 읽지 않고, 테이블 이름을 노출할 이유도 없습니다",
}


def stage_dir() -> str:
    """업로드 폴더. `06/` 밖에 둔다 — 안에 두면 다음 빌드의 `--prune` 와 얽힌다."""
    return os.path.join(paths.book_dir(), "_upload")


def _copy(src: str, dst: str, log: list, kind: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    same = os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False)
    if not same:
        shutil.copy2(src, dst)
    log.append({"to": os.path.relpath(dst, stage_dir()).replace("\\", "/"),
                "from": kind, "bytes": os.path.getsize(src), "changed": not same})


def build() -> dict:
    """`_upload/` 를 서버 레이아웃으로 새로 만든다."""
    out = paths.out_dir()
    if not os.path.isdir(out):
        raise ValueError(f"06/ 이 없습니다: {out} — 먼저 빌드하세요.")
    web = os.path.join(BASE_DIR, "axexam", "web")
    if not os.path.isdir(web):
        raise ValueError(f"axexam/web 이 없습니다: {web}")

    pd = buildcheck.active_pd()
    dest = stage_dir()
    # ★ 안을 비우고 다시 채운다. 남겨 두면 지워진 파일이 계속 올라가고,
    #   "왜 지운 화면이 아직 보이나" 를 찾느라 시간을 쓴다.
    #
    #   ★ 폴더 **자신**은 지우지 않는다. 탐색기나 FileZilla 로 그 폴더를 열어 두면
    #     Windows 가 잠궈서 rmtree(dest) 가 WinError 32 로 죽는다 — 그리고 이 기능은
    #     "폴더를 열어 놓고 끌어놓는" 용도라 그 상황이 정상이다. 실제로 걸렸다.
    os.makedirs(dest, exist_ok=True)
    for name in os.listdir(dest):
        p_ = os.path.join(dest, name)
        try:
            shutil.rmtree(p_) if os.path.isdir(p_) else os.remove(p_)
        except OSError as e:
            raise ValueError(
                f"업로드 폴더를 비우지 못했습니다: {name} ({e.strerror or e}). "
                "그 파일을 열어 둔 프로그램(탐색기 미리보기·FileZilla 전송 중)을 "
                "닫고 다시 누르세요.") from e

    log: list = []
    skipped: list = []

    # ── ① 06/ → _upload/exam/ ────────────────────────────────────────────
    exam = os.path.join(dest, "exam")
    for root, dirs, files in os.walk(out):
        rel_dir = os.path.relpath(root, out)
        top = rel_dir.split(os.sep)[0] if rel_dir != "." else ""
        if top == "_upload":
            dirs[:] = []
            continue
        if top in SKIP_IN_06:
            skipped.append({"path": rel_dir.replace("\\", "/"), "reason": SKIP_IN_06[top]})
            dirs[:] = []
            continue
        # 다른 품목 트리는 건드리지 않는다 — 올리면 그 품목을 덮어쓴다.
        if rel_dir.replace("\\", "/").startswith("pd/") and \
                rel_dir.replace("\\", "/").split("/")[1] not in (pd,):
            skipped.append({"path": rel_dir.replace("\\", "/"),
                            "reason": f"다른 품목입니다. 이번 발행 대상({pd})이 아닙니다"})
            dirs[:] = []
            continue
        for f in sorted(files):
            if f in SKIP_IN_06:
                skipped.append({"path": os.path.join(rel_dir, f).replace("\\", "/"),
                                "reason": SKIP_IN_06[f]})
                continue
            src = os.path.join(root, f)
            rel = os.path.relpath(src, out)
            _copy(src, os.path.join(exam, rel), log, "06/")

    # ── ② axexam/web/ → _upload/ (web 을 벗긴다) ─────────────────────────
    for root, dirs, files in os.walk(web):
        for d in list(dirs):
            if d in SKIP_WEB_DIRS:
                skipped.append({"path": os.path.relpath(os.path.join(root, d), web)
                                        .replace("\\", "/") + "/",
                                "reason": SKIP_WEB_DIRS[d]})
        dirs[:] = [d for d in dirs if d not in SKIP_NAMES and d not in SKIP_WEB_DIRS]
        for f in sorted(files):
            low = f.lower()
            if "secret" in low or low.endswith("dbconfig.php"):
                skipped.append({"path": f, "reason": "비밀 파일입니다. 서버의 것을 그대로 둡니다"})
                continue
            src = os.path.join(root, f)
            rel = os.path.relpath(src, web)
            _copy(src, os.path.join(dest, rel), log, "axexam/web/")

    tops = sorted({p["to"].split("/")[0] for p in log})
    changed = [p for p in log if p["changed"]]
    return {
        "dir": dest,
        "server": "/www/",
        "files": len(log),
        "bytes": sum(p["bytes"] for p in log),
        "changed": len(changed),
        "tops": tops,
        "skipped": skipped,
        "pd": pd,
        # 이 폴더 안에서 손으로 지울 것 — 없으면 빈 목록이다(그게 정상).
        "delete_here": [],
    }


def summary() -> dict:
    """이미 만들어 둔 폴더의 상태 — 만들지 않고 본다.

    ★ `stale` 을 함께 준다: 빌드(06/)가 이 폴더보다 새로우면 **옛 산출물을 올리게 된다.**
      실제로 그렇게 걸렸다 — 빌드는 10:21 에 돌았는데 업로드 폴더는 08:58 것이라
      새로 생긴 `videos.private.json` 이 빠진 채 "다 만들어졌다" 로 보였다.
      화면이 그걸 모르면 사람이 알아챌 방법이 없다(파일 수만 보면 그럴듯하다).
    """
    d = stage_dir()
    if not os.path.isdir(d):
        return {"dir": d, "exists": False, "server": "/www/"}
    n = 0
    b = 0
    newest = 0.0
    for root, _dirs, files in os.walk(d):
        for f in files:
            p_ = os.path.join(root, f)
            n += 1
            b += os.path.getsize(p_)
            newest = max(newest, os.path.getmtime(p_))

    # 06/ 쪽에서 가장 새로운 파일과 비교한다.
    out = paths.out_dir()
    build_newest = 0.0
    if os.path.isdir(out):
        for root, dirs, files in os.walk(out):
            dirs[:] = [x for x in dirs if x not in ("_partial",)]
            for f in files:
                build_newest = max(build_newest, os.path.getmtime(os.path.join(root, f)))

    stale = build_newest > newest + 1     # 1초 여유(복사 시각 차)
    return {"dir": d, "exists": True, "server": "/www/", "files": n, "bytes": b,
            "tops": sorted(x for x in os.listdir(d)),
            "stale": stale,
            "stale_text": ("빌드(06/)가 이 폴더보다 새롭습니다 — [업로드 폴더 다시 만들기] 를 "
                           "누르지 않으면 **옛 산출물을 올립니다.**") if stale else ""}
