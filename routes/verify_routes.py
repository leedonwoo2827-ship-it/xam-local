"""/api/verify — 바이트 충실도 왕복 검증.

디스크에 아무것도 쓰지 않는다. 240 md + 2 json + 24 lesson 을 메모리에서 렌더해
원본과 바이트 비교한다. 이 검증이 통과하지 않으면 문항 저장이 막힌다.
"""
from __future__ import annotations

from fastapi import APIRouter

from services.book import lesson, verify


def setup_verify_routes() -> APIRouter:
    router = APIRouter(prefix="/api/verify", tags=["verify"])

    @router.get("/roundtrip")
    async def roundtrip():
        return verify.run_all()

    @router.get("/speech-drift")
    async def speech_drift():
        """05 lesson 의 낭독문이 _rounds 와 다른 문항.

        실측 2건(m01-47 · m02-47)은 TTS 손질이다 — "(R)" 을 "괄호 알 괄호" 로 읽지
        않게 lesson 쪽에서 고쳐 둔 것. 낭독문을 직접 편집하지 않는 한 유지한다.
        """
        rows = lesson.speech_drift()
        return {"count": len(rows), "items": rows}

    return router
