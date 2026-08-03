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
        return {"path": books.active_path(), "first_run": books.is_first_run(),
                **books.active_meta()}

    @router.post("/confirm")
    async def confirm(request: Request):
        """지금 쓰고 있는(또는 넘긴) 폴더를 **사람이 지정한 것으로 확정**한다.

        첫 실행에는 `.env` 의 값을 잠정으로 쓰고 있을 뿐이라 `data/books.json` 이 없다.
        이 호출이 그 파일을 만들어 "지정했다" 로 바꾼다 — 그 뒤로는 그 폴더가 먼저 뜬다.
        """
        body = await request.json() if await request.body() else {}
        path = (body.get("path") or books.active_path()).strip()

        def run():
            if not os.path.isdir(path):
                raise ValueError(f"폴더가 없습니다: {path}")
            pd, label = books.guess_meta(path)
            r = books.add(path, pd=pd, label=label)
            r.update(books.select(path))
            r.update(_after_switch(path))
            r["first_run"] = books.is_first_run()
            return r

        return _guarded(run)

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

    @router.post("/ocr")
    async def set_ocr(request: Request):
        """이 작업 폴더에 딸린 **OCR 판독 폴더**를 지정한다(도구 #1 의 data/ 가 있는 곳).

        BOOK 과 따로 지정한다 — 판독 작업물(스캔 PNG · 초안 JSON)은 BOOK 밖에 있고,
        Claude Code 창과 이 앱이 같이 쓰는 폴더다.

        `ocr` 을 빈 문자열로 보내면 지정을 지운다 → BOOK 이름에서 유도로 되돌아간다
        (`ocr-output-260730` → 형제 폴더 `260730-ocr`).
        `pick: true` 면 OS 네이티브 폴더 선택창을 먼저 띄운다.
        """
        body = await request.json() if await request.body() else {}
        path = (body.get("path") or books.active_path()).strip()

        def run():
            ocr = (body.get("ocr") or "").strip()
            if body.get("pick"):
                from services.ocr import project
                start = ocr or project.ocr_dir() or os.path.dirname(path)
                picked = books.pick_folder(start)
                if not picked:
                    return {"picked": None, "cancelled": True}
                ocr = picked
            if ocr and not os.path.isdir(os.path.join(ocr, "data")):
                raise ValueError(
                    f"판독 폴더로 보이지 않습니다: {ocr}\n"
                    "그 안에 data\\raw_pages · data\\ocr_draft 가 있어야 합니다.")
            item = books.set_ocr_path(path, ocr)
            from services.ocr import project
            return {"ok": True, "item": item, "ocr": project.info()}

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
