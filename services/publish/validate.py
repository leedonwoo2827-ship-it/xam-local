"""발행 사전점검 — 실측 기반 규칙.

error 는 우회 불가, warn 만 force_ignore_warnings 로 통과시킨다.

이 점검은 읽기 전용이고 그 자체로 유용하다. 그래서 발행 화면에서 가장 먼저 만들고
가장 위에 둔다 — 무엇이 아직 준비되지 않았는지가 한 화면에서 보여야 한다.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET

from core.constants import (
    AXEXAM_DIR, BUNDLES_PER_ROUND, PD_CODE, QUESTIONS_PER_ROUND,
    SUBJECT_COUNT, SUMMARY_KEYS,
)
from services.book import index as bindex, lesson, md, paths, rounds, verify
from services.render import bundles as rbundles

# pd 코드 검증 — _boot.php / exam_lib/problem.php 의 정규식과 같아야 한다.
import re
_PD_RE = re.compile(r"^[a-z0-9\-]{1,20}$")
# pr_key 검증 — ex_valid_key() / ex_valid_pr_key() 의 정규식. 어긋나면 채점이
# 조용히 0점이 된다(오류가 아니라 무응답 처리).
_PR_KEY_RE = re.compile(r"^m\d{2}-\d{1,2}#\d{1,3}$")


def _want_bundles() -> int:
    """이 폴더가 내야 하는 번들 수 — 회차 수를 폴더에서 읽는다.

    ★ 상수 24 로 고정하면 21회차 SQLD 나 1회차만 들어온 신규 책에서 항상 실패한다.
    """
    return len(paths.all_bundles())


def _chk(gid: str, cid: str, level: str, label: str, ok: bool, detail: str = "") -> dict:
    return {"group": gid, "id": cid, "level": level, "label": label,
            "ok": bool(ok), "detail": detail}


def check_questions() -> list[dict]:
    out: list[dict] = []
    items = bindex.cached_items()
    docs = rounds.load_all()

    # 회차별 80문항 · 결번 없음
    for rc in paths.round_codes():
        doc = docs.get(rc)
        if not doc:
            out.append(_chk("questions", f"q.round.{rc}", "error",
                            f"{rc} 회차 파일 존재", False,
                            f"_rounds/{rc}.json 이 없습니다."))
            continue
        qs = doc.get("questions") or []
        nos = [int(q.get("question_no", 0)) for q in qs]
        out.append(_chk("questions", f"q.count.{rc}", "error",
                        f"{rc} 문항 {QUESTIONS_PER_ROUND}개", len(qs) == QUESTIONS_PER_ROUND,
                        f"현재 {len(qs)}개"))
        out.append(_chk("questions", f"q.gaps.{rc}", "error",
                        f"{rc} 번호 1~{QUESTIONS_PER_ROUND} 결번·중복 없음",
                        sorted(nos) == list(range(1, QUESTIONS_PER_ROUND + 1)),
                        f"중복/결번: {len(nos) - len(set(nos))}개 중복"))

    # 보기 4개 · 정답 범위 · subject_no 정수
    bad_choices = [i["id"] for i in items if i["n_choices"] != 4]
    out.append(_chk("questions", "q.choices_4", "error", "모든 문항 보기 4개",
                    not bad_choices, ", ".join(bad_choices[:10])))

    bad_ans = [i["id"] for i in items
               if not isinstance(i["answer_index"], int)
               or not 0 <= i["answer_index"] < i["n_choices"]]
    out.append(_chk("questions", "q.answer_range", "error", "정답 번호 범위 정상",
                    not bad_ans, ", ".join(bad_ans[:10])))

    bad_subj = [i["id"] for i in items
                if not isinstance(i["subject_no"], int) or i["subject_no"] < 1]
    out.append(_chk("questions", "q.subject_no_int", "error",
                    "subject_no 가 1 이상의 정수",
                    not bad_subj,
                    (", ".join(bad_subj[:10]) + " — 문자열이면 웹의 과목 필터가 "
                     "통째로 깨집니다(build_check 의 과목 N종 리포트는 이걸 못 잡습니다).")
                    if bad_subj else ""))

    subjects = sorted({(i["subject_no"], i["subject"]) for i in items})
    out.append(_chk("questions", "q.subject_count", "error",
                    f"과목 {SUBJECT_COUNT}종", len(subjects) == SUBJECT_COUNT,
                    " / ".join(f"{n}:{s}" for n, s in subjects)))

    # ★ 미검수 0개 — 이게 화면①의 존재 이유다
    unrev = [i["id"] for i in items if not i["reviewed"]]
    out.append(_chk("questions", "q.needs_review", "error", "미검수 문항 없음",
                    not unrev,
                    f"{len(unrev)}문항이 아직 미검수입니다 (예: {', '.join(unrev[:5])})"
                    if unrev else ""))

    # 그림 파일
    miss_svg = []
    for i in items:
        if not i["has_figure"]:
            continue
        rc = paths.round_code(i["round"])
        q = rounds.question_of(docs.get(rc) or {}, i["question_no"])
        for name in ((q and [a.get("name") for a in (q.get("assets") or [])]) or []):
            name = (name or "").removesuffix(".svg")
            p = paths.q_svg(name)
            if not name or paths.size(p) == 0:
                miss_svg.append(f"{i['id']}:{name}")
    out.append(_chk("questions", "q.figure_svg", "error", "그림 SVG 전부 존재",
                    not miss_svg, ", ".join(miss_svg[:10])))

    # 바이트 충실도 — 02/md 와 05/lesson 이 _rounds 와 일치하는가
    v = verify.run_all()
    md_g, idx_g, les_g, ast_g = v["groups"]
    out.append(_chk("questions", "q.md_sync", "error", "02/*.md 가 _rounds 와 일치",
                    md_g["fail_count"] == 0 and md_g["missing_count"] == 0,
                    f"불일치 {md_g['fail_count']}건 · 없음 {md_g['missing_count']}건"))
    out.append(_chk("questions", "q.lesson_sync", "error",
                    "05/lesson 이 _rounds 와 일치 (본문이 웹에 가는 경로)",
                    les_g["fail_count"] == 0 and les_g["missing_count"] == 0,
                    f"불일치 {les_g['fail_count']}건 · 없음 {les_g['missing_count']}건"))
    out.append(_chk("questions", "q.index_sync", "error",
                    "02/_index.json · difficulty_stats.json 최신",
                    idx_g["ok"] == idx_g["total"],
                    "재색인 버튼으로 고칠 수 있습니다."))

    # ── warn ──
    for rc in paths.round_codes():
        rows = [i for i in items if paths.round_code(i["round"]) == rc]
        if not rows:
            continue
        dist = {}
        for r in rows:
            dist[r["answer"]] = dist.get(r["answer"], 0) + 1
        want = QUESTIONS_PER_ROUND // 4
        ok = all(abs(dist.get(g, 0) - want) <= 2 for g in "①②③④")
        out.append(_chk("questions", f"q.answer_balance.{rc}", "warn",
                        f"{rc} 정답 분포 각 {want}±2", ok,
                        " ".join(f"{g}{dist.get(g, 0)}" for g in "①②③④")))
        ddist = {}
        for r in rows:
            ddist[r["difficulty"]] = ddist.get(r["difficulty"], 0) + 1
        ok_d = (abs(ddist.get("상", 0) - 24) <= 4 and abs(ddist.get("중", 0) - 44) <= 6
                and abs(ddist.get("하", 0) - 12) <= 4)
        out.append(_chk("questions", f"q.difficulty_mix.{rc}", "warn",
                        f"{rc} 난이도 상24±4·중44±6·하12±4", ok_d,
                        " ".join(f"{k}{v}" for k, v in ddist.items())))

    # 고아 SVG
    used = set()
    for rc, meta, q in rounds.all_questions():
        for a in q.get("assets") or []:
            n = (a.get("name") if isinstance(a, dict) else str(a)) or ""
            used.add((n if n.endswith(".svg") else n + ".svg"))
    orphan = []
    adir = paths.q_assets_dir()
    if os.path.isdir(adir):
        orphan = [f for f in sorted(os.listdir(adir))
                  if f.endswith(".svg") and f not in used]
    out.append(_chk("questions", "q.orphan_svg", "warn", "쓰이지 않는 SVG 없음",
                    not orphan, ", ".join(orphan[:10])))

    # SVG 파싱
    bad_svg = []
    if os.path.isdir(adir):
        for f in sorted(os.listdir(adir)):
            if not f.endswith(".svg"):
                continue
            try:
                root = ET.parse(os.path.join(adir, f)).getroot()
                if not root.tag.endswith("svg"):
                    bad_svg.append(f)
            except Exception:
                bad_svg.append(f)
    out.append(_chk("questions", "q.svg_wellformed", "warn", "SVG 파싱 정상",
                    not bad_svg, ", ".join(bad_svg[:10])))

    # 낭독문 정답번호
    from services.book import derive
    bad_speech = []
    for rc, meta, q in rounds.all_questions():
        r = derive.check_speech(q)
        if r and r["code"] == "speech_answer":
            bad_speech.append(paths.qid(int(meta["round"]), int(q["question_no"])))
    out.append(_chk("questions", "q.speech_answer", "warn",
                    "낭독문 정답번호가 보기 정답과 일치", not bad_speech,
                    ", ".join(bad_speech[:10])))

    drift = lesson.speech_drift()
    out.append(_chk("questions", "q.speech_drift", "warn",
                    "05 lesson 낭독문이 _rounds 와 동일", not drift,
                    (", ".join(d["id"] for d in drift[:6])
                     + " — TTS 손질로 보입니다. 낭독문을 직접 고치지 않는 한 유지됩니다.")
                    if drift else ""))
    return out


def check_videos() -> list[dict]:
    out: list[dict] = []
    rows = rbundles.scan_all()
    by_code = {r["code"]: r for r in rows}

    out.append(_chk("videos", "v.bundle_count", "error",
                    f"번들 {_want_bundles()}개 (회차별 {BUNDLES_PER_ROUND}개)",
                    len(rows) == _want_bundles(), f"현재 {len(rows)}개"))

    broken = [r["code"] for r in rows if not r["ok_1to1"]]
    out.append(_chk("videos", "v.deck_scene_1to1", "error",
                    "deck 슬라이드 = 캡처 씬 (1:1)", not broken,
                    ", ".join(broken[:10])))

    no_mp4 = [r["code"] for r in rows if not r["mp4"]["exists"]]
    out.append(_chk("videos", "v.mp4_exists", "error", "mp4 전부 존재", not no_mp4,
                    ", ".join(no_mp4[:10])))

    small = [f"{r['code']}({r['mp4']['bytes']}B)" for r in rows
             if r["mp4"]["exists"] and r["mp4"]["bytes"] < 1024 * 1024]
    out.append(_chk("videos", "v.mp4_size", "error", "mp4 크기 1MB 이상", not small,
                    ", ".join(small[:10])))

    no_vtt, bad_vtt = [], []
    for r in rows:
        if not r["vtt"]["exists"]:
            no_vtt.append(r["code"])
            continue
        try:
            with open(paths.bundle_vtt(r["code"]), encoding="utf-8") as f:
                if not f.readline().startswith("WEBVTT"):
                    bad_vtt.append(r["code"])
        except OSError:
            bad_vtt.append(r["code"])
    out.append(_chk("videos", "v.vtt_exists", "error", "자막(.ko.vtt) 전부 존재",
                    not no_vtt, ", ".join(no_vtt[:10])))
    out.append(_chk("videos", "v.vtt_header", "error", "자막 첫 줄이 WEBVTT",
                    not bad_vtt, ", ".join(bad_vtt[:10])))

    no_rv = [r["code"] for r in rows if not r["review"]["exists"]]
    out.append(_chk("videos", "v.review_exists", "error", "review.json 전부 존재",
                    not no_rv, ", ".join(no_rv[:10])))
    zero = [r["code"] for r in rows
            if r["review"]["exists"] and not (r["review"]["total_seconds"] or 0) > 0]
    out.append(_chk("videos", "v.review_duration", "error", "영상 길이 > 0",
                    not zero, ", ".join(zero[:10])))

    # ── warn ──
    not_ftyp = []
    for r in rows:
        if not r["mp4"]["exists"]:
            continue
        try:
            with open(paths.bundle_mp4(r["code"]), "rb") as f:
                if b"ftyp" not in f.read(16):
                    not_ftyp.append(r["code"])
        except OSError:
            not_ftyp.append(r["code"])
    out.append(_chk("videos", "v.mp4_playable", "warn", "mp4 헤더에 ftyp 박스",
                    not not_ftyp, ", ".join(not_ftyp[:10])))

    stale = [r["code"] for r in rows if r["status"] == "stale"]
    out.append(_chk("videos", "v.mp4_fresh", "warn",
                    "mp4 가 deck·lesson 보다 새롭다", not stale,
                    (", ".join(stale) + " — 문항이나 deck 을 고친 뒤 아직 렌더하지 "
                     "않았습니다. 문항 데이터만 넘길 거면 무시해도 됩니다.")
                    if stale else ""))

    mismatch = [r["code"] for r in rows
                if r["review"]["slides"] is not None and r["review"]["slides"] != r["scenes"]]
    out.append(_chk("videos", "v.review_slides", "warn", "review 슬라이드 수 = 씬 수",
                    not mismatch, ", ".join(mismatch[:10])))
    return out


def check_youtube() -> list[dict]:
    """유튜브 매핑 — 영상은 mp4 를 올리지 않고 유튜브 embed 로 나간다.

    ★ axexam 의 data/youtube_map.json 은 책마다 갈라야 한다. 번들 키가 SQLD 의
      m01-1…m06-5 와 우리 m01-1…m03-8 구간에서 겹치기 때문이다(패치 1번).
    """
    out: list[dict] = []
    per_book = os.path.join(AXEXAM_DIR, "data", f"youtube_map.{PD_CODE}.json")
    shared = os.path.join(AXEXAM_DIR, "data", "youtube_map.json")
    path = per_book if os.path.isfile(per_book) else shared

    if not os.path.isdir(AXEXAM_DIR):
        out.append(_chk("youtube", "y.axexam", "error", "axexam 저장소 클론됨", False,
                        f"{AXEXAM_DIR} 가 없습니다. "
                        "git clone https://github.com/leedonwoo2827-ship-it/axexam _ref\\axexam"))
        return out

    out.append(_chk("youtube", "y.per_book_map", "error",
                    f"품목 전용 유튜브 매핑 (youtube_map.{PD_CODE}.json)",
                    os.path.isfile(per_book),
                    ("공용 youtube_map.json 을 쓰면 SQLD 의 번들 키(m01-1…m06-5)와 "
                     "겹쳐 서로의 영상 ID 를 덮어씁니다. axexam 패치 1번이 필요합니다.")
                    if not os.path.isfile(per_book) else ""))

    if not os.path.isfile(path):
        out.append(_chk("youtube", "y.map_exists", "error", "유튜브 매핑 파일 존재", False,
                        f"{path} 가 없습니다."))
        return out

    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        out.append(_chk("youtube", "y.map_parse", "error", "유튜브 매핑 파싱", False, str(e)))
        return out

    # 실측 스키마: {"_note":…, "_provider":"youtube", "videos": {"m01-1": {id,label,sec}, …}}
    entries = doc.get("videos") or {}
    want = set(paths.all_bundles())
    missing_keys = sorted(want - set(entries))
    empty = sorted(k for k, v in entries.items()
                   if k in want and not (v or {}).get("id"))
    out.append(_chk("youtube", "y.keys", "error", f"번들 {_want_bundles()}개 항목 존재",
                    not missing_keys, ", ".join(missing_keys[:10])))
    out.append(_chk("youtube", "y.ids", "error", "유튜브 ID 전부 입력됨",
                    not empty,
                    (f"{len(empty)}개 비어 있음: {', '.join(empty[:8])} — "
                     "영상을 유튜브에 올리고 URL 의 v= 값을 넣어야 합니다.")
                    if empty else ""))
    return out


def check_summaries() -> list[dict]:
    out: list[dict] = []
    missing = [k for k in SUMMARY_KEYS if not os.path.isfile(paths.summary_html(k))]
    out.append(_chk("summaries", "s.four_files", "error",
                    f"요약노트 HTML {len(SUMMARY_KEYS)}종 존재", not missing,
                    ", ".join(missing)))
    no_md = [k for k in SUMMARY_KEYS if not os.path.isfile(paths.summary_md(k))]
    out.append(_chk("summaries", "s.md_pair", "warn", "요약노트 .md 짝 존재",
                    not no_md, ", ".join(no_md)))
    stale = [k for k in SUMMARY_KEYS
             if os.path.isfile(paths.summary_md(k))
             and paths.mtime(paths.summary_html(k)) < paths.mtime(paths.summary_md(k))]
    out.append(_chk("summaries", "s.html_fresh", "warn",
                    ".html 이 .md 보다 새롭다", not stale,
                    (", ".join(stale) + " — .md 를 고쳤지만 .html 은 다시 만들어지지 "
                     "않았습니다. 발행되는 것은 .html 입니다.") if stale else ""))
    out.append(_chk("summaries", "s.index", "warn", "summary_index.html 존재",
                    os.path.isfile(paths.summary_index_html())))
    return out


def check_server() -> list[dict]:
    """서버 전제 — 우리가 확인할 수 있는 것만. 나머지는 체크리스트로 넘긴다."""
    out: list[dict] = []
    out.append(_chk("server", "p.pd_format", "error",
                    f"품목 코드 형식 (pd={PD_CODE})", bool(_PD_RE.match(PD_CODE)),
                    "소문자·숫자·하이픈 20자 이내. 언더바는 안 됩니다."))

    keys, dup = [], []
    seen = set()
    for b in paths.all_bundles():
        lo, hi = paths.bundle_range(b)
        for n in range(lo, hi + 1):
            k = f"{b}#{n}"
            keys.append(k)
            if k in seen:
                dup.append(k)
            seen.add(k)
    bad = [k for k in keys if not _PR_KEY_RE.match(k)]
    out.append(_chk("server", "p.pr_key_format", "error",
                    "pr_key 가 서버 정규식을 통과", not bad,
                    (", ".join(bad[:6]) + " — ex_valid_key() 를 통과하지 못하면 "
                     "채점이 오류 없이 0점이 됩니다.") if bad else ""))
    out.append(_chk("server", "p.pr_key_unique", "error", "pr_key 중복 없음",
                    not dup, ", ".join(dup[:6]))),

    out.append(_chk("server", "p.axexam", "error", "axexam 저장소 클론됨",
                    os.path.isfile(os.path.join(AXEXAM_DIR, "scripts", "build_check.py")),
                    f"{AXEXAM_DIR}\\scripts\\build_check.py 가 없습니다."))

    # 디스크 여유 — 06/ 산출물은 작지만(mp4 를 안 담는다) 그래도 확인한다.
    try:
        import shutil
        free = shutil.disk_usage(paths.book_dir()).free
        out.append(_chk("server", "p.disk_free", "warn", "디스크 여유 1GB 이상",
                        free > 1024 ** 3, f"{free / 1024 ** 3:.1f} GB"))
    except Exception:
        pass
    return out


GROUP_LABELS = {
    "questions": "문항",
    "videos": "영상",
    "youtube": "유튜브 매핑",
    "summaries": "요약노트",
    "server": "서버 전제",
}


def run() -> dict:
    if not paths.exists():
        return {"ok": False, "error":
                f"이 작업 폴더에는 아직 문항이 없습니다: {paths.book_dir()}"
                " — _rounds/ 와 02/ 가 있는 폴더로 전환하세요."}

    checks = (check_questions() + check_videos() + check_youtube()
              + check_summaries() + check_server())
    groups = []
    for gid, label in GROUP_LABELS.items():
        rows = [c for c in checks if c["group"] == gid]
        groups.append({
            "key": gid, "label": label, "checks": rows,
            "errors": sum(1 for c in rows if c["level"] == "error" and not c["ok"]),
            "warnings": sum(1 for c in rows if c["level"] == "warn" and not c["ok"]),
        })
    errors = sum(g["errors"] for g in groups)
    warnings = sum(g["warnings"] for g in groups)
    items = bindex.cached_items()
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "groups": groups,
        "counts": {
            "questions": len(items),
            "reviewed": sum(1 for i in items if i["reviewed"]),
            "videos": _want_bundles(),
            "figures": sum(1 for i in items if i["has_figure"]),
            "subjects": len({i["subject_no"] for i in items}),
            "rounds": len({i["round"] for i in items}),
        },
        "pd": PD_CODE,
    }
