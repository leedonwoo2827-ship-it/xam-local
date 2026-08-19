"""/api/render — 번들 상태 · 사전점검 · 렌더 잡.
   /api/jobs   — 렌더·발행 공용 잡 조회 (셸의 최근 작업 목록도 이걸 쓴다)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core.speak import speak_numbers
from services.book import paths
from services.jobs import jobstore, registry
from services.render import bundles, lexicon, precheck, runner, speech

logger = logging.getLogger(__name__)


def _need_bundle(code: str) -> None:
    """번들 코드 형식 검사 — 네 곳이 같은 문구를 되풀이하고 있었다."""
    if not paths.parse_bundle(code):
        raise HTTPException(status_code=400, detail=f"번들 코드 형식이 잘못됐습니다: {code!r}")


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
        _need_bundle(code)
        return {"info": bundles.scan_one(code), "toc": bundles.review_toc(code)}

    @router.get("/api/render/bundles/{code}/scenes")
    async def bundle_scenes(code: str):
        """씬별 슬라이드 · 음성 · 자막 — 화면 바닥의 실행 판이 이걸 쓴다."""
        _need_bundle(code)
        d = bundles.scenes(code)
        if not d["ok"]:
            raise HTTPException(status_code=404, detail=d.get("error") or "씬을 읽을 수 없습니다.")
        return d

    # ── 발음대본 ────────────────────────────────────────────────────────────
    #
    # 자막은 그대로 두고 **발음만** 고친다. 두 값은 script.json 의 `narration`(자막)과
    # `narration_text`(발음)로 갈리고, 손수정은 `<번들>_speech.json` 에 남아 재베이크를
    # 견딘다(services/render/speech.py 머리말).
    @router.get("/api/render/bundles/{code}/speech")
    async def get_speech(code: str):
        _need_bundle(code)
        d = speech.read(code)
        d["stale_scenes"] = speech.stale_scenes(code)
        return d

    @router.post("/api/render/bundles/{code}/speech")
    async def put_speech(code: str, request: Request):
        """그 씬의 발음을 저장한다. `text` 가 비면 덮어쓰기를 지운다(원문 낭독으로)."""
        _need_bundle(code)
        body = await request.json()
        try:
            scene = int(body.get("scene"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="scene 이 없습니다.") from None
        try:
            return speech.save(code, scene, body.get("text") or "",
                               src=body.get("subtitle") or "")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    @router.post("/api/render/bundles/{code}/resynth")
    async def do_resynth(code: str, request: Request):
        """그 씬 wav 하나만 다시 만든다. mp4·통합자막은 그대로 — 번들 재렌더가 낸다."""
        _need_bundle(code)
        body = await request.json()
        try:
            scene = int(body.get("scene"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="scene 이 없습니다.") from None
        # ★ 렌더와 같은 TTS 엔진(같은 GPU·모델)을 쓴다. 동시에 돌리면 둘 다 느려지거나
        #   모델 적재에서 부딪힌다 — 렌더는 원래 동시 1개만 허용한다.
        if registry.running("render"):
            raise HTTPException(
                status_code=409,
                detail="렌더가 돌고 있습니다 — 같은 엔진을 쓰므로 끝난 뒤에 하세요.")
        try:
            return speech.resynth(code, scene, text=body.get("text") or "")
        except (ValueError, RuntimeError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # ── 용어 사전 ───────────────────────────────────────────────────────────
    #
    # 발음 고침의 **1차 자리**다. 한 줄 넣으면 전 품목에 걸리고 자막은 원문을 지킨다.
    # 씬마다 손으로 고치는 것보다 싸므로, 되풀이되는 용어는 여기로 올린다.
    @router.get("/api/render/lexicon")
    async def get_lexicon(round: str = ""):
        d = lexicon.read()
        # 사전에 없어서 낱자로 읽히는 약어 — 빈 화면을 주지 않으려고 후보를 같이 낸다
        d["candidates"] = lexicon.candidates(round)
        return d

    @router.post("/api/render/lexicon")
    async def put_lexicon(request: Request):
        body = await request.json()
        try:
            if body.get("remove"):
                return lexicon.remove(body.get("term") or "")
            return lexicon.save(body.get("term") or "", body.get("say") or "")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/api/render/speak-numbers")
    async def do_speak_numbers(request: Request):
        """숫자를 소리대로 — **발음 칸 안에서만** 쓴다(자막에서 다시 만들지 않는다)."""
        body = await request.json()
        return {"text": speak_numbers(body.get("text") or "")}

    @router.get("/api/render/bundles/{code}/precheck")
    async def do_precheck(code: str):
        _need_bundle(code)
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
