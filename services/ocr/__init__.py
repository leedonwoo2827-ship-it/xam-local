"""도구 #1 — 스캔 PDF → 페이지 초안 → `01/*.md` 확정.

원본은 `d:\\00work\\260730-ocr`(빅분기) · `d:\\00work\\260723-ocr`(SQLD) 다.
그 프로젝트의 `app/qmodel.py` · `app/server.py` · `scripts/*.py` 를 이 패키지로
들여왔다. **재현이 아니라 이식이다** — 업로드본의 `services/book/scan.py` 는 #1 의
출력 형식을 추측해 근사했고(보기 줄 간격을 '지문 유무' 로 갈랐는데 실제 기준은
'자산 유무' 였다), 그래서 여기서는 원본 코드를 기준으로 삼는다.

  project.py    작업 폴더 해석 · 소스(PDF) 목록 · 페이지 목록 · 시험 설정
  draft.py      data/ocr_draft/<src>_pNNN.json 읽기·쓰기 (원자적 + .bak)
  finalize.py   초안 → 01/{RR}-{NN}.md 바이트 충실 쓰기 + 그림 크롭
  pdfrender.py  00/*.pdf → data/raw_pages/<stem>/page_NNN.png
  answers.py    분리형 교재의 정답·해설 주입 (merge_answers)
  checks.py     회차 정합성 검증 + 확정 게이트(--refinalize-dry)

★ 판독(OCR) 자체는 이 앱이 하지 않는다. Claude Code 창이 `raw_pages/*.png` 를 읽어
  `ocr_draft/*.json` 을 쓰고, 이 앱은 그 초안을 검수해 `01/` 로 확정한다.
  그래서 LLM·API 키·OCR 엔진 의존성이 없다.
"""
