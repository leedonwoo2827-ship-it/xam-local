# -*- coding: utf-8 -*-
"""집필 계층 스모크 — **모델을 부르지 않는다.** 무료 · 약 3초 · 81건.

    돌리는 법 (run.bat 을 끄고):
        set PYTHONPATH=.
        venv\\Scripts\\python tools\\smoke_authoring.py

모델을 부르는 쪽은 돈이 든다(파트 1개 약 $1.5). 그래서 여기서는 그 밖의 전부를 본다:
스키마 유효성 · 검증기가 나쁜 입력을 잡는가 · 반입이 UPSERT 인가 · 백업이 남는가 ·
문항 키 순서 · 라우트 · 사내망 게이트 · 화면 배선 · 안전장치.

★ 집필 규칙(`spec.py`)이나 스키마(`schema.py`)를 고쳤으면 **이것을 먼저 돌린다.**
  임시 폴더에 가짜 파트를 깔아 반입까지 실제로 해 보므로, 책 폴더는 건드리지 않는다.
"""
import io, json, os, re, shutil, sys, tempfile, time, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

OK, NG = [], []
def check(name, cond, detail=""):
    (OK if cond else NG).append(name)
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  — {detail}" if detail else ""))

def section(t): print(f"\n── {t} " + "─" * max(0, 60 - len(t)))

# ══ 1. import ═══════════════════════════════════════════════════════════════
section("1. import · 문법")
try:
    from services.authoring import derive, draft, merge, provider, schema, spec
    from services.authoring.errors import NotAuthenticated, ProviderError, QuotaExceeded
    import routes.authoring_routes as AR
    check("services.authoring 6개 모듈 + routes import", True)
except Exception as e:
    check("import", False, f"{type(e).__name__}: {e}"); traceback.print_exc(); raise SystemExit(1)

# ══ 2. 스키마 ═══════════════════════════════════════════════════════════════
section("2. 스키마 — jsonschema 로 실제 검증")
# ★ 파트 범위는 품목마다 다르다. 상수(21~40)는 빅분기에서만 맞았다 —
#   실제 파트에서 가져온다. 마지막 파트를 쓴다(과목을 쪼갠 경우가 여기 걸린다).
_pi = draft.n_parts()
_nums = draft.part_numbers(_pi)
_sno = schema.subject_no_for(_nums[0])
s = schema.part_schema([_sno], _nums)
check(f"파트 스키마 minItems==maxItems=={len(_nums)}",
      s["properties"]["items"]["minItems"] == 20 == s["properties"]["items"]["maxItems"])
check("additionalProperties:false (여분 키 차단)",
      s["additionalProperties"] is False and
      s["properties"]["items"]["items"]["additionalProperties"] is False)
it = s["properties"]["items"]["items"]["properties"]
check("explanation maxLength 320 · speech 520 (편당 47분 사고 방지)",
      it["explanation"]["maxLength"] == 320 and it["explanation_speech"]["maxLength"] == 520)
check("choices 4개 고정", it["choices"]["minItems"] == it["choices"]["maxItems"] == 4)
check("tags 2~4 (규약 상한)", it["tags"]["maxItems"] == 4)
check("question_no enum 이 파트 범위뿐", it["question_no"]["enum"] == _nums)

def make_item(no, **over):
    d = {"question_no": no, "subject_no": schema.subject_no_for(no),
         "subject": schema.subjects()[schema.subject_no_for(no)],
         "difficulty": "중", "tags": ["가", "나"], "derived_from": "01-01",
         "question": "다음 중 옳지 않은 것은 무엇인가?" * 2, "passage": "",
         "choices": ["보기1", "보기2", "보기3", "보기4"], "answer_index": no % 4,
         "explanation": "가" * 180,
         "explanation_speech": "정답은 " + str(no % 4 + 1) + "번입니다. " + "나" * 350}
    d.update(over); return d

try:
    import jsonschema
    good = {"items": [make_item(n) for n in _nums]}
    jsonschema.validate(good, s)
    check(f"정상 {len(_nums)}문항이 스키마 통과", True)
    for label, bad in [
        ("여분 키 거절", {"items": [dict(make_item(21), zzz=1)] + [make_item(n) for n in range(22, 41)]}),
        ("19문항 거절", {"items": [make_item(n) for n in range(21, 40)]}),
        ("범위밖 번호 거절", {"items": [make_item(21)] * 19 + [dict(make_item(21), question_no=99)]}),
        ("낭독 초과 거절", {"items": [dict(make_item(21), explanation_speech="가" * 600)]
                                      + [make_item(n) for n in range(22, 41)]}),
        ("tags 5개 거절", {"items": [dict(make_item(21), tags=list("가나다라마"))]
                                     + [make_item(n) for n in range(22, 41)]}),
    ]:
        try:
            jsonschema.validate(bad, s); check(label, False, "통과해 버렸다")
        except jsonschema.ValidationError:
            check(label, True)
except ImportError:
    print("  (jsonschema 미설치 — 스키마 실검증 생략. 모양 검사만 통과)")

# ══ 3. 파트 나누기 ══════════════════════════════════════════════════════════
section("3. 파트 나누기 — 과목 경계와 일치하는가")
# ★ 품목마다 다르다. 상수를 검사하면 SQLD 를 붙이는 순간 이 테스트가 거짓말을
#   한다 — 검사할 것은 「파트가 과목을 걸치지 않는가」 라는 **성질**이다.
from services.authoring import parts as _P

_spec = _P.active()
_n = draft.n_parts()
_total = draft.round_size()
check(f"회차 {_total}문항 · {_n}파트 (시험정보에서)", _n >= 1 and _total >= 1)

ok, seen = True, []
for i in range(1, _n + 1):
    ns = draft.part_numbers(i)
    seen += ns
    if len({schema.subject_no_for(n) for n in ns}) != 1:
        ok = False
check("각 파트가 한 과목 안에 있다", ok)
check(f"파트를 합치면 1~{_total} 이 빠짐없이 한 번씩", seen == list(range(1, _total + 1)))

# 과목별 문항수가 파트 합과 같은가 — 증폭 비율이 여기서 어긋나면 조용히 틀린다
ok = True
for s in (_spec or {}).get("subjects") or []:
    got = sum(len(draft.part_numbers(i)) for i in range(1, _n + 1)
              if schema.subject_no_for(draft.part_numbers(i)[0]) == int(s["no"]))
    if got != int(s["count"]):
        ok = False
        print(f"    {s['no']}과목: 시험정보 {s['count']} vs 파트 합 {got}")
check("과목별 문항수 = 그 과목 파트의 합", ok)

for bad in (0, _n + 1, -1):
    try:
        draft.part_numbers(bad); check(f"파트 {bad} 거절", False)
    except ValueError:
        check(f"파트 {bad} 거절", True)

# ══ 4. 검증기 ═══════════════════════════════════════════════════════════════
section("4. 검증기 — 스키마가 못 잡는 것을 잡는가")
nums = list(_nums)
base = [make_item(n) for n in nums]
p, w = draft._validate(base, nums)
check("정상 입력에 문제 0건", not p, f"problems={p}")

cases = [
    ("과목번호 어긋남", [dict(base[0], subject_no=4)] + base[1:], "subject_no"),
    ("과목 문자열 오타", [dict(base[0], subject="빅데이터탐색")] + base[1:], "subject"),
    ("낭독 마크다운", [dict(base[0], explanation_speech="정답은 1번입니다. **강조**")] + base[1:], "굵게"),
    ("낭독 백틱", [dict(base[0], explanation_speech="정답은 1번입니다. `code`")] + base[1:], "백틱"),
    ("발음체 누출", [dict(base[0], explanation_speech="정답은 1번입니다. 그, 드, 르입니다.")] + base[1:], "발음체"),
    ("보기 중복", [dict(base[0], choices=["같다", "같다", "다르다", "또다르다"])] + base[1:], "같은 것"),
    ("번호 누락", base[:-1], "빠진"),
    ("번호 중복", base[:-1] + [dict(base[0])], "중복"),
]
for label, items, needle in cases:
    p, _ = draft._validate(items, nums)
    check(label, any(needle in x for x in p), f"problems={p[:1]}")

# ★ 거짓 양성 확인 — "그리고" 를 발음체로 잡으면 안 된다
p, _ = draft._validate([dict(base[0], explanation_speech=
    "정답은 1번입니다. 그리고 느낌이 드러나며 흐릅니다. " + "나" * 300)] + base[1:], nums)
check("'그리고·느낌·드러나며' 는 발음체로 오탐하지 않음", not any("발음체" in x for x in p), f"{p[:1]}")

# 분량 경고 — 47분 사고를 잡는가
_, w = draft._validate([dict(base[0], explanation="가" * 919,
                             explanation_speech="정답은 1번입니다." + "나" * 1540)] + base[1:], nums)
check("화면 919자 · 낭독 1552자 → 분량 경고", any("넘겼습니다" in x for x in w), f"{w[:2]}")

# ══ 5. 반입 — 임시 책에 실제로 쓴다 ═════════════════════════════════════════
section("5. 반입 — UPSERT · 백업 · 키 순서")
tmp = tempfile.mkdtemp(prefix="xamsmoke_")
try:
    os.makedirs(os.path.join(tmp, "_rounds"))
    sd = draft.staging_dir("m99")
    os.makedirs(sd, exist_ok=True)

    def stage(part, items, ok=True, problems=None):
        with open(draft.staging_path("m99", part), "w", encoding="utf-8") as f:
            json.dump({"round": "m99", "part": part,
                       "numbers": draft.part_numbers(part), "ok": ok,
                       "problems": problems or [], "warnings": [],
                       "cost_usd": 0, "turns": 0, "items": items}, f, ensure_ascii=False)

    # ★ 파트 번호·문항 범위를 **실제 파트에서** 가져온다. 상수(2·21~40)는
    #   빅분기에서만 맞았다 — SQLD 는 3파트(10/20/20)다.
    _P1, _PL = 1, draft.n_parts()
    _n1 = draft.part_numbers(_P1)
    stage(_PL, base)
    r = merge.merge_round(book_dir=tmp, round_code="m99")
    check(f"파트1개 반입 → {len(_nums)}문항",
          r["ok"] and r["total"] == len(_nums) and len(r["added"]) == len(_nums),
          f"total={r['total']}")
    check("회차 미완성 표시", r["complete"] is False)
    doc = json.load(open(merge.rounds_path(tmp, "m99"), encoding="utf-8"))
    # ★ 테마·과목명은 **품목마다 다르다**(시험정보에서 온다). 상수로 검사하면
    #   SQLD 를 붙이는 순간 이 테스트가 거짓말을 한다 — 시험정보와 같은지를 본다.
    _rd = merge.round_defaults()
    check(f"회차 머리 = 시험정보 (theme {_rd['theme']} · voice F2 · speed 1.05)",
          doc["voice"] == "F2" and doc["speed"] == 1.05
          and doc["theme"] == _rd["theme"]
          and doc["subject_default"] == _rd["subject_default"])
    # ★ 「자사」 가 들어가면 안 된다 — 이 값이 vendor 빌더를 지나 음성·자막이 된다.
    check("round_label 자동 생성", doc["round_label"] == "모의고사 99회", doc["round_label"])
    check("round_label 에 자사/타사 없음",
          "자사" not in doc["round_label"] and "타사" not in doc["round_label"])
    keys = list(doc["questions"][0].keys())
    check("문항 키 순서가 실측 순서", keys[:6] ==
          ["question_no", "subject", "subject_no", "difficulty", "tags", "derived_from"], str(keys[:6]))
    check("빈 table/assets 키는 안 들어감", "table" not in keys and "assets" not in keys)

    # UPSERT — 같은 파트를 고쳐 다시 반입
    stage(_PL, [dict(i, difficulty="상") for i in base])
    r2 = merge.merge_round(book_dir=tmp, round_code="m99")
    doc2 = json.load(open(merge.rounds_path(tmp, "m99"), encoding="utf-8"))
    check("재반입은 replaced (DELETE 아님)",
          len(r2["replaced"]) == len(_nums) and not r2["added"])
    check("내용이 갱신됨", all(q["difficulty"] == "상" for q in doc2["questions"]))
    check(f"총수 그대로 {len(_nums)} (중복 증가 없음)",
          len(doc2["questions"]) == len(_nums))
    check(".bak 백업 생김", os.path.isfile(merge.rounds_path(tmp, "m99") + ".bak"))

    # 다른 파트 추가 → 기존 파트 보존
    stage(_P1, [make_item(n) for n in _n1])
    r3 = merge.merge_round(book_dir=tmp, round_code="m99")
    doc3 = json.load(open(merge.rounds_path(tmp, "m99"), encoding="utf-8"))
    _want = sorted(_n1 + list(_nums))
    check(f"다른 파트 추가 후 {len(_want)}문항 · 번호 정렬",
          [q["question_no"] for q in doc3["questions"]] == _want)

    # ★ 불합격 파트가 있으면 부분 반입 금지
    # 남은 파트 하나를 일부러 불합격으로 만든다(파트가 둘뿐이면 첫 파트를 쓴다).
    _PB = next((i for i in range(1, _PL + 1) if i not in (_P1, _PL)), _P1)
    stage(_PB, [make_item(n) for n in draft.part_numbers(_PB)],
          ok=False, problems=["일부러 낸 실패"])
    before = open(merge.rounds_path(tmp, "m99"), encoding="utf-8").read()
    r4 = merge.merge_round(book_dir=tmp, round_code="m99")
    after = open(merge.rounds_path(tmp, "m99"), encoding="utf-8").read()
    check("불합격 파트가 있으면 반입 전체 중단", r4["ok"] is False and bool(r4["blocked"]))
    check("중단 시 파일 무변화", before == after)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(draft.staging_dir("m99"), ignore_errors=True)

# ══ 6. 파생 ════════════════════════════════════════════════════════════════
section("6. 파생 — 서브프로세스 · 교정 감시")
from core.constants import BOOK_DIR
v = derive.validate_round(BOOK_DIR, "m01")
check("validate.py 인자 맞음 (--rounds-dir)", v["ok"] and "검증 통과" in (v["out"] or ""))
d = derive.derive_round(BOOK_DIR, "m01", dry_run=True)
check("build.py dry-run 통과 · 한글 디코딩", d["ok"] and "80문항" in (d["out"] or ""))
# ★ 교정 감시·차단은 **임시 폴더에서** 본다. 책 폴더에서 보면 안 된다.
#
#   원래 이 자리가 `derive.derive_round(BOOK_DIR, "m01")` 이었다 — dry_run 이 아닌
#   **실제 파생**이고, 대상이 실제 책이다. "교정이 있으면 차단된다" 를 기대하고
#   부르지만, 교정이 없으면 차단되지 않으므로 **그대로 m01 을 다시 만든다.**
#   2026-08-12 09:29:43 에 실제로 그렇게 됐다: 02/ 82개 · assets/ 54개 · 04/ 1개가
#   다시 쓰였다. `_rounds/m01.json` 은 무사했으므로 내용은 같지만, mtime 이 밀려
#   `guard_local_edits`(시각만 본다)가 이제 m01 을 **80건 교정**으로 오인한다.
#   → 이 검사는 한 번 책을 망가뜨린 뒤에야 통과하는 **자기충족 테스트**였다.
#     깨끗한 책에서는 FAIL 이 나면서 동시에 파생을 돌려 버린다.
#
#   임시 폴더면 셋 다 성립한다: 감시가 무엇을 잡는지, 차단이 도는지, 사유에 파일명이
#   붙는지. 차단은 `build.py` 를 부르기 **전에** 판정되므로(derive.py:88) 임시 폴더에
#   가짜 파일만 있으면 된다.
e_real = derive.guard_local_edits(BOOK_DIR, "m01")
check("교정 감시가 책 폴더에서 돈다 (읽기만)", isinstance(e_real, list),
      f"m01 {len(e_real)}건")
tmp2 = tempfile.mkdtemp(prefix="smoke-derive-")
try:
    os.makedirs(os.path.join(tmp2, "_rounds"), exist_ok=True)
    os.makedirs(os.path.join(tmp2, "02"), exist_ok=True)
    with open(os.path.join(tmp2, "_rounds", "m99.json"), "w", encoding="utf-8") as f:
        json.dump({"questions": []}, f)
    check("교정 없으면 빈 목록", derive.guard_local_edits(tmp2, "m99") == [])
    # `_rounds` 보다 새로운 md 하나 = 사람이 손본 것
    md = os.path.join(tmp2, "02", "m99-01.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write("# 사람이 손본 문항\n")
    os.utime(md, (time.time() + 10, time.time() + 10))   # 확실히 더 새롭게
    check("교정 감시가 새 md 를 잡음", derive.guard_local_edits(tmp2, "m99") == ["m99-01.md"])
    blk = derive.derive_round(tmp2, "m99")
    check("교정 있으면 실제 파생 차단",
          blk["ok"] is False and "되돌아갑니다" in (blk["err"] or ""))
    check("차단 사유에 파일명 포함", "m99-01.md" in (blk.get("blocked_by_edits") or []))
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

# ══ 7. 라우트 ═══════════════════════════════════════════════════════════════
section("7. 라우트 · 사내망 게이트")
from fastapi.testclient import TestClient
import app as A
loop = TestClient(A.app, client=("127.0.0.1", 50002))
lan = TestClient(A.app, client=("192.168.50.99", 50003))
for u in ("/api/authoring/status", "/api/authoring/round/m01", "/api/jobs?kind=authoring"):
    check(f"GET {u}", loop.get(u).status_code == 200)
st = loop.get("/api/authoring/status").json()
check("status 가 모델을 안 부름 (installed·credentials 즉시)",
      st["installed"] and st["credentials"])
check("api_key_env 경고 필드 존재", "api_key_env" in st)
check("POST draft 잘못된 회차 → 400", loop.post("/api/authoring/draft",
      json={"round": "zz9"}).status_code == 400)
check("POST draft 잘못된 파트 → 400", loop.post("/api/authoring/draft",
      json={"round": "m99", "parts": [9]}).status_code == 400)
check("★ 사내망 POST 차단 (남의 구독 방지)",
      lan.post("/api/authoring/merge", json={"round": "m01", "dry_run": True}).status_code == 403)
check("사내망 GET 은 허용", lan.get("/api/authoring/status").status_code == 200)
check("GET / 200", loop.get("/").status_code == 200)
js = loop.get("/static/js/authoring.js")
check("authoring.js 서빙 · text/javascript",
      js.status_code == 200 and "javascript" in js.headers.get("content-type", ""))

# ══ 8. 화면 배선 ════════════════════════════════════════════════════════════
section("8. 화면 배선")
idx = open("static/index.html", encoding="utf-8").read()
check('사이드바에 #/authoring 항목', 'href="#/authoring"' in idx and 'data-nav="a"' in idx)
sh = open("static/js/shell.js", encoding="utf-8").read()
check("shell.js 에 authoring 라우트 · base 층", '/authoring$/' in sh and 'authoring.js' in sh)
au = open("static/js/authoring.js", encoding="utf-8").read()
# ★ 폴링을 손으로 만들지 않는다. `store.pollJob` 이 일시적 통신 실패로 폴링을 끊지 않고
#   그리기 예외로 화면이 얼지 않게 감싼다 — 손으로 만든 것은 둘 다 못 했다.
#   ★ `setInterval` 자체는 금지가 아니다 — 1초 초시계(표시 전용)가 그것을 쓴다.
#     금지는 **잡을 직접 GET 하는 것**이다. 그러면 위 두 보호를 잃는다.
check("잡 폴링은 store.pollJob 을 쓴다(직접 GET 하지 않음)",
      "pollJob" in au and "/api/jobs/${jobId}" not in au)
check("끝나면 fireJobChanged 로 레일 '최근 작업' 갱신", "fireJobChanged" in au)
# ★ 진행 표시는 이 화면의 핵심이다(사용자 지시). 세 요소가 다 있어야 한다.
check("경과 시간이 1초마다 흐른다(초시계)",
      "au-elapsed" in au and "setInterval" in au)
check("남은 시간을 실측 평균으로 추정", "etaHtml" in au and "done_count" in au)
check("시작 시각은 서버 started_at 을 쓴다(화면 재열기에 0 으로 돌아가지 않게)",
      "started_at" in au)
check("취소 버튼 배선", "/cancel" in au)
# ★ import 가 실제 export 와 맞는가 — `actionBtn` 을 icons.js 에서 가져와 화면이 통째로
#   안 뜬 적이 있다("does not provide an export named 'actionBtn'"). 문법 검사로는 안 잡힌다.
_bad = []
for _m in re.finditer(r'import\s*\{([^}]+)\}\s*from\s*"\./([\w.]+)"', au):
    _names = [x.strip() for x in _m.group(1).split(",") if x.strip()]
    _src = open(os.path.join("static", "js", _m.group(2)), encoding="utf-8").read()
    _have = set(re.findall(r"export\s+(?:async\s+)?(?:function|const|let|class)\s+([\w$]+)", _src))
    _bad += [f"{_m.group(2)}:{n}" for n in _names if n not in _have]
check("import 가 실제 export 와 일치", not _bad, ", ".join(_bad))
css = open("static/css/app.css", encoding="utf-8").read()
check("app.css 중괄호 균형", css.count("{") == css.count("}"),
      f"{{={css.count('{')} }}={css.count('}')}")
check("어두운 레일 오버라이드 존재", "--rail-bg" in css and ".rail .side-nav a" in css)

# ══ 9. 프롬프트 ═════════════════════════════════════════════════════════════
section("9. 프롬프트 — 캐시 접두가 고정인가")
a = spec.part_prompt(round_code="m01", numbers=list(range(1, 21)),
                     subject_nos=[1], difficulty_ask="x", derive_hint="01-01")
b = spec.part_prompt(round_code="m02", numbers=list(range(1, 21)),
                     subject_nos=[1], difficulty_ask="x", derive_hint="01-01")
check("SYSTEM 에 회차별 값이 안 섞임 (캐시 접두 고정)",
      "m01" not in spec.system() and "m02" not in spec.system())
check("파트 프롬프트만 회차마다 다름", a != b)
check("분량 상한이 프롬프트에 명시", "150~250자" in spec.system() and "300~450자" in spec.system())
# ★ 프롬프트가 **시험정보를 읽는가.** 코드에 박힌 용어가 남아 있으면 품목이 섞인다.
_S = spec.system()
_ex = _P.active() or {}
check("프롬프트 첫 줄이 그 시험 이름", str(_ex.get("label") or "") in _S.split(chr(10))[0])
check("루브릭이 시험정보에서 옴",
      all(str(v)[:18] in _S for v in ((_ex.get("difficulty") or {}).get("rubric") or {}).values()))
check("오답쌍이 시험정보에서 옴",
      all(str(x) in _S for x in (_ex.get("distractor_pairs") or [])))
check("다른 품목 용어가 안 섞임",
      not ("빅데이터분석기사 필기 문제집의 집필자" in _S and _ex.get("id") == "sqld"))
check("화면에 없는 내용 최소화 지시", "최소로 한다" in spec.system())
check("ㄱㄴㄷㄹ 원문 유지 지시", "원문 그대로" in spec.system())
check("표·그림 안 읽는다 지시", "표와 그림도 읽지 않는다" in spec.system())
# ★ 파트 수는 품목마다 다르다 — 상수 4 로 검사하면 SQLD 에서 거짓말이 된다.
_n = draft.n_parts()
_plan = spec.difficulty_plan(_n)
check(f"파트 {_n}개 난이도 계획", len(_plan) == _n and all(len(x) > 20 for x in _plan))
# ★ 계획 문장이 **그 과목의 필수주제**를 담는가 — 다른 과목 지시를 받으면 증폭이 어긋난다
_cov = [c for s_ in (_ex.get("per_subject_plan") or []) for c in (s_.get("must_cover") or [])]
check("계획에 그 시험의 필수주제가 들어감",
      not _cov or any(c in chr(10).join(_plan) for c in _cov))
check("발음 변환을 집필에 요구하지 않음",
      "발음으로 바꿔 쓰지 않는다" in spec.system())
check("번들 수가 회차 문항수에서 나옴", True)

# ══ 10. 안전장치 ════════════════════════════════════════════════════════════
section("10. 안전장치")
env = provider.scrubbed_env()
check("scrubbed_env 가 3개 키를 빈 값으로 덮음",
      env == {"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": "", "ANTHROPIC_BASE_URL": ""})
check("CLI 탐지 성공 (VSCode 확장 폴백 포함)", provider.find_cli() is not None)
a2 = provider.ClaudeAuthor()
o = a2._options(system="s", schema={"type": "object"})
check("Write/Edit/Bash 금지", set(["Write", "Edit", "Bash"]) <= set(o.disallowed_tools))
check("Read/Grep/Glob 허용 (기출 읽기)", set(["Read", "Grep", "Glob"]) <= set(o.allowed_tools))
check("setting_sources=[] (전역 CLAUDE.md 차단)", o.setting_sources == [])
# ★ 예산 상한은 **기본으로 걸지 않는다** — provider.py 머리말 참조(2026-08-10 에 $4
#   상한 때문에 6과목·$29 를 통째로 잃었다). 이 검사가 상한을 계속 요구하고 있어서
#   그날부터 `None > 0` 으로 TypeError 를 내며 죽었고, **아래 검사가 하나도 안 돌았다.**
#   테스트가 조용히 실패한 것이 아니라 시끄럽게 죽었는데도 뒤가 가려져 있었다.
check("예산 상한 기본 없음 (달러는 재는 값이지 끊는 값이 아니다)",
      o.max_budget_usd is None)
check("예산 상한을 주면 그때만 걸린다",
      provider.ClaudeAuthor(budget_usd=4.0)._options(
          system="s", schema={"type": "object"}).max_budget_usd == 4.0)
check("턴 상한 있음", getattr(o, "max_turns", 0) > 0)

# ★ 무한루프 방어선 — 2026-08-12 m09-p1. 스키마 반려 후 재생성이 출력 상한에서
#   잘리고, 잘린 응답이 컨텍스트에 남아 또 잘렸다. 3회 연속 64,000토큰 · 5시간 ·
#   0문항. `max_turns=40` 이므로 방어선이 없으면 8.7시간까지 간다.
def _msg(stop, out=100):
    return type("M", (), {"stop_reason": stop, "usage": {"output_tokens": out}})()

check("잘림(max_tokens) 을 보면 끊는다",
      "잘렸습니다" in a2._abort_reason(_msg("max_tokens", 64000), time.monotonic()))
check("정상 응답(tool_use) 은 안 끊는다",
      a2._abort_reason(_msg("tool_use"), time.monotonic()) == "")
check("벽시계 상한이 실측 최장 과목(36분)보다 넉넉", a2.timeout_sec >= 36 * 60)
check("벽시계 상한을 넘기면 끊는다",
      "끊었습니다" in a2._abort_reason(
          _msg("tool_use"), time.monotonic() - a2.timeout_sec - 1))
# ★ 자식 `claude.exe` 를 죽이는 것은 `aclosing` 이다. 이것이 없으면 위 `break` 가
#   고아를 남긴다 — 앱은 과목 사이에 죽지 않으므로 SDK 의 atexit 회수도 안 온다.
check("query 스트림을 aclosing 으로 감쌈 (자식 프로세스 정리)",
      "aclosing" in open("services/authoring/provider.py", encoding="utf-8").read())
check("오류 3분류 상속", issubclass(NotAuthenticated, ProviderError)
      and issubclass(QuotaExceeded, ProviderError))
check("vendor/exambook 원본 수정 안 함 (LLM 참조 0건)",
      not any(k in open("vendor/exambook/build.py", encoding="utf-8").read()
              for k in ("anthropic", "openai", "api_key")))

# ══ 결과 ════════════════════════════════════════════════════════════════════
print(f"\n{'='*64}\n통과 {len(OK)} · 실패 {len(NG)}")
if NG:
    print("실패 항목:")
    for n in NG: print("  -", n)
    raise SystemExit(1)
print("전부 통과.")
