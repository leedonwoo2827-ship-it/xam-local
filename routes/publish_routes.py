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
