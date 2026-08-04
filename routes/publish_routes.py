"""/api/publish — 사전점검 · 빌드 · problems.json 검증 · FTP 목록 · 체크리스트.

발행은 '버튼 하나' 가 아니다. axexam 절차의 순서를 틀릴 수 없게 만드는 것이 이
화면의 일이다. 임포트는 브라우저 단계라서 우리가 대신 누를 수 없다.
"""
from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request

from core.constants import PD_CODE, PUBLISH_DIR, SITE_BASE, SITE_PATH
from core.atomic_io import atomic_write_json
from services.book import paths
from services.jobs import registry
from services.publish import buildcheck, ftplist, validate

logger = logging.getLogger(__name__)

_STATE = os.path.join(PUBLISH_DIR, "checklist.json")


def _load_state() -> dict:
    if os.path.isfile(_STATE):
        try:
            with open(_STATE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def setup_publish_routes() -> APIRouter:
    router = APIRouter(prefix="/api/publish", tags=["publish"])

    @router.get("/preflight")
    async def preflight():
        r = validate.run()
        if r.get("error"):
            raise HTTPException(status_code=503, detail=r["error"])
        return r

    @router.get("/env")
    async def env():
        e = buildcheck.env_info()
        # pd 가 안 정해진 폴더에서는 명령을 만들 수 없다 — 화면이 그 사실을 보여준다.
        try:
            e["command"] = buildcheck.command_text()
            e["pd_ok"] = True
        except ValueError as ex:
            e["command"] = ""
            e["pd_ok"] = False
            e["pd_error"] = str(ex)
        e["site"] = SITE_BASE + SITE_PATH
        return e

    @router.post("/build")
    async def build(request: Request):
        """axexam 의 build_check.py 를 --book/--pd 를 명시해 호출한다.

        오류(error)가 하나라도 있으면 시작하지 않는다. 경고는
        force_ignore_warnings 로 통과시킬 수 있다.
        """
        body = await request.json() if await request.body() else {}
        force = bool(body.get("force_ignore_warnings"))

        pre = validate.run()
        if pre.get("error"):
            raise HTTPException(status_code=503, detail=pre["error"])
        if pre["errors"]:
            bad = [c["label"] for g in pre["groups"] for c in g["checks"]
                   if c["level"] == "error" and not c["ok"]]
            raise HTTPException(
                status_code=409,
                detail=("사전점검 오류가 남아 있어 빌드를 시작하지 않았습니다 "
                        f"({pre['errors']}건).\n· " + "\n· ".join(bad[:8])))
        if pre["warnings"] and not force:
            bad = [c["label"] for g in pre["groups"] for c in g["checks"]
                   if c["level"] == "warn" and not c["ok"]]
            raise HTTPException(
                status_code=409,
                detail=(f"경고 {pre['warnings']}건이 있습니다. 확인한 뒤 다시 누르면 "
                        "진행합니다.\n· " + "\n· ".join(bad[:8])))

        busy = registry.running("build")
        if busy:
            raise HTTPException(status_code=409, detail="이미 빌드가 돌고 있습니다.")
        try:
            job = buildcheck.start()
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return registry.view(job)

    @router.get("/problems")
    async def problems():
        """마지막으로 만들어진 problems.json 검증 (임포트 드라이런)."""
        return buildcheck.validate_problems_json()

    @router.get("/ftplist")
    async def get_ftplist(hash: int = 0):
        r = ftplist.build(with_hash=bool(hash))
        if not r["ok"]:
            raise HTTPException(status_code=409, detail=r.get("error") or "06/ 가 없습니다.")
        return r

    @router.post("/open")
    async def open_folder(request: Request):
        """탐색기로 06/ 를 연다 — FileZilla 로 끌어다 놓는 손잡이."""
        body = await request.json() if await request.body() else {}
        which = body.get("which") or "out"
        target = paths.out_dir() if which == "out" else PUBLISH_DIR
        if not os.path.isdir(target):
            raise HTTPException(status_code=404, detail=f"폴더가 없습니다: {target}")
        try:
            os.startfile(target)          # noqa: S606  (로컬 단일 사용자 앱)
        except Exception as e:
            raise HTTPException(status_code=500,
                                detail=f"폴더를 열지 못했습니다: {e}") from e
        return {"ok": True, "path": target}

    @router.get("/ytmap")
    async def get_ytmap():
        """영상 매핑 상태 — 번들별 링크가 채워졌는지."""
        from services.publish import ytmap
        return ytmap.read()

    @router.post("/ytmap/sync")
    async def sync_ytmap(request: Request):
        """매핑 골격 생성 / 빠진 번들 채우기. **이미 넣은 링크는 건드리지 않는다.**

        빌더의 `--init-youtube-map` 은 "파일이 있으면 아무것도 안 함" 이라 회차가
        늘어난 뒤에는 쓸 수 없다. 그래서 여기서 증분으로 맞춘다.
        """
        from services.publish import ytmap
        body = await request.json() if await request.body() else {}
        try:
            return ytmap.sync(provider=(body.get("provider") or "").strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/ytmap/paste")
    async def paste_ytmap(request: Request):
        """붙여넣은 목록으로 링크 72개를 한 번에 채운다.

        한 줄에서 번들코드와 ID/URL 을 각각 찾아 맞추므로 형식이 느슨해도 된다.
        번들이 72개라 손으로 넣으면 한 줄 밀려 영상이 엉뚱한 회차에 붙는다 —
        그건 영상을 봐야 알 수 있어서 되돌리기 비싸다.
        """
        from services.publish import ytmap
        body = await request.json() if await request.body() else {}
        try:
            return ytmap.fill_from_text(body.get("text") or "")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/ytmap/open")
    async def open_ytmap():
        """매핑 파일을 기본 편집기로 연다 — 링크를 붙여넣는 자리."""
        from services.publish import ytmap
        p = ytmap.path()
        if not os.path.isfile(p):
            raise HTTPException(status_code=404,
                                detail=f"매핑 파일이 없습니다: {p} — [영상 매핑 만들기] 를 먼저 누르세요.")
        try:
            os.startfile(p)               # noqa: S606  (로컬 단일 사용자 앱)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"열지 못했습니다: {e}") from e
        return {"ok": True, "path": p}

    @router.get("/partial")
    async def get_partial():
        """problems.json 을 무엇으로 쪼갤 수 있는지 (회차·번들 목록)."""
        from services.publish import partial
        try:
            return partial.summary()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    @router.post("/partial")
    async def make_partial(request: Request):
        """회차·번들·문항만 담은 부분 임포트 파일을 만든다.

        임포트가 DELETE 를 하지 않으므로(problem.php:13) 여기 없는 문항은 서버에 그대로
        남는다. 전체 714KB 를 다시 올리는 대신 회차 92KB · 문항 2.6KB 만 올린다.
        용량보다 **확인**이 이득이다 — 리포트가 '갱신 1' 만 찍으면 끝난다.
        """
        from services.publish import partial
        b = await request.json() if await request.body() else {}
        try:
            return partial.write(rounds=b.get("rounds") or None,
                                 bundles=b.get("bundles") or None,
                                 keys=b.get("keys") or None,
                                 label=(b.get("label") or "").strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("/stage")
    async def get_stage():
        """업로드 폴더 상태 — 만들지 않고 본다."""
        from services.publish import stage
        return stage.summary()

    @router.post("/stage")
    async def make_stage(request: Request):
        """`_upload/` 를 **서버와 똑같은 모양**으로 만든다.

        올릴 것이 로컬 두 곳에서 서버 세 곳으로 가는데(06/ → /exam/,
        web/exam → /exam/, web/adm → /adm/), 그 매핑을 사람이 하면 반드시 틀린다.
        여기서 한 번 해 두면 폴더 하나를 /www/ 에 통째로 올리는 것으로 끝난다.
        """
        from services.publish import stage
        try:
            return stage.build()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    @router.post("/stage/clear")
    async def clear_stage():
        """다 올린 뒤 지운다. 남겨 두면 다음에 무엇이 새것인지 헷갈린다."""
        import shutil
        from services.publish import stage
        d = stage.stage_dir()
        if os.path.isdir(d):
            shutil.rmtree(d)
        return {"ok": True, "dir": d}

    @router.post("/stage/open")
    async def open_stage():
        from services.publish import stage
        d = stage.stage_dir()
        if not os.path.isdir(d):
            raise HTTPException(status_code=404,
                                detail="업로드 폴더가 없습니다 — [업로드 폴더 만들기] 를 먼저 누르세요.")
        try:
            os.startfile(d)           # noqa: S606
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return {"ok": True, "dir": d}

    @router.get("/checklist")
    async def get_checklist():
        return {"pd": PD_CODE, "items": ftplist.server_checklist(),
                "state": _load_state()}

    @router.put("/checklist")
    async def put_checklist(request: Request):
        """서버 단계 진행상태 기록.

        서버에서 되읽을 수 없으므로(/exam/.htaccess 가 .json 을 403) 이 로컬
        기록이 유일한 발행 이력이다.
        """
        body = await request.json()
        state = _load_state()
        key = (body.get("key") or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="key 가 없습니다.")
        state[key] = {
            "done": bool(body.get("done")),
            "note": (body.get("note") or "").strip(),
            "at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        os.makedirs(PUBLISH_DIR, exist_ok=True)
        atomic_write_json(_STATE, state, indent=2)
        return {"ok": True, "state": state}

    return router
