"""/api/books — 작업 폴더 (품목 전환 = 폴더 권한).

★ 폴더를 바꾸면 /book 정적 마운트도 같이 갈아야 한다. 그 마운트는 부팅 시점의
  경로에 묶여 있어서, 안 갈면 폴더는 바뀌는데 mp4·이미지·PDF 가 옛 폴더에서
  나온다. app.py 가 등록해 둔 rebind 콜백을 여기서 부른다.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from fastapi import APIRouter, HTTPException, Request

from services.book import books, index as bindex

logger = logging.getLogger(__name__)

# app.py 가 부팅 때 넣어 주는 콜백. /book StaticFiles 의 경로를 갈아 준다.
_rebind: Callable[[str], bool] | None = None


def set_rebind(fn: Callable[[str], bool]) -> None:
    global _rebind
    _rebind = fn


def _after_switch(path: str) -> dict:
    """폴더가 바뀐 뒤 반드시 해야 하는 일 — 마운트 교체 + 캐시 무효화."""
    remounted = False
    if _rebind:
        try:
            remounted = bool(_rebind(path))
        except Exception as e:
            logger.warning("/book 마운트 교체 실패: %s", e)
    try:
        bindex.invalidate()      # 240문항 색인 캐시는 책마다 다르다
    except Exception:
        pass
    return {"remounted": remounted}


def setup_books_routes() -> APIRouter:
    router = APIRouter(prefix="/api/books", tags=["books"])

    def _guarded(fn):
        try:
            return fn()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

    @router.get("")
    @router.get("/")
    async def list_all():
        return books.list_books()

    @router.get("/active")
    async def active():
        return {"path": books.active_path(), **books.active_meta()}

    @router.post("/pick")
    async def pick(request: Request):
        """OS 네이티브 폴더 선택창을 띄운다.

        서버와 브라우저가 같은 PC 이므로 이게 성립한다(로컬 전용 앱).
        취소하면 picked=null 을 돌려준다 — 오류가 아니다.
        """
        body = await request.json() if await request.body() else {}
        start = (body.get("start") or books.active_path())

        def run():
            picked = books.pick_folder(start)
            if not picked:
                return {"picked": None, "cancelled": True}
            # pd 는 폴더 안 _book.json 에 있을 때만 채워진다. 이름으로 추측하지 않는다.
            pd, label = books.guess_meta(picked)
            return {"picked": picked, "scan": books.scan(picked),
                    "pd": pd, "label": label}

        return _guarded(run)

    @router.post("/add")
    async def add(request: Request):
        body = await request.json()
        path = (body.get("path") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="폴더 경로가 없습니다.")
        return _guarded(lambda: books.add(
            path, pd=(body.get("pd") or "").strip(),
            label=(body.get("label") or "").strip()))

    @router.post("/meta")
    async def meta(request: Request):
        """표시 이름·품목 코드를 고친다. 이름은 이 앱 안에서만 쓰는 값이다."""
        body = await request.json()
        path = (body.get("path") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="폴더 경로가 없습니다.")
        kw = {}
        if "label" in body:
            kw["label"] = str(body.get("label") or "")
        if "pd" in body:
            kw["pd"] = str(body.get("pd") or "")
        if not kw:
            raise HTTPException(status_code=400, detail="바꿀 값이 없습니다.")

        def run():
            r = books.set_meta(path, **kw)
            # pd 를 바꿨으면 발행 대상이 바뀐다 — 활성 폴더면 재바인딩까지
            if os.path.normcase(os.path.abspath(path)) == \
                    os.path.normcase(books.active_path()):
                r.update(_after_switch(path))
            return r

        return _guarded(run)

    @router.post("/select")
    async def select(request: Request):
        body = await request.json()
        path = (body.get("path") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="폴더 경로가 없습니다.")

        def run():
            r = books.select(path)
            r.update(_after_switch(path))
            return r

        return _guarded(run)

    @router.post("/remove")
    async def remove(request: Request):
        body = await request.json()
        path = (body.get("path") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="폴더 경로가 없습니다.")

        def run():
            r = books.remove(path)
            r.update(_after_switch(r["active"]))
            return r

        return _guarded(run)

    @router.post("/open")
    async def open_folder(request: Request):
        """탐색기로 폴더를 연다."""
        import os
        body = await request.json()
        path = (body.get("path") or books.active_path()).strip()
        if not os.path.isdir(path):
            raise HTTPException(status_code=404, detail=f"폴더가 없습니다: {path}")
        try:
            os.startfile(path)          # noqa: S606  (로컬 단일 사용자 앱)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"폴더를 열지 못했습니다: {e}") from e
        return {"ok": True, "path": path}

    return router
