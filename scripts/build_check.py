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
TEMPLATE = Path(__file__).with_name("check_template.html")
PRESENT_ASSETS = ROOT / "assets" / "present"
YOUTUBE_MAP = ROOT / "data" / "youtube_map.json"
KST = timezone(timedelta(hours=9))
_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


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
    if not TEMPLATE.exists():
        raise SystemExit(f"[error] 템플릿 없음: {TEMPLATE}")
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

    # 2) 문제 수집 + 도식 SVG
    probs, copied, missing = collect(book, out / "figs", meta, strict=args.strict_meta)

    # 3) 영상 — 유튜브 매핑. mp4 를 복사하지 않는다.
    vids, vfilled, vtotal = map_videos(book)

    # 4) 이론(03 요약노트)
    theory, theory_html = build_theory(book, out)

    # 5) 데이터 파일
    (out / "problems.js").write_text(
        "window.PROBLEMS = " + json.dumps(probs, ensure_ascii=False) + ";\n", encoding="utf-8")
    (out / "videos.js").write_text(
        "window.VIDEOS = " + json.dumps(vids, ensure_ascii=False) + ";\n", encoding="utf-8")
    (out / "theory.js").write_text(
        "window.THEORY = " + json.dumps(theory, ensure_ascii=False) + ";\n", encoding="utf-8")
    (out / "theory_content.js").write_text(
        "window.THEORY_HTML = " + json.dumps(theory_html, ensure_ascii=False) + ";\n", encoding="utf-8")

    # 6) check.html — --api-base 가 있으면 EXAM_API 주입 (없으면 StaticDS 로 동작)
    html = TEMPLATE.read_text(encoding="utf-8")
    if args.api_base:
        inject = ('<script>window.EXAM_API=' + json.dumps(args.api_base) + ';'
                  'window.EXAM_PD=' + json.dumps(args.pd) + ';</script>\n')
        html = html.replace("</head>", inject + "</head>", 1)
    (out / "check.html").write_text(html, encoding="utf-8")

    # 7) problems.json
    json_path = None
    if args.emit_json:
        dest = Path(args.json_out).resolve() if args.json_out else (out / "problems.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        json_path = emit_json(probs, meta, args.pd, dest)

    # ── 리포트 ──────────────────────────────────────────────
    subj = sorted({p["subject"] for p in probs if p["subject"]})
    n_rounds = len(set(p["round_num"] for p in probs if p["round_num"]))
    n_vid = sum(len(v) for v in vids.values())
    print(f"[check] {len(probs)}문제 · {n_rounds}회 → {out / 'check.html'}")
    print(f"        과목 {len(subj)}종: {', '.join(subj) or '(없음)'}")
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
