"""/api/questions — 문항 목록 · 읽기 · 저장 · 검수.

저장 실패는 상태 코드로 구분한다. 프론트의 api() 헬퍼가 err.status 를 보존하므로
화면이 그걸로 분기한다.
    400  검증 실패 (보기 개수, 정답 범위, subject_no 타입 …)
    409  화면을 연 뒤 디스크가 바뀌었다 → 다시 읽으라고 안내
    423  파일이 잠겨 있다 (편집기에서 열어 둔 경우) → 닫고 재시도
    503  BOOK 경로 오류
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from core.constants import BOOK_DIR
from services.book import index as bindex, paths, store, verify

logger = logging.getLogger(__name__)


def setup_question_routes() -> APIRouter:
    router = APIRouter(prefix="/api/questions", tags=["questions"])

    def _require_book() -> None:
        if not paths.exists():
            raise HTTPException(
                status_code=503,
                # ★ 02/ 를 만드는 것은 이 앱이 아니라 도구 #2(Claude Desktop 스킬)다.
                #   예전 문구는 '구조화 MD로 정리' 화면으로 보냈는데, 그 화면은 01/ 을
                #   손보는 곳이라 따라가도 02/ 가 생기지 않는다.
                detail=(f"이 작업 폴더는 아직 01/ 단계입니다: {paths.book_dir()}\n"
                        + ("_rounds/ 와 02/ 는 도구 #2(Claude Desktop 스킬)가 01/ 을 "
                           "읽어 만듭니다. 그때까지 'OCR 검수' 와 '구조화 MD로 정리' 를 "
                           "쓰세요."
                           if paths.scan_exists()
                           else "00/ 에 원본 PDF 를 넣고 'OCR 검수' 의 [PDF 렌더] 부터 "
                                "시작하세요.")),
            )

    def _guarded(fn):
        """store 의 예외를 HTTP 상태 코드로 옮긴다."""
        try:
            return fn()
        except store.ConflictError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except store.LockedError as e:
            raise HTTPException(status_code=423, detail=str(e)) from e
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("")
    @router.get("/")
    async def list_questions(
        round: str = "", subject: str = "", difficulty: str = "",
        unreviewed: int = 0, figure: str = "", q: str = "",
        limit: int = 0, offset: int = 0,
    ):
        _require_book()
        has_figure = None
        if figure in ("1", "true", "yes"):
            has_figure = True
        elif figure in ("0", "false", "no"):
            has_figure = False
        return bindex.query(
            round_code=round, subject=subject, difficulty=difficulty,
            unreviewed=bool(unreviewed), has_figure=has_figure, q=q,
            limit=limit, offset=offset,
        )

    @router.get("/next-unreviewed")
    async def next_unreviewed(after: str = ""):
        _require_book()
        return {"id": bindex.next_unreviewed(after)}

    @router.get("/{qid}")
    async def get_question(qid: str):
        _require_book()
        return _guarded(lambda: store.read(qid))

    @router.get("/{qid}/source")
    async def get_source(qid: str):
        """기출 원문(01/xx.md) — 에디터 우측 드로어."""
        _require_book()
        return _guarded(lambda: store.read_source(qid))

    @router.get("/{qid}/preview")
    async def preview(qid: str):
        """디스크에 쓰지 않고, 저장하면 나올 02/*.md 전문을 미리 보여준다."""
        _require_book()

        def run():
            from services.book import md, rounds
            p = paths.parse_qid(qid)
            if not p:
                raise ValueError(f"문항 id 형식이 잘못됐습니다: {qid!r}")
            rc = paths.round_code(p[0])
            doc = rounds.load(rc)
            question = rounds.question_of(doc, p[1])
            if question is None:
                raise KeyError(f"{qid} 를 찾을 수 없습니다.")
            md_path = paths.q_md(qid)
            return {
                "id": qid,
                "md": md.render(question, rounds.meta_of(doc), md.flags_for(question, md_path)),
                "path": paths.rel(md_path),
            }

        return _guarded(run)

    @router.put("/{qid}")
    async def save_question(qid: str, request: Request):
        """5파일 트랜잭션. 실제로 쓴 파일 목록을 응답에 담는다.

        ★ 저장 전에 바이트 충실도 게이트를 확인한다. 렌더러가 원본을 재현하지
          못하는 상태에서 쓰면 편집한 문항 하나가 나머지 산물을 손상시킨다.
        """
        _require_book()
        gate = verify.run_all()
        if not gate.get("ok"):
            raise HTTPException(
                status_code=409,
                detail=("바이트 충실도 검증이 통과하지 않아 저장을 막았습니다.\n"
                        f"md {gate['summary']['md']} · "
                        f"index {gate['summary']['index']} · "
                        f"lesson {gate['summary']['lesson']}\n"
                        "`python -m services.book.verify` 로 원인을 확인하세요."),
            )

        body = await request.json()
        values = body.get("values") or {}
        flags = body.get("flags") or {}
        etag = body.get("etag")
        return _guarded(lambda: store.save(qid, values, flags, etag))

    @router.post("/{qid}/review")
    async def review(qid: str, request: Request):
        """검수 플래그만 뒤집는 핫패스. 내용은 건드리지 않는다."""
        _require_book()
        body = await request.json()
        reviewed = bool(body.get("reviewed", True))
        etag = body.get("etag")
        return _guarded(lambda: store.set_review(qid, reviewed, etag))

    @router.post("/bulk-review")
    async def bulk_review(request: Request):
        """여러 문항을 한 번에 검수완료. 충돌한 문항은 건너뛰고 목록으로 알린다."""
        _require_book()
        body = await request.json()
        ids = body.get("ids") or []
        reviewed = bool(body.get("reviewed", True))
        updated, conflicts, failed = [], [], []
        for qid in ids:
            try:
                # etag 를 넘기지 않는다 — 일괄 처리는 '지금 상태 기준' 이 맞다.
                store.set_review(qid, reviewed, etag=None)
                updated.append(qid)
            except store.ConflictError:
                conflicts.append(qid)
            except Exception as e:
                failed.append({"id": qid, "error": str(e)})
        return {"ok": not failed, "updated": updated,
                "conflicts": conflicts, "failed": failed}

    @router.post("/reindex")
    async def reindex(request: Request):
        """02/_index.json · difficulty_stats.json 만 다시 쓴다.

        ★ md 240개는 다시 쓰지 않는다. 드리프트 복구용 안전한 출구다.
        """
        _require_book()
        bindex.invalidate()
        res = bindex.write()
        return {"ok": True, **res}

    return router
