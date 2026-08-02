"""/api/summary — 요약노트 4과목 검수.

★ 우리는 .md 만 고친다. 그런데 axexam 의 build_check.py::build_theory 는
  03/summary_*.html 을 발행한다. 즉 .md 수정은 웹에 반영되지 않는다.
  이 사실을 API 응답 · 화면 배너 · 발행 사전점검 세 곳에서 모두 말한다 —
  조용히 넘기면 "고쳤는데 사이트에 반영이 안 된다" 는 최악의 혼란이 된다.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request

from core.constants import SUMMARY_KEYS
from core.atomic_io import atomic_write_text, backup_sibling
from services.book import paths

logger = logging.getLogger(__name__)

DRIFT_TEXT = (".md 를 고쳤지만 .html 은 다시 만들어지지 않았습니다. "
              "발행되는 것은 .html 입니다 — 도구 #1/#2 에서 HTML 을 재생성해야 "
              "사이트에 반영됩니다.")


def _read(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _drift(key: str) -> bool:
    html, md = paths.summary_html(key), paths.summary_md(key)
    if not (os.path.isfile(html) and os.path.isfile(md)):
        return False
    return paths.mtime(html) < paths.mtime(md)


def setup_summary_routes() -> APIRouter:
    router = APIRouter(prefix="/api/summary", tags=["summary"])

    @router.get("")
    @router.get("/")
    async def list_all():
        items = []
        for key in SUMMARY_KEYS:
            html, md = paths.summary_html(key), paths.summary_md(key)
            items.append({
                "key": key,
                "html_path": paths.rel(html),
                "md_path": paths.rel(md),
                "html_bytes": paths.size(html),
                "md_bytes": paths.size(md),
                "html_exists": os.path.isfile(html),
                "md_exists": os.path.isfile(md),
                "html_url": paths.book_url(html),
                "drift": _drift(key),
            })
        idx = paths.summary_index_html()
        return {"items": items,
                "index_url": paths.book_url(idx) if os.path.isfile(idx) else None,
                "drift_text": DRIFT_TEXT}

    @router.get("/{key}")
    async def get_one(key: str):
        if key not in SUMMARY_KEYS:
            raise HTTPException(status_code=404, detail=f"알 수 없는 요약노트: {key!r}")
        md_path = paths.summary_md(key)
        text = _read(md_path)
        if text is None:
            raise HTTPException(status_code=404,
                                detail=f"{paths.rel(md_path)} 가 없습니다.")
        return {"key": key, "md": text, "etag": paths.etag(md_path),
                "html_url": paths.book_url(paths.summary_html(key)),
                "drift": _drift(key), "drift_text": DRIFT_TEXT}

    @router.put("/{key}")
    async def put_one(key: str, request: Request):
        if key not in SUMMARY_KEYS:
            raise HTTPException(status_code=404, detail=f"알 수 없는 요약노트: {key!r}")
        body = await request.json()
        text = body.get("md")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(status_code=400, detail="본문이 비어 있습니다.")

        md_path = paths.summary_md(key)
        etag = body.get("etag")
        if etag is not None and etag != paths.etag(md_path):
            raise HTTPException(
                status_code=409,
                detail=("이 파일이 화면을 연 뒤에 바뀌었습니다. 새로고침해 최신 내용을 "
                        "확인한 뒤 다시 수정해 주세요."))
        try:
            backup_sibling(md_path)
            atomic_write_text(md_path, text)
        except PermissionError as e:
            raise HTTPException(
                status_code=423,
                detail=(f"파일을 저장하지 못했습니다: {paths.rel(md_path)}. "
                        "편집기에서 열어 두었다면 닫고 다시 시도하세요.")) from e

        return {"ok": True, "key": key, "etag": paths.etag(md_path),
                "written": [paths.rel(md_path)],
                "drift": True, "warning": DRIFT_TEXT}

    return router
