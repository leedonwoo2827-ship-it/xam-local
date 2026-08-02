"""경로·버전·품목 코드 — 이 앱의 모든 절대 경로가 여기서만 결정된다.

BOOK / CHODANGI / AXEXAM 은 전부 이 PC 밖에 있는 외부 트리다. 하드코딩 기본값을
두되 .env 로 덮어쓸 수 있게 해야, 책이 하나 더 생겼을 때 코드를 안 고친다.
"""
from __future__ import annotations

import os

APP_VERSION = "0.1.0"
APP_NAME = "XAM LOCAL"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
PUBLISH_DIR = os.path.join(DATA_DIR, "publish")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")


def _env_path(key: str, default: str) -> str:
    """경로 환경변수 — 빈 문자열은 '미설정' 으로 보고 기본값을 쓴다."""
    v = (os.getenv(key) or "").strip().strip('"')
    return os.path.abspath(v) if v else os.path.abspath(default)


# ── 외부 트리 ────────────────────────────────────────────────────────────────
# BOOK: 도구 #1(exam-ocr-tool)이 원격 세션에서 만들어 동기화해 준 산출물 트리.
#       00/ 01/ 02/ 03/ 04/ 05/ 06/ _rounds/ 를 갖는다.
BOOK_DIR = _env_path("XAM_BOOK", r"D:\00work\ocr-output-260730")

# CHODANGI: 도구 #3. make_bundle_video.py 를 이 폴더에서 cwd 로 실행한다.
CHODANGI_DIR = _env_path("XAM_CHODANGI", r"D:\00work\chodangi-mp4-forge-main")

# AXEXAM: 웹(그누보드) 저장소. scripts/build_check.py 를 여기서 호출한다.
AXEXAM_DIR = _env_path("XAM_AXEXAM", os.path.join(BASE_DIR, "_ref", "axexam"))

# ── 품목 ────────────────────────────────────────────────────────────────────
# ★ build_check.py 의 --pd 기본값은 'sqld' 다. 우리가 이 값을 반드시 명시해야
#   라이브 SQLD 문제은행을 덮어쓰는 사고를 막는다. §7 참고.
PD_CODE = (os.getenv("XAM_PD") or "bigdata").strip()
PD_LABEL = (os.getenv("XAM_PD_LABEL") or "빅데이터분석기사 필기").strip()

SITE_BASE = (os.getenv("XAM_SITE") or "https://axexam.mycafe24.com").rstrip("/")
SITE_PATH = "/" + (os.getenv("XAM_SITE_PATH") or "exam").strip("/") + "/"

PORT = int(os.getenv("XAM_PORT") or "8870")

# ── 책의 형태 (사전점검 기대값) ──────────────────────────────────────────────
ROUND_CODES = ("m01", "m02", "m03")
QUESTIONS_PER_ROUND = 80
QUESTIONS_PER_BUNDLE = 10
BUNDLES_PER_ROUND = QUESTIONS_PER_ROUND // QUESTIONS_PER_BUNDLE   # 8
TOTAL_QUESTIONS = len(ROUND_CODES) * QUESTIONS_PER_ROUND          # 240
TOTAL_BUNDLES = len(ROUND_CODES) * BUNDLES_PER_ROUND              # 24
SUBJECT_COUNT = 4

# 요약노트 4과목 — 03/summary_{key}.html
SUMMARY_KEYS = ("분석기획", "탐색", "모델링", "결과해석")

# 잡 이력 보관 개수 / 로그 링버퍼 줄수
JOB_HISTORY = int(os.getenv("XAM_JOB_HISTORY") or "200")
LOG_TAIL = int(os.getenv("XAM_LOG_TAIL") or "400")

ANSWER_GLYPHS = "①②③④⑤"
KOR_NUM = {0: "일", 1: "이", 2: "삼", 3: "사", 4: "오"}
DIFFICULTIES = ("상", "중", "하")
