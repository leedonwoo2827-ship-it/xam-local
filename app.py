"""XAM LOCAL — 문제은행 로컬 운영 콘솔.

도구 #1(exam-ocr-tool, 원격 산출) 과 #3(chodangi-mp4-forge, 로컬) 의 산물을
검수하고, axexam(그누보드5 웹) 파이프라인을 안전하게 호출해 웹으로 넘긴다.

이 파일은 페이지 HTML 과 정적 마운트만 담당한다. API 는 전부 routes/ 에 있다.
"""
import mimetypes
import os


def register_static_mime_types() -> None:
    """일부 Windows 환경의 잘못된 레지스트리 MIME 매핑을 덮어쓴다.

    .js  — text/javascript 가 아니면 ES 모듈이 화면만 뜨고 동작하지 않는다.
    .vtt — 레지스트리에 없으면 octet-stream 이 되고 브라우저가 <track> 을
           **오류 없이 조용히** 버린다(자막만 안 나온다). 가장 찾기 어려운 증상.
    """
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("application/javascript", ".mjs")
    mimetypes.add_type("text/vtt", ".vtt")
    mimetypes.add_type("video/mp4", ".mp4")
    # 씬별 음성 미리듣기 — 이게 없으면 <audio> 가 octet-stream 을 받고 조용히 안 울린다.
    mimetypes.add_type("audio/wav", ".wav")
    mimetypes.add_type("image/png", ".png")
    mimetypes.add_type("image/svg+xml", ".svg")
    mimetypes.add_type("application/json", ".json")


register_static_mime_types()

from dotenv import load_dotenv

# utf-8-sig: 메모장으로 저장한 .env 의 BOM 때문에 첫 키가 깨지는 흔한 문제 방지.
load_dotenv(encoding="utf-8-sig")

import logging

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.constants import (
    APP_NAME, APP_VERSION, AXEXAM_DIR, BASE_DIR, BOOK_DIR, ENGINE_DIR,
    DATA_DIR, JOBS_DIR, PD_CODE, PD_LABEL, PORT, PUBLISH_DIR, STATIC_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=APP_NAME,
    description="문제은행 로컬 운영 콘솔 — 문항 교정 · 영상 검수 · 발행",
    version=APP_VERSION,
)

# ========= 라우터 =========
# 각 계층은 독립적으로 미탑재일 수 있다. 하나가 없어도 앱은 뜬다 —
# 특히 BOOK 경로가 틀렸을 때 그걸 고칠 화면이 남아 있어야 한다.
_ROUTERS = (
    ("routes.books_routes", "setup_books_routes", "작업 폴더"),
    ("routes.book_routes", "setup_book_routes", "BOOK 개요"),
    ("routes.ocr_routes", "setup_ocr_routes", "OCR 검수(페이지 단위)"),
    ("routes.scan_routes", "setup_scan_routes", "구조화 MD"),
    ("routes.question_routes", "setup_question_routes", "문항 교정"),
    ("routes.verify_routes", "setup_verify_routes", "바이트 충실도 검증"),
    ("routes.render_routes", "setup_render_routes", "영상 렌더"),
    ("routes.render_routes", "setup_job_routes", "잡 조회"),
    ("routes.publish_routes", "setup_publish_routes", "발행"),
    ("routes.summary_routes", "setup_summary_routes", "요약노트"),
)

for _mod, _factory, _label in _ROUTERS:
    try:
        _m = __import__(_mod, fromlist=[_factory])
        app.include_router(getattr(_m, _factory)())
    except (ImportError, AttributeError):
        logger.warning("%s 미탑재 — %s API 비활성", _mod, _label)

# ========= 정적 파일 =========
class _NoCacheStatic(StaticFiles):
    """앱 코드는 캐시하지 않는다.

    ★ ES 모듈은 브라우저가 아주 공격적으로 캐시한다. util.js 를 고쳐도 이미 열린 탭은
      예전 모듈을 계속 써서, 새로 추가한 export 를 "does not provide an export named …"
      로 거부한다. 실제로 그 사고가 났다 — 파일도 서버도 정상인데 화면만 깨져서
      원인이 코드에 있는 줄 알게 된다.

      로컬 단일 사용자 앱이라 캐시로 얻을 게 없다. 폰트만 예외로 둔다(1.2MB, 안 바뀜).
    """

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if path.replace("\\", "/").startswith("fonts/"):
            resp.headers["Cache-Control"] = "public, max-age=604800"
        else:
            resp.headers["Cache-Control"] = "no-store, must-revalidate"
        return resp


app.mount("/static", _NoCacheStatic(directory=STATIC_DIR), name="static")

# BOOK 트리를 읽기 전용으로 그대로 노출한다 — mp4 · vtt · svg · deck.html 미리보기용.
# ★ Range 처리를 직접 구현하지 않는다. starlette 의 FileResponse 가 이미
#   206 Partial Content / Accept-Ranges / 416 을 낸다. mp4 드래그 탐색이 공짜로 된다.
#
# ★ 이 마운트는 부팅 시점의 경로에 묶인다. 작업 폴더를 바꾸면 반드시 같이 갈아야
#   한다 — 안 갈면 폴더는 바뀌는데 영상·그림이 옛 폴더에서 나온다.
#   그래서 항상 만들어 두고(없는 폴더라도), rebind_book() 으로 경로를 교체한다.
def _initial_book_dir() -> str:
    try:
        from services.book import books
        return books.active_path()
    except Exception:
        return BOOK_DIR


_book_dir_now = _initial_book_dir()
if not os.path.isdir(_book_dir_now):
    logger.warning("BOOK 경로가 없습니다 — /book 은 빈 폴더를 가리킵니다: %s", _book_dir_now)
    os.makedirs(os.path.join(DATA_DIR, "_nobook"), exist_ok=True)
    _book_static = StaticFiles(directory=os.path.join(DATA_DIR, "_nobook"))
else:
    _book_static = StaticFiles(directory=_book_dir_now)
app.mount("/book", _book_static, name="book")


def rebind_book(path: str) -> bool:
    """/book 마운트를 새 폴더로 갈아 끼운다.

    StaticFiles 는 directory 와 all_directories 를 들고 있으므로 둘 다 바꿔야 한다
    (lookup_path 가 all_directories 를 훑는다). 마운트를 새로 만들지 않는 이유는
    app.router.routes 를 런타임에 재배치하면 다른 라우트 순서까지 흔들리기 때문이다.
    """
    if not os.path.isdir(path):
        logger.warning("/book 교체 실패 — 폴더가 없습니다: %s", path)
        return False
    try:
        _book_static.directory = path
        _book_static.all_directories = _book_static.get_directories(path, None)
        logger.info("/book → %s", path)
        return True
    except Exception:
        logger.exception("/book 마운트 교체 실패")
        return False


# ========= 페이지 =========
@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/home")
async def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/mock")
async def mock():
    """UI/UX 확정용 목업 모음. 확정되면 static/_mock/ 과 함께 지운다."""
    p = os.path.join(STATIC_DIR, "_mock", "index.html")
    if not os.path.isfile(p):
        return JSONResponse(status_code=404, content={"detail": "목업이 없습니다."})
    return FileResponse(p)


@app.get("/api/version")
async def version():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "port": PORT,
        "pd": PD_CODE,
        "pd_label": PD_LABEL,
        "book": _initial_book_dir(),
        "engine": ENGINE_DIR,
        "axexam": AXEXAM_DIR,
    }


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.exception_handler(500)
async def internal_error(request: Request, exc: Exception):
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류"})


def _bootstrap() -> None:
    os.makedirs(JOBS_DIR, exist_ok=True)

    # 작업 폴더 화면이 폴더를 바꿀 때 /book 마운트를 갈 수 있도록 콜백을 넘긴다.
    try:
        from routes import books_routes
        books_routes.set_rebind(rebind_book)
    except ImportError:
        logger.warning("routes.books_routes 미탑재 — 폴더 전환 시 /book 이 안 바뀝니다")

    os.makedirs(PUBLISH_DIR, exist_ok=True)

    # starlette 버전 경고 — mp4 탐색이 Range 지원에 달려 있다.
    try:
        import starlette
        parts = tuple(int(x) for x in starlette.__version__.split(".")[:2])
        if parts < (0, 40):
            logger.warning(
                "starlette %s — FileResponse Range 지원이 없을 수 있습니다. "
                "mp4 드래그 탐색이 안 되면 `pip install -U fastapi` 하십시오.",
                starlette.__version__,
            )
    except Exception:
        pass

    # ImportError 로 잡는다 — services.jobs 패키지는 있고 registry 모듈만 없을 때
    # 나오는 예외가 ModuleNotFoundError 가 아니라 ImportError 다.
    try:
        from services.jobs import registry
        restored, broken = registry.restore_history()
        if restored:
            logger.info("지난 작업 %d건 복원 (끊긴 작업 %d건 정리)", restored, broken)
    except ImportError:
        logger.warning("services.jobs.registry 미탑재 — 잡 이력 복원 생략")

    if not os.path.isdir(BOOK_DIR):
        logger.error("BOOK 경로를 찾을 수 없습니다: %s  (.env 의 XAM_BOOK 확인)", BOOK_DIR)


_bootstrap()
logger.info("%s %s — pd=%s  book=%s", APP_NAME, APP_VERSION, PD_CODE, BOOK_DIR)
logger.info("base=%s", BASE_DIR)
