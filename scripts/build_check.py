"""05 lesson JSON + 02 메타 → 정답 체크 정적 웹(06) + DB 임포트용 problems.json.

<book>/05/*/source/lesson_*.json 을 모아 <book>/06/ 생성:
  06/check.html         WOWPASS 디자인 문제풀이+채점 화면
  06/problems.js        window.PROBLEMS  (정적 폴백 전용 — 서버에선 api/problems.php 가 이긴다)
  06/videos.js          window.VIDEOS    (유튜브 {provider,id} — mp4 복사 안 함)
  06/assets/            디자인 자산 (폰트는 CDN 이라 번들하지 않는다)
  06/figs/              문제 도식 SVG
  06/theory/            이론 요약노트

문제의 진짜 과목·검수상태는 05 가 아니라 `02/` 에 있다 → exam_meta.py 참조.

사용:
  python scripts/build_check.py                       # 정적 폴백 빌드
  python scripts/build_check.py --emit-json           # problems.json (adm/exam_import.php 업로드용)
  python scripts/build_check.py --emit-json --pd adsp # 품목 지정
  python scripts/build_check.py --api-base ./api/     # check.html 에 EXAM_API 주입 (서버 배포용)
  python scripts/build_check.py --init-youtube-map    # data/youtube_map.json 골격 1회 생성
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exam_meta import load_meta, load_rounds, load_subjects, src_id  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# check_template.html 은 더 이상 굽지 않는다.
# 문제풀이 화면은 web/exam/check.php + assets/check.css + assets/check.js 로 옮겼다
# (과목게시판이 그누보드 게시판이라 정적 HTML 안에 들어가지 않는다).
# 템플릿 파일은 이력 참고용으로만 남겨둔다 — 빌드는 읽지 않는다.
LANDING  = Path(__file__).with_name("landing_template.html")   # → 06/index.html  (포털 메인)
DETAIL   = Path(__file__).with_name("detail_template.html")    # → 06/detail.html (문제집 상세, ?pd= 로 N품목)
PRESENT_ASSETS = ROOT / "assets" / "present"
YOUTUBE_MAP = ROOT / "data" / "youtube_map.json"
BRAND_JSON = ROOT / "data" / "brand.json"
KST = timezone(timedelta(hours=9))
_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")

# 브랜드가 없을 때의 최소 기본값. 파일을 지워도 빌드가 죽지 않게 한다.
BRAND_FALLBACK = {
    "brand": "XAMpass",
    "brand_html": "<i>XAM</i>pass",
    "tagline": "자격증 문제은행",
    "intro": "자격증 문제은행과 1:1 질문 서비스.",
}


def load_brand() -> dict:
    """data/brand.json — 브랜드 단일 출처.

    형제 사이트(어학XAMpass·금융XAMpass)를 만들 때 고치는 유일한 파일이다.
    `_comment` 키는 설명용이라 걸러낸다.
    """
    if not BRAND_JSON.exists():
        print(f"[경고] {BRAND_JSON.name} 이 없어 기본 브랜드로 굽습니다.")
        return dict(BRAND_FALLBACK)
    try:
        raw = json.loads(BRAND_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"[브랜드] {BRAND_JSON} 파싱 실패: {e}")

    b = dict(BRAND_FALLBACK)
    for k, v in raw.items():
        if k.startswith("_") or not isinstance(v, str):
            continue
        b[k] = v
    for k in BRAND_FALLBACK:
        if not b.get(k):
            raise SystemExit(f"[브랜드] {BRAND_JSON.name} 의 '{k}' 가 비어 있습니다.")
    return b


def php_str(s: str) -> str:
    """PHP 홑따옴표 문자열 리터럴. 홑따옴표와 백슬래시만 이스케이프하면 된다."""
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _parse_bundle(bundle: str) -> tuple[int, int]:
    """m01-3 → (round=1, part=3). part 없으면 0."""
    m = re.search(r"m0*(\d+)(?:-(\d+))?", bundle or "")
    if not m:
        return 0, 0
    return int(m.group(1)), int(m.group(2) or 0)


def _svg_index(book: Path) -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for sub in ("02/assets", "04/assets", "03/assets"):
        d = book / sub
        if d.is_dir():
            for f in d.glob("*.svg"):
                idx.setdefault(f.name, f)
    return idx


def _inline(text: str) -> set[str]:
    return {Path(u).name for u in _IMG_RE.findall(text or "")}


def _hash(p: dict) -> str:
    """콘텐츠 md5 — 임포트가 이걸로 변경분만 UPDATE 한다.

    표시용 메타(subject 라벨 등)는 넣지 않는다. 본문이 안 바뀌었는데
    해시가 흔들리면 매번 전건 UPDATE 가 나간다.
    """
    payload = json.dumps([
        p.get("question") or "", p.get("passage") or "", p.get("sql") or "",
        p.get("table"), p.get("choices") or [], p.get("answer_index"),
        p.get("explanation") or "",
    ], ensure_ascii=False, sort_keys=True)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def collect(book: Path, figs_dir: Path, meta: dict[str, dict], strict: bool = True):
    """05 의 lesson 블록 + 02 의 메타를 조인해 문제 목록을 만든다.

    ⚠ subject 는 lesson 블록에 **없다**(전부 None). 반드시 meta 에서 가져온다.
       예전 `b.get("subject") or subj` 는 lesson 최상위 'SQLD' 로 폴백해
       300문제를 전부 'SQLD' 로 채웠다.
    """
    svg_idx = _svg_index(book)
    figs_dir.mkdir(parents=True, exist_ok=True)
    copied: set[str] = set()
    missing: set[str] = set()

    def ensure(name: str):
        base = Path(name).name
        if base in copied or base in missing:
            return
        src = svg_idx.get(base)
        if src:
            shutil.copy2(src, figs_dir / base)
            copied.add(base)
        else:
            missing.add(base)

    probs: list[dict] = []
    no_meta: list[str] = []
    for lj in sorted((book / "05").glob("*/source/lesson_*.json")):
        try:
            d = json.loads(lj.read_text(encoding="utf-8"))
        except Exception:
            continue
        bundle = lj.parent.parent.name
        rn, _part = _parse_bundle(bundle)
        for b in d.get("blocks") or []:
            if b.get("kind") != "problem" and not b.get("question"):
                continue
            num = b.get("number")
            sid = src_id(rn, num) if (rn and num is not None) else ""
            m = meta.get(sid) or {}
            if not m:
                no_meta.append(f"{bundle}#{num} (src_id={sid or '?'})")

            q = b.get("question") or ""
            passage = b.get("passage") or ""
            expl = b.get("explanation") or ""
            inl_q = _inline(q) | _inline(passage)
            inl_e = _inline(expl)
            asset_field = {Path(a).name for a in (b.get("assets") or [])}
            figures = sorted(asset_field - inl_q - inl_e)
            for name in (asset_field | inl_q | inl_e):
                ensure(name)

            rec = {
                "round_num": rn, "round": f"{rn}회" if rn else bundle, "bundle": bundle,
                "src_id": sid,
                "src_from": str(m.get("derived_from") or ""),
                # ★ meta 에서만 온다. lesson 폴백 없음.
                "subject": m.get("subject") or "",
                "subject_no": m.get("subject_no") or 0,
                "number": num,
                "difficulty": b.get("difficulty") or m.get("difficulty") or "",
                "question": q, "passage": passage,
                "sql": b.get("sql") or "", "table": b.get("table") or None,
                "figures": figures,
                "choices": [str(c) for c in (b.get("choices") or [])],
                "answer_index": b.get("answer_index"),
                "answer": b.get("answer") or m.get("answer") or "",
                "explanation": expl,
                "tags": b.get("tags") or m.get("tags") or [],
                # 검수 상태 — 02/*.md frontmatter 에만 있다
                "verified": bool(m.get("verified")),
                "reviewed": bool(m.get("reviewed")),
                "needs_review": bool(m.get("needs_review")),
            }
            rec["n_choices"] = m.get("n_choices") or len(rec["choices"])
            rec["has_figure"] = bool(figures or inl_q or inl_e)
            rec["has_sql"] = bool(rec["sql"])
            rec["has_table"] = bool(rec["table"])
            rec["pr_hash"] = _hash(rec)
            probs.append(rec)

    probs.sort(key=lambda p: (p["round_num"], p.get("number") or 0))

    if no_meta:
        head = ", ".join(no_meta[:8]) + (" …" if len(no_meta) > 8 else "")
        msg = f"02/ 메타를 못 찾은 문제 {len(no_meta)}건: {head}"
        if strict:
            raise SystemExit(f"[error] {msg}\n"
                             "        --no-strict-meta 로 무시할 수 있지만 그러면 과목이 빈 채로 나간다.")
        print(f"[warn] {msg}")

    return probs, copied, missing


def _num_range(bundle_dir: Path) -> tuple[int, int] | None:
    """번들의 문제 번호 min~max (라벨 'N회 1~10번' 용)."""
    for lj in (bundle_dir / "source").glob("lesson_*.json"):
        try:
            d = json.loads(lj.read_text(encoding="utf-8"))
        except Exception:
            continue
        nums = [b.get("number") for b in (d.get("blocks") or []) if isinstance(b.get("number"), int)]
        if nums:
            return min(nums), max(nums)
    return None


def _bundles(book: Path) -> list[tuple[str, int, int, str]]:
    """[(bundle, round, part, label)] — 05 의 번들 목록. 라벨은 문제번호 범위."""
    out = []
    for d in sorted((book / "05").glob("*/")):
        if not d.is_dir():
            continue
        bundle = d.name
        rn, part = _parse_bundle(bundle)
        if not rn:
            continue
        rng = _num_range(d)
        label = f"{rn}회 {rng[0]}~{rng[1]}번" if rng else (f"{rn}회 {part}부" if part else f"{rn}회")
        out.append((bundle, rn, part, label))
    return out


def init_youtube_map(book: Path) -> Path:
    """data/youtube_map.json 골격을 1회 생성한다. 이미 있으면 건드리지 않는다.

    이 파일은 **수동 관리 입력 파일**이고 빌드가 절대 덮어쓰지 않는다.
    유튜브에 올린 뒤 URL 의 v= 값을 `id` 에 붙여 넣으면 된다.
    """
    if YOUTUBE_MAP.exists():
        print(f"[youtube] 이미 있음 — 덮어쓰지 않는다: {YOUTUBE_MAP}")
        return YOUTUBE_MAP
    YOUTUBE_MAP.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "_note": "수동 관리 파일. 빌드가 덮어쓰지 않는다. id 에 유튜브 URL 의 v= 값을 넣는다.",
        "_provider": "youtube",
        "videos": {b: {"id": "", "label": lab, "sec": 0}
                   for b, _rn, _p, lab in _bundles(book)},
    }
    YOUTUBE_MAP.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[youtube] 골격 생성 {len(data['videos'])}개 → {YOUTUBE_MAP}")
    return YOUTUBE_MAP


def map_videos(book: Path) -> tuple[dict, int, int]:
    """data/youtube_map.json → VIDEOS 맵. **mp4 를 복사하지 않는다.**

    반환 {'1회': [{label, part, provider, id, sec}, ...]}.
    `id` 가 빈 항목은 아직 업로드 전이므로 제외한다(화면에 죽은 버튼이 생기지 않게).
    """
    entries: dict[str, dict] = {}
    provider = "youtube"
    if YOUTUBE_MAP.exists():
        try:
            raw = json.loads(YOUTUBE_MAP.read_text(encoding="utf-8"))
            entries = raw.get("videos") or {}
            provider = raw.get("_provider") or "youtube"
        except Exception as e:
            print(f"[warn] youtube_map.json 파싱 실패({e}) — 영상 없이 빌드한다")

    vids: dict[str, list] = {}
    filled = 0
    total = 0
    for bundle, rn, part, label in _bundles(book):
        total += 1
        e = entries.get(bundle) or {}
        vid = str(e.get("id") or "").strip()
        if not vid:
            continue
        filled += 1
        vids.setdefault(f"{rn}회", []).append({
            "label": e.get("label") or label,
            "part": part,
            # 항목별 provider 가 전역 _provider 를 이긴다 →
            # "1회차만 서버 파일로 테스트, 나머지는 유튜브" 혼용이 된다.
            "provider": e.get("provider") or provider,
            "id": vid,
            "sec": int(e.get("sec") or 0),
        })
    for k in vids:
        vids[k].sort(key=lambda v: v.get("part") or 0)
    return vids, filled, total


def build_theory(book: Path, out: Path) -> tuple[list[dict], dict]:
    """03 요약노트 → 이론 탭 목록 + 내용(JS 에 구워넣을 dict) 반환.

    fetch/iframe 없이 file://·서버 둘 다 되도록, 각 요약 HTML 의 <style>+<body> 를 추출해
    theory_content.js(window.THEORY_HTML)로 굽는다.
    """
    src = book / "03"
    if not src.is_dir():
        return [], {}
    tdir = out / "theory"
    tdir.mkdir(parents=True, exist_ok=True)
    if (src / "assets").is_dir():
        shutil.copytree(src / "assets", tdir / "assets", dirs_exist_ok=True)

    files = sorted(src.glob("summary_*.html"))
    name_map: dict[str, str] = {}
    i = 0
    for f in files:
        if f.name.isascii():
            name_map[f.name] = f.name
        else:
            i += 1
            name_map[f.name] = f"summary_ko{i}.html"

    def subject_of(html: str) -> tuple[int, str]:
        m = re.search(r"<h1[^>]*>([^<]*)</h1>", html) or re.search(r"<title>([^<]*)</title>", html)
        t = (m.group(1) if m else "").strip()
        mm = re.search(r"(\d+)\s*과목\s*[·:\-—\s]*(.*)", t)
        return (int(mm.group(1)), mm.group(2).strip(" —-·")) if mm else (99, t)

    content: dict[str, str] = {}
    items: list[dict] = []
    for f in files:
        raw = f.read_text(encoding="utf-8")
        styles = "".join(re.findall(r"<style[^>]*>(.*?)</style>", raw, re.S))
        mb = re.search(r"<body[^>]*>(.*?)</body>", raw, re.S)
        body = mb.group(1) if mb else raw
        for old, new in name_map.items():
            if old != new:
                body = body.replace(old, new)
        body = re.sub(r'(src|href)="(?!https?:|data:|#|/|theory/)([^"]+)"', r'\1="theory/\2"', body)
        styles = re.sub(r'(^|[^-\w.#])body\b', r'\1:host', styles)
        key = f"theory/{name_map[f.name]}"
        content[key] = "<style>:host{display:block;background:#fff}</style><style>" + styles + "</style>" + body
        if f.stem != "summary_index":
            n, name = subject_of(raw)
            lab = f"{n}과목 · {name}" if n != 99 else (f.stem.replace("summary_", "") + " 요약")
            items.append({"label": lab, "href": key, "sub": n})
    items.sort(key=lambda x: x["sub"])
    return items, content


def emit_json(probs: list[dict], meta: dict[str, dict], pd_id: str, dest: Path) -> Path:
    """adm/exam_import.php 가 업로드받아 upsert 할 problems.json 을 만든다.

    ⚠ `pr_key` 는 임포트의 upsert 축(UNIQUE (pd_id, pr_key))이다.
       바뀌면 같은 문제가 새 행으로 들어가고 pr_id 가 갈려서
       ex_attempt_item / ex_wrong 의 참조가 끊긴다. **절대 형식을 바꾸지 않는다.**
       (check_template.html 의 keyOf() 와 같은 규칙: bundle + '#' + number)
    """
    rd_label = {r["rd_no"]: r["rd_label"] for r in load_rounds(meta)}
    rd_count: dict[int, int] = {}
    for p in probs:
        rd_count[p["round_num"]] = rd_count.get(p["round_num"], 0) + 1

    rows = []
    for p in probs:
        rows.append({
            "pr_key": f'{p["bundle"]}#{p["number"]}',
            "bundle": p["bundle"],
            "rd_no": p["round_num"],
            "pr_no": p["number"],
            "src_id": p["src_id"],
            "src_from": p["src_from"],
            "sj_no": p["subject_no"],
            "sj_name": p["subject"],
            "difficulty": p["difficulty"],
            "question": p["question"],
            "passage": p["passage"],
            "sql_text": p["sql"],
            "table_json": p["table"],
            "figures_json": p["figures"],
            "choices_json": p["choices"],
            "n_choices": p["n_choices"],
            "answer_index": p["answer_index"],
            "answer_label": p["answer"],
            "explanation": p["explanation"],
            "tags_json": p["tags"],
            "has_figure": p["has_figure"],
            "has_sql": p["has_sql"],
            "has_table": p["has_table"],
            "verified": p["verified"],
            "reviewed": p["reviewed"],
            "needs_review": p["needs_review"],
            "pr_hash": p["pr_hash"],
        })

    doc = {
        "pd_id": pd_id,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "rounds": [{"rd_no": rn, "rd_label": rd_label.get(rn, f"{rn}회"), "rd_count": c}
                   for rn, c in sorted(rd_count.items())],
        "subjects": load_subjects(meta),
        "problems": rows,
    }
    dest.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(prog="build_check.py",
                                 description="05 + 02 → 정적 웹(06) + problems.json")
    ap.add_argument("--book", default="D:/00work/ocr-output-260723")
    ap.add_argument("--out", default="")
    ap.add_argument("--pd", default="sqld", help="품목 코드 (ex_product.pd_id)")
    ap.add_argument("--pd-name", default="",
                    help="품목 표시명. file:// 미리보기에만 쓴다 — 서버는 ex_product.pd_name 이 이긴다")
    ap.add_argument("--emit-json", action="store_true", help="problems.json 생성 (DB 임포트용)")
    ap.add_argument("--json-out", default="", help="problems.json 경로 (기본: <out>/problems.json)")
    ap.add_argument("--api-base", default="", help="예: ./api/ — check.html 에 window.EXAM_API 주입")
    ap.add_argument("--init-youtube-map", action="store_true", help="data/youtube_map.json 골격 1회 생성")
    ap.add_argument("--prune", action="store_true",
                    help="예전 빌드가 남긴 06/videos/*.mp4 삭제 (원본은 05/*/draft/ 에 있다)")
    ap.add_argument("--no-strict-meta", dest="strict_meta", action="store_false",
                    help="02/ 메타 미발견을 경고로만 처리 (기본은 빌드 실패)")
    ap.set_defaults(strict_meta=True)
    args = ap.parse_args(argv)

    book = Path(args.book).resolve()

    if args.init_youtube_map:
        init_youtube_map(book)
        return 0

    out = Path(args.out).resolve() if args.out else (book / "06")
    out.mkdir(parents=True, exist_ok=True)

    # ★ 문제집별 데이터 디렉터리 — 06/pd/<pd_id>/
    #
    #   왜 나누는가: 06/ 은 /www/exam/ 에 **납작하게** 복사된다(DEPLOY.md).
    #   두 번째 문제집을 빌드하면 problems.js · theory_content.js · videos.js · figs/ ·
    #   theory/ 가 전부 같은 이름이라 **첫 번째 문제집의 데이터를 덮어쓴다.**
    #   품목이 늘어나는 순간 터지는데, 덮어쓴 뒤에는 원인이 안 보인다.
    #
    #   공용(06/ 루트): index.html · detail.html · assets/ · brand.php
    #   문제집별(06/pd/<pd>/): problems.js · videos.js · theory.js · theory_content.js
    #                          · figs/ · theory/ · problems.json
    pdir = out / "pd" / args.pd
    pdir.mkdir(parents=True, exist_ok=True)

    if not PRESENT_ASSETS.is_dir():
        raise SystemExit(f"[error] 디자인 자산 없음: {PRESENT_ASSETS}")

    # 0) 02/ 메타 (과목·검수상태의 유일한 출처)
    meta = load_meta(book)
    if not meta:
        raise SystemExit(f"[error] 02/ 메타를 못 읽었다: {book / '02'}")

    # 1) 디자인 자산 (fonts 는 CDN 이라 여기 없다)
    #    copytree(dirs_exist_ok=True) 는 소스에 없어진 파일을 지우지 않는다 →
    #    예전 빌드의 assets/fonts/PretendardVariable.woff2(2.06MB)가 남아서 그대로 배포된다.
    #    assets/ 는 빌드가 전적으로 소유하므로 매번 새로 만든다.
    if (out / "assets").exists():
        shutil.rmtree(out / "assets")
    shutil.copytree(PRESENT_ASSETS, out / "assets")

    # 2) 문제 수집 + 도식 SVG  → 06/pd/<pd>/figs/
    probs, copied, missing = collect(book, pdir / "figs", meta, strict=args.strict_meta)

    # 3) 영상 — 유튜브 매핑. mp4 를 복사하지 않는다.
    vids, vfilled, vtotal = map_videos(book)

    # 4) 이론(03 요약노트)  → 06/pd/<pd>/theory/
    theory, theory_html = build_theory(book, pdir)

    # 5) 데이터 파일 — 전부 문제집별 디렉터리로
    (pdir / "problems.js").write_text(
        "window.PROBLEMS = " + json.dumps(probs, ensure_ascii=False) + ";\n", encoding="utf-8")
    (pdir / "videos.js").write_text(
        "window.VIDEOS = " + json.dumps(vids, ensure_ascii=False) + ";\n", encoding="utf-8")
    (pdir / "theory.js").write_text(
        "window.THEORY = " + json.dumps(theory, ensure_ascii=False) + ";\n", encoding="utf-8")
    (pdir / "theory_content.js").write_text(
        "window.THEORY_HTML = " + json.dumps(theory_html, ensure_ascii=False) + ";\n", encoding="utf-8")

    # 6) 화면
    #
    # ★ EXAM_CFG 를 **항상** 주입한다. 예전에는 --api-base 가 있을 때만 넣어서,
    #   로컬 미리보기(file://)가 어떤 품목을 빌드해도 템플릿의 'sqld' 폴백으로 떨어졌다.
    #   즉 로컬에서는 다른 문제집을 확인하는 것이 구조적으로 불가능했다.
    brand = load_brand()
    cfg = {
        "api":   args.api_base or "",
        "pd":    args.pd,
        "data":  f"pd/{args.pd}/",     # 정적 데이터 기준 경로. check.php 도 같은 값을 준다
        "brand": brand,
        # file:// 폴백용. 서버에서는 API 가 이긴다.
        "product": {
            "pd_id":    args.pd,
            "pd_name":  args.pd_name or args.pd.upper(),
            "problems": len(probs),
            "rounds":   len(set(p["round_num"] for p in probs if p["round_num"])),
            "subjects": [{"sj_no": i + 1, "sj_name": s}
                         for i, s in enumerate(sorted({p["subject"] for p in probs if p["subject"]}))],
        },
    }
    inject = ("<script>window.EXAM_CFG=" + json.dumps(cfg, ensure_ascii=False) + ";"
              # 구 이름 별칭 — 템플릿이 아직 이 둘을 참조한다. 한 릴리스만 유지한다.
              "window.EXAM_API=EXAM_CFG.api;window.EXAM_PD=EXAM_CFG.pd;</script>\n")

    # 브랜드 토큰. <title> 과 로고 마크업은 JS 로 바꿀 수 없다(바꿔도 깜빡인다).
    tokens = {
        "{{BRAND}}":      brand["brand"],
        "{{BRAND_HTML}}": brand["brand_html"],
        "{{TAGLINE}}":    brand["tagline"],
        "{{INTRO}}":      brand["intro"],
        # 정적 페이지의 상단 nav·CTA 가 가리킬 기본 문제집.
        # index.html·detail.html 은 공용 페이지라 DB 를 못 본다 — 빌드한 품목을 쓴다.
        # (품목별 링크는 카드/회차 목록이 데이터에서 만든다. nav 는 일반 진입점이다)
        "{{PD}}":         args.pd,
    }

    def emit(tpl: Path, name: str):
        if not tpl.exists():
            return False
        h = tpl.read_text(encoding="utf-8")
        for k, v in tokens.items():
            h = h.replace(k, v)
        # 오타 난 토큰이 그대로 배포되면 이용자가 {{BRND}} 를 본다. 빌드에서 죽인다.
        if "{{" in h:
            leftover = re.findall(r"\{\{[A-Z_]{2,}\}\}", h)
            if leftover:
                raise SystemExit(f"[브랜드] {tpl.name} 에 치환되지 않은 토큰: {sorted(set(leftover))}")
        h = h.replace("</head>", inject + "</head>", 1)
        (out / name).write_text(h, encoding="utf-8")
        return True

    n_pages = 0
    # 랜딩·상세는 있으면 굽는다 (없어도 빌드가 죽지 않게)
    if emit(LANDING, "index.html"):   n_pages += 1

    # ★ check.html 은 더 이상 굽지 않는다 — web/exam/check.php 로 옮겼다.
    #   과목게시판이 그누보드 게시판(PHP)이라 정적 HTML 안에 들어가지 않는다.
    #   예전 URL 이 문서·북마크·체크리스트에 남아 있으므로 리다이렉트만 남긴다.
    (out / "check.html").write_text(
        "<!DOCTYPE html><meta charset=\"utf-8\">"
        "<meta http-equiv=\"refresh\" content=\"0;url=check.php\">\n"
        "<p><a href=\"check.php\">문제풀이 화면으로 이동</a></p>\n",
        encoding="utf-8")
    n_pages += 1

    # ★ 상세는 품목별 파일이 아니라 detail.html 하나가 ?pd= 로 렌더한다.
    #   build_check.py 는 DB 를 못 보므로 품목 목록을 모른다(--pd 하나뿐).
    #   품목별로 구우려면 ex_product 의 사본을 로컬에 또 둬야 하고, 그러면
    #   "품목 추가 = DB 1행" 이라는 원칙이 깨진다.
    if emit(DETAIL, "detail.html"):   n_pages += 1

    # 예전 URL 보존 — /exam/sqld.html 이 문서·북마크·체크리스트에 남아 있다.
    # 파일명이 코드가 아니라 args.pd 로 정해지므로 품목이 늘어도 그대로 동작한다.
    if (out / "detail.html").exists():
        (out / f"{args.pd}.html").write_text(
            "<!DOCTYPE html><meta charset=\"utf-8\">"
            f"<meta http-equiv=\"refresh\" content=\"0;url=detail.html?pd={args.pd}\">\n"
            f"<p><a href=\"detail.html?pd={args.pd}\">이동</a></p>\n",
            encoding="utf-8")
        n_pages += 1

    # PHP 쪽 브랜드. 06/ → /www/exam/ 업로드에 같이 실려 간다.
    (out / "brand.php").write_text(
        "<?php\n"
        "/* build_check.py 가 data/brand.json 에서 생성한다. 손으로 고치지 않는다. */\n"
        f"$EX_BRAND      = {php_str(brand['brand'])};\n"
        f"$EX_BRAND_HTML = {php_str(brand['brand_html'])};\n"
        f"$EX_TAGLINE    = {php_str(brand['tagline'])};\n"
        f"$EX_INTRO      = {php_str(brand['intro'])};\n",
        encoding="utf-8")

    # 7) problems.json
    json_path = None
    if args.emit_json:
        # 문제집별 디렉터리에 둔다. 예전엔 06/problems.json 이라 두 번째 문제집이 덮어썼다.
        # (FTP 로 올리지 않는다 — adm/exam_import.php 화면 업로드다. DEPLOY.md §70)
        dest = Path(args.json_out).resolve() if args.json_out else (pdir / "problems.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        json_path = emit_json(probs, meta, args.pd, dest)

    # ── 옛 납작 레이아웃 잔존물 ─────────────────────────────
    #
    # 예전 빌드는 problems.js · figs/ 등을 06/ 루트에 만들었다. 이제 pd/<pd>/ 로 내려갔지만
    # **예전 파일이 그대로 남는다.** 그걸 두면:
    #   · FTP 업로드가 낡은 사본까지 올려 /www/exam/problems.js 가 공개 상태로 남는다
    #   · 상대경로로 떨어지는 버그가 조용히 낡은 데이터를 읽는다(정답이 다를 수 있다)
    # mp4 경고(아래)와 같은 부류이므로 같은 방식으로 처리한다.
    FLAT = ["problems.js", "videos.js", "theory.js", "theory_content.js", "problems.json"]
    FLAT_DIRS = ["figs", "theory"]
    flat_hit = [f for f in FLAT if (out / f).is_file()]
    flat_dir = [d for d in FLAT_DIRS if (out / d).is_dir()]

    if flat_hit or flat_dir:
        if args.prune:
            for f in flat_hit:
                (out / f).unlink()
            for d in flat_dir:
                shutil.rmtree(out / d)
            print(f"[flat]  옛 납작 파일 정리: {len(flat_hit)}개 + 폴더 {len(flat_dir)}개 삭제")
            print( "        ⚠ 서버에도 남아 있다. FTP 업로드는 지우지 않는다 —")
            print( "          /www/exam/ 의 problems.js · videos.js · theory.js ·")
            print( "          theory_content.js · figs/ · theory/ 를 손으로 지운다.")
        else:
            print(f"\n[FLAT]  옛 레이아웃 파일이 {out} 루트에 남아 있다:")
            if flat_hit: print(f"        파일 {', '.join(flat_hit)}")
            if flat_dir: print(f"        폴더 {', '.join(d + '/' for d in flat_dir)}")
            print( "        이제 정적 데이터는 pd/<품목>/ 아래에 있다. 위 사본은 낡은 것이다.")
            print( "        → 지우려면: python scripts/build_check.py --prune")

    # ── 리포트 ──────────────────────────────────────────────
    subj = sorted({p["subject"] for p in probs if p["subject"]})
    n_rounds = len(set(p["round_num"] for p in probs if p["round_num"]))
    n_vid = sum(len(v) for v in vids.values())
    print(f"[check] {len(probs)}문제 · {n_rounds}회 · 화면 {n_pages}개 → {out}")
    print(f"        과목 {len(subj)}종: {', '.join(subj) or '(없음)'}")
    # 브랜드·품목을 찍는다 — --pd-name 을 잘못 줘도 업로드 전에 눈에 보이게
    print(f"[brand] {brand['brand']}  ·  {brand['tagline']}")
    print(f"        품목 {args.pd} = {cfg['product']['pd_name']}"
          f"   → detail.html?pd={args.pd}  ({args.pd}.html 은 리다이렉트)")
    print(f"[data]  정적 데이터 → {pdir.relative_to(out).as_posix()}/  "
          f"(problems.js · videos.js · theory*.js · figs/ · theory/)")
    print( "        문제풀이 화면은 web/exam/check.php 다 — 이 빌드가 굽지 않는다.")
    print( "        06/check.html 은 check.php 로 보내는 리다이렉트만 남는다.")
    print(f"        지문 {sum(1 for p in probs if p['passage'])} · SQL {sum(1 for p in probs if p['sql'])}"
          f" · 표 {sum(1 for p in probs if p['table'])} · SVG {len(copied)}")
    print(f"        영상 {n_vid}개 매핑 ({vfilled}/{vtotal} 유튜브 ID 입력됨) · mp4 복사 없음")
    if args.api_base:
        print(f"        EXAM_API = {args.api_base}  (ApiDS 모드)")
    else:
        print("        EXAM_API 없음 → StaticDS (file:// 로컬 검수용)")
    if json_path:
        size_kb = json_path.stat().st_size / 1024
        print(f"[json]  {len(probs)}문제 → {json_path}  ({size_kb:,.0f} KB)")
        print("        adm/exam_import.php 에 업로드하면 upsert 된다.")
    if missing:
        print(f"[warn]  SVG 못 찾음 {len(missing)}: {', '.join(sorted(missing))}")
    if vfilled < vtotal:
        print(f"[warn]  유튜브 ID 미입력 {vtotal - vfilled}개 — {YOUTUBE_MAP} 를 채운다"
              " (--init-youtube-map 으로 골격 생성)")

    # 예전 빌드가 남긴 mp4 — 이 빌드는 만들지 않지만 폴더가 남아 있으면 그대로 배포된다.
    # 카페24 뉴아우토반 일반형은 하드 1,400MB · 트래픽 4,000MB 다. 411MB 가 올라가면 끝난다.
    vdir = out / "videos"
    stale = sorted(vdir.glob("*.mp4")) if vdir.is_dir() else []
    if stale:
        mb = sum(f.stat().st_size for f in stale) / 1024 / 1024
        orig = len(list((book / "05").glob("*/draft/*.static.mp4")))
        print(f"\n[STALE] {out / 'videos'} 에 예전 빌드의 mp4 {len(stale)}개 ({mb:,.0f}MB)가 남아 있다.")
        print(f"        이 빌드는 mp4 를 복사하지 않는다. 그대로 두면 FTP 업로드 때 같이 올라간다.")
        print(f"        원본은 05/*/draft/ 에 {orig}개 그대로 있다"
              f"{' (전부 확인됨)' if orig >= len(stale) else ' ⚠ 개수 불일치 — 지우기 전에 확인할 것'}.")
        if args.prune:
            for f in stale:
                f.unlink()
            try:
                vdir.rmdir()
            except OSError:
                pass
            print(f"        → --prune: {len(stale)}개 삭제함. {mb:,.0f}MB 회수.")
        else:
            print("        → 지우려면: python scripts/build_check.py --prune")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
