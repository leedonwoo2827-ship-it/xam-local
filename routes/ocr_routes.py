"""/api/ocr — 도구 #1(OCR 검수) 의 페이지 단위 작업.

레이어는 이 앱의 UX 원칙을 따른다.
    위층 패널  `/api/ocr/overview`            페이지 목록 (고르는 곳)
    아래층 바탕 `/api/ocr/draft/{src}/{page}`  그 페이지 작업 (일하는 곳)

`services/scan_routes.py` 는 **확정된 `01/*.md` 를 한 문항씩** 손보는 화면이고,
여기는 **초안을 페이지 단위로** 검수해 그 `01/*.md` 를 만드는 화면이다. 둘 다 남는다.

★ 판독(OCR)은 여기에 없다. Claude Code 창이 `raw_pages/*.png` 를 읽어 초안을 쓴다.
"""
from __future__ import annotations

import io
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from services.book import paths
from services.ocr import answers as ocr_answers
from services.ocr import checks, draft, finalize, pdfrender, project

logger = logging.getLogger(__name__)


def setup_ocr_routes() -> APIRouter:
    router = APIRouter(prefix="/api/ocr", tags=["ocr"])

    def _need_project() -> None:
        if not project.exists():
            raise HTTPException(
                status_code=503,
                detail=(f"OCR 판독 폴더를 찾을 수 없습니다: "
                        f"{project.ocr_dir() or '(미지정)'}. "
                        "좌하단 작업 폴더 패널에서 지정하거나 .env 의 XAM_OCR 을 채우세요."))

    # ── 위층 패널: 페이지 목록 ──────────────────────────────────────────────
    @router.get("/overview")
    async def overview():
        """회차별로 묶은 페이지 목록 + 책 정보. ★ 캐시하지 않는다 —
        Claude Code 창에서 새 초안을 만들면 패널만 다시 열어도 보여야 한다."""
        info = project.info()
        if not info["exists"]:
            return {"exists": False, "info": info, "pages": [], "finalized": {},
                    "error": (f"OCR 판독 폴더가 없습니다: "
                              f"{project.ocr_dir() or '(미지정)'}")}

        pm = project.page_map()
        pages = []
        for src in project.visible_srcs():
            entry = project.source_entry(src)
            for page in project.list_pages(src):
                meta = pm.get(f"{src}:{page}", {})
                d = draft.load(src, page)
                qs = (d or {}).get("questions") or []
                pages.append({
                    "src": src,
                    "page": page,
                    "role": entry.get("role") or "문제",
                    "pair": entry.get("pair") or "",
                    "round": meta.get("round") or (d or {}).get("round"),
                    "round_label": (meta.get("round_label")
                                    or (d or {}).get("round_label") or ""),
                    "question_range": meta.get("question_range"),
                    "has_draft": d is not None,
                    "n_questions": len(qs),
                    "n_verified": sum(1 for q in qs if q.get("verified")),
                })

        # 확정 현황 — 01/ 의 {RR}-{NN}.md 를 회차별로 센다(상수 없음).
        finalized: dict[str, int] = {}
        stage = os.path.join(paths.book_dir(), "01")
        if os.path.isdir(stage):
            for f in sorted(os.listdir(stage)):
                if f.endswith(".md") and not f.startswith("_") and len(f) >= 5:
                    finalized[f[:2]] = finalized.get(f[:2], 0) + 1

        gate_ok, gate_msg = checks.gate_ok()
        return {"exists": True, "info": info, "pages": pages,
                "finalized": finalized,
                "gate": {"ok": gate_ok, "message": gate_msg}}

    # ── 아래층 바탕: 페이지 초안 ────────────────────────────────────────────
    @router.get("/draft/{src}/{page}")
    async def get_draft(src: str, page: int):
        _need_project()
        d = draft.load_or_skeleton(src, page)
        entry = project.source_entry(src)
        d["_meta"] = {
            "source_pdf": project.source_pdf_name(src),
            "role": entry.get("role") or "문제",
            "pair": entry.get("pair") or "",
            "scan": f"/api/ocr/scan/{src}/{page}",
            "has_scan": os.path.isfile(project.scan_png(src, page)),
            "pages": project.list_pages(src),
            "questions_per_round": project.questions_per_round(),
            "subjects": project.subjects(),
        }
        return d

    @router.post("/draft/{src}/{page}")
    async def post_draft(src: str, page: int, request: Request):
        """초안 저장. 확정과 달리 게이트를 보지 않는다 — 초안은 작업 중인 값이다."""
        _need_project()
        body = await request.json()
        body.pop("_meta", None)
        try:
            p, wrote = draft.save(src, page, body)
        except PermissionError as e:
            raise HTTPException(status_code=423, detail=(
                f"초안을 저장하지 못했습니다: {os.path.basename(str(e.filename or ''))}. "
                "편집기에서 열어 두었다면 닫고 다시 시도하세요.")) from e
        return {"ok": True, "path": p, "wrote": wrote}

    # ── 스캔 이미지 · 크롭 미리보기 ─────────────────────────────────────────
    @router.get("/scan/{src}/{page}")
    async def scan_image(src: str, page: int):
        p = project.scan_png(src, page)
        if not os.path.isfile(p):
            raise HTTPException(status_code=404, detail=(
                f"스캔 이미지가 없습니다: {src} p.{page}. "
                "`python -m services.ocr.pdfrender` 로 렌더하세요."))
        return FileResponse(p, media_type="image/png")

    @router.get("/crop")
    async def crop(src: str, page: int, x: int, y: int, w: int, h: int):
        """드래그한 영역 미리보기. 확정 전이라 파일로 굳히지 않는다."""
        p = project.scan_png(src, page)
        if not os.path.isfile(p):
            raise HTTPException(status_code=404, detail="스캔 이미지가 없습니다.")
        from PIL import Image
        img = Image.open(p)
        buf = io.BytesIO()
        img.crop((x, y, x + w, y + h)).save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png")

    @router.get("/figure/{name}")
    async def figure(name: str):
        """확정된 그림 — 01/images/ 아래."""
        p = os.path.join(paths.book_dir(), "01", "images", os.path.basename(name))
        if not os.path.isfile(p):
            raise HTTPException(status_code=404, detail="그림 파일이 없습니다.")
        return FileResponse(p, media_type="image/png")

    # ── 확정 ────────────────────────────────────────────────────────────────
    @router.post("/finalize")
    async def do_finalize(request: Request):
        """`{src, page, questions:[…]}` → 01/{RR}-{NN}.md 기록 + 그림 크롭.

        ★ 확정 왕복 게이트를 먼저 본다. 통과하지 않는 렌더러로 확정하면 이미
          검수해 둔 01/*.md 가 조용히 바뀐다.
        """
        _need_project()
        ok, msg = checks.gate_ok()
        if not ok:
            raise HTTPException(status_code=409, detail=msg)

        body = await request.json()
        src = str(body.get("src") or "")
        page = int(body.get("page") or 0)
        questions = body.get("questions") or []
        if not src or not page:
            raise HTTPException(status_code=400, detail="src · page 가 필요합니다.")
        try:
            return finalize.finalize_page(src, page, questions)
        except finalize.LockedError as e:
            raise HTTPException(status_code=423, detail=str(e)) from e
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # ── 검증 · 도구 ─────────────────────────────────────────────────────────
    @router.get("/verify")
    async def verify():
        """확정 왕복 게이트 + 회차 정합성. 화면의 `검증` 버튼이 쓴다."""
        return {"refinalize": checks.refinalize(),
                "rounds": checks.verify_all_rounds()}

    @router.get("/render/plan")
    async def render_plan():
        """00/ 의 PDF 를 어떻게 렌더할지. 중복·역할·짝이 여기서 보인다."""
        return pdfrender.run(dry=True)

    @router.post("/render")
    async def do_render(request: Request):
        """00/*.pdf → raw_pages/*.png. 이미 있는 소스는 건너뛴다(force 로 강제)."""
        _need_project()
        body = await request.json() if await request.body() else {}
        return pdfrender.run(force=bool(body.get("force")))

    @router.post("/answers/merge")
    async def merge_answers(request: Request):
        """분리형 교재의 정답·해설을 초안에 주입."""
        _need_project()
        body = await request.json() if await request.body() else {}
        r = ocr_answers.merge(body.get("src") or None,
                              body.get("round") or None,
                              force=bool(body.get("force")),
                              check=bool(body.get("check", True)))
        if not r["ok"]:
            raise HTTPException(status_code=404, detail=r["error"])
        return r

    return router
