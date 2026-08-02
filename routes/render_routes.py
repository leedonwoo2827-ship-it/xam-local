"""/api/render — 번들 상태 · 사전점검 · 렌더 잡.
   /api/jobs   — 렌더·발행 공용 잡 조회 (셸의 최근 작업 목록도 이걸 쓴다)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from services.book import paths
from services.jobs import jobstore, registry
from services.render import bundles, precheck, runner

logger = logging.getLogger(__name__)


def setup_render_routes() -> APIRouter:
    router = APIRouter(tags=["render"])

    # ── 번들 ────────────────────────────────────────────────────────────────
    @router.get("/api/render/env")
    async def env():
        return runner.env_info()

    @router.get("/api/render/bundles")
    async def list_bundles():
        items = bundles.scan_all()
        counts = {"done": 0, "stale": 0, "missing": 0, "broken": 0}
        for i in items:
            counts[i["status"]] = counts.get(i["status"], 0) + 1
        return {"count": len(items), "counts": counts, "items": items}

    @router.get("/api/render/bundles/{code}")
    async def one_bundle(code: str):
        if not paths.parse_bundle(code):
            raise HTTPException(status_code=400, detail=f"번들 코드 형식이 잘못됐습니다: {code!r}")
        return {"info": bundles.scan_one(code), "toc": bundles.review_toc(code)}

    @router.get("/api/render/bundles/{code}/scenes")
    async def bundle_scenes(code: str):
        """씬별 슬라이드 · 음성 · 자막 — 화면 바닥의 실행 판이 이걸 쓴다."""
        if not paths.parse_bundle(code):
            raise HTTPException(status_code=400, detail=f"번들 코드 형식이 잘못됐습니다: {code!r}")
        d = bundles.scenes(code)
        if not d["ok"]:
            raise HTTPException(status_code=404, detail=d.get("error") or "씬을 읽을 수 없습니다.")
        return d

    @router.get("/api/render/bundles/{code}/precheck")
    async def do_precheck(code: str):
        if not paths.parse_bundle(code):
            raise HTTPException(status_code=400, detail=f"번들 코드 형식이 잘못됐습니다: {code!r}")
        return precheck.run(code)

    # ── 렌더 잡 ─────────────────────────────────────────────────────────────
    @router.post("/api/render/jobs")
    async def start_render(request: Request):
        body = await request.json()
        codes = body.get("codes")
        no_audio = bool(body.get("no_audio"))
        keep_scratch = bool(body.get("keep_scratch"))
        stop_on_error = bool(body.get("stop_on_error", True))

        all_codes = paths.all_bundles()
        if codes == "all" or codes is None:
            codes = all_codes
        elif codes == "missing":
            codes = [b["code"] for b in bundles.scan_all()
                     if b["status"] in ("missing", "stale")]
        elif isinstance(codes, str):
            codes = [codes]
        codes = [c for c in codes if c in all_codes]
        if not codes:
            raise HTTPException(status_code=400, detail="렌더할 번들이 없습니다.")

        busy = registry.running("render")
        if busy:
            raise HTTPException(
                status_code=409,
                detail=("이미 렌더가 돌고 있습니다 — 동시에 하나만 실행됩니다. "
                        f"진행 중: {busy.get('label')} ({busy.get('current') or '준비 중'})"))
        try:
            job = runner.start(codes, no_audio=no_audio, keep_scratch=keep_scratch,
                               stop_on_error=stop_on_error)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return registry.view(job)

    return router


def setup_job_routes() -> APIRouter:
    """잡 조회는 렌더·발행이 공유한다."""
    router = APIRouter(prefix="/api/jobs", tags=["jobs"])

    @router.get("")
    @router.get("/")
    async def list_jobs(limit: int = 20, kind: str = ""):
        return {"jobs": registry.list_jobs(limit=limit, kind=kind)}

    @router.get("/{job_id}")
    async def get_job(job_id: str, log_from: int = 0):
        job = registry.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        return registry.view(job, log_from=log_from)

    @router.get("/{job_id}/log")
    async def full_log(job_id: str):
        p = jobstore.log_path(job_id)
        if not p:
            raise HTTPException(status_code=404, detail="로그 파일이 없습니다.")
        return FileResponse(p, media_type="text/plain; charset=utf-8",
                            filename=f"{job_id}.log")

    @router.post("/{job_id}/cancel")
    async def cancel(job_id: str):
        job = registry.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        if job.get("kind") == "render":
            ok = runner.cancel(job_id)
        else:
            ok = registry.request_cancel(job_id)
        if not ok:
            raise HTTPException(status_code=409, detail="이미 끝난 작업입니다.")
        return {"ok": True}

    return router
