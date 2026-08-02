"""/api/scan — 01/ 기출 OCR 문항 (구조화 MD로 정리).

위 판이 OCR 본문을 보여주고, 항목을 누르면 아래 판이 그 문제를 연다.
쓰기는 01/{qid}.md 하나만 건드린다 — 01/ 은 파이프라인의 시작점이라 하위 산물이 없다.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from core.constants import BOOK_DIR
from services.book import paths, scan

logger = logging.getLogger(__name__)


def setup_scan_routes() -> APIRouter:
    router = APIRouter(prefix="/api/scan", tags=["scan"])

    def _guarded(fn):
        try:
            return fn()
        except scan.ConflictError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except scan.LockedError as e:
            raise HTTPException(status_code=423, detail=str(e)) from e
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("")
    @router.get("/")
    async def list_all(unconfirmed: int = 0, q: str = ""):
        d = scan.list_items(unconfirmed=bool(unconfirmed), q=q)
        if not d.get("exists"):
            raise HTTPException(
                status_code=503,
                detail=d.get("error") or f"01/ 을 찾을 수 없습니다 ({BOOK_DIR}).")
        return d

    @router.get("/verify")
    async def verify():
        """01/*.md 왕복 검증. 통과하지 않으면 저장이 막힌다."""
        return scan.verify()

    @router.get("/{qid}")
    async def get_one(qid: str):
        if not scan.parse_qid(qid):
            raise HTTPException(status_code=400,
                                detail=f"문항 id 형식이 잘못됐습니다: {qid!r} (예: 01-17)")
        return _guarded(lambda: scan.read(qid))

    @router.put("/{qid}")
    async def put_one(qid: str, request: Request):
        if not scan.parse_qid(qid):
            raise HTTPException(status_code=400, detail=f"문항 id 형식이 잘못됐습니다: {qid!r}")
        v = scan.verify()
        if not v["ok"]:
            raise HTTPException(
                status_code=409,
                detail=(f"바이트 충실도 검증이 통과하지 않아 저장을 막았습니다 "
                        f"({v['passed']}/{v['total']}). "
                        "`/api/scan/verify` 로 원인을 확인하세요."))
        body = await request.json()
        return _guarded(lambda: scan.save(
            qid, body.get("values") or {}, flags=body.get("flags") or {},
            etag=body.get("etag")))

    @router.post("/{qid}/confirm")
    async def confirm(qid: str, request: Request):
        """확정 — verified·reviewed true, needs_review false."""
        if not scan.parse_qid(qid):
            raise HTTPException(status_code=400, detail=f"문항 id 형식이 잘못됐습니다: {qid!r}")
        body = await request.json() if await request.body() else {}
        return _guarded(lambda: scan.confirm(
            qid, bool(body.get("confirmed", True)), etag=body.get("etag")))

    return router
