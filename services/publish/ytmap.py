"""영상 매핑 파일(`data/youtube_map.<pd>.json`) 만들기·동기화.

빌더에 `--init-youtube-map` 이 있지만 앱이 노출하지 않아서, 사람이 72줄을 손으로
쓰거나 명령줄을 따로 열어야 했다. 발행 절차에서 **가장 손이 많이 가는 칸**이라
화면에 붙인다.

★ `id` 는 **절대 건드리지 않는다.** 이 파일은 사람이 채우는 입력이다.
  다시 눌러도 안전해야 한다 — 번들이 늘면 빈 항목만 추가하고, 이미 채운 ID 는 남긴다.
  (빌더의 init 은 "이미 있으면 아무것도 안 함" 이라 회차가 늘어난 뒤에는 쓸 수 없다.)

★ 이름이 youtube_map 이지만 유튜브 전용이 아니다. `_provider` 로 갈린다 —
  drive(구글 드라이브)·youtube·vimeo·file·link. 드라이브로 시작해 나중에 유튜브로
  옮길 수 있다: 항목별 `provider` 가 파일 전역 `_provider` 를 이긴다.
"""
from __future__ import annotations

import json
import os
import re

from services.book import paths
from services.publish import buildcheck

# 빌더 `PROVIDERS` 와 같아야 한다. 모르는 값을 쓰면 화면이 유튜브로 오인해
# 빈 iframe 이 뜨고 원인이 안 보인다(빌더도 그래서 죽인다).
PROVIDERS = ("youtube", "drive", "vimeo", "file", "link")


def path() -> str:
    return buildcheck.youtube_map_path()


def _label(bundle: str) -> str:
    """`m01-1` → `1회 1~10번`. 빌더 `_bundles()` 의 라벨 규칙을 따른다.

    문제 번호 범위는 05/lesson 에서 읽는다 — 상수로 두면 chunk 가 바뀔 때 어긋난다.
    """
    m = re.match(r"m(\d+)-(\d+)$", bundle)
    rn = int(m.group(1)) if m else 0
    part = int(m.group(2)) if m else 0
    nums: list[int] = []
    lp = paths.bundle_lesson(bundle)
    try:
        with open(lp, encoding="utf-8") as f:
            doc = json.load(f)
        for b in doc.get("blocks") or []:
            n = b.get("number")
            if isinstance(n, int):
                nums.append(n)
    except (OSError, ValueError):
        pass
    if nums:
        return f"{rn}회 {min(nums)}~{max(nums)}번"
    return f"{rn}회 {part}부" if part else f"{rn}회"


def _length(bundle: str) -> int:
    """렌더된 영상의 **전체 길이**(초). 화면에 보여 주기만 한다.

    ★ 이 값을 매핑의 `sec` 에 넣으면 안 된다. `sec` 은 길이가 아니라 **시작 초**다 —
      axexam 의 `check.js` 가 `embedUrl()` 에서 `"&start=" + (v.sec|0)` 로 쓴다.
      길이를 넣으면 모든 영상이 끝에서 시작해 빈 화면처럼 보인다.
      (실제로 그렇게 채우려다 잡았다. 필드 이름만 보고 길이라고 읽기 쉽다.)
    """
    p = os.path.join(paths.bundle_dir(bundle), "review.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return 0
    for k in ("totalSeconds", "videoSec", "durSec"):
        v = d.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return int(round(v))
    return 0


def _question_starts(bundle: str) -> list[dict]:
    """문항별 시작 초 — `review.json` 의 슬라이드에서 뽑는다.

    아직 웹으로 나가지 않는다. `check.js` 의 `sec` 은 **번들 하나에 시작점 하나**라서,
    문항별로 뛰려면 웹·빌더 스키마를 늘려야 한다(추후 과제).
    여기서는 화면에 보여 주고, 그때가 오면 이 값을 쓴다.

    시간축은 이미 영상 기준으로 맞춰져 있다(`timebase: "video"`) — 2026-08-03 에
    crossfade 겹침 보정을 넣었다. 그래서 `startSec` 을 그대로 시크에 쓸 수 있다.
    """
    bdir = paths.bundle_dir(bundle)
    # 문항번호는 review.json 에 없다 — script.json 의 씬이 들고 있다(`number`·`kind`).
    # 둘은 `image` 로 맞붙는다(같은 슬라이드 파일명).
    starts: dict[str, float] = {}
    try:
        with open(os.path.join(bdir, "review.json"), encoding="utf-8") as f:
            for s in json.load(f).get("slides") or []:
                img, st = s.get("image"), s.get("startSec")
                if img and isinstance(st, (int, float)):
                    starts[img] = st
    except (OSError, ValueError):
        return []

    scenes: list[dict] = []
    try:
        import glob
        cand = glob.glob(os.path.join(bdir, "script", "*_script.json"))
        if not cand:
            return []
        with open(cand[0], encoding="utf-8") as f:
            scenes = json.load(f).get("scenes") or []
    except (OSError, ValueError):
        return []

    out: list[dict] = []
    for sc in scenes:
        # 문항의 '시작' 은 문제가 뜨는 슬라이드다(정답·카운트다운이 아니라).
        if sc.get("kind") != "problem":
            continue
        n = sc.get("number")
        st = starts.get(sc.get("image"))
        if not isinstance(n, int) or st is None:
            continue
        if not out or out[-1]["number"] != n:
            out.append({"number": n, "startSec": int(round(st))})
    return out


def prov_file(raw: dict, prov: str) -> str:
    """파일 전역 provider — 항목에 provider 가 없을 때 적용되는 값."""
    return prov or raw.get("_provider") or "youtube"


def read() -> dict:
    """현재 매핑 상태. 파일이 없어도 예외를 내지 않는다."""
    p = path()
    bundles = paths.all_bundles()
    raw: dict = {}
    exists = os.path.isfile(p)
    if exists:
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f) or {}
        except (OSError, ValueError) as e:
            return {"exists": True, "path": p, "error": f"읽을 수 없습니다: {e}",
                    "provider": "", "items": [], "bundles": len(bundles)}

    videos = raw.get("videos") or {}
    items = []
    for b in bundles:
        e = videos.get(b) or {}
        prov = (e.get("provider") or raw.get("_provider") or "youtube")
        lv = int(e.get("min_level") or 0)
        items.append({
            "bundle": b,
            "id": (e.get("id") or "").strip(),
            "label": e.get("label") or _label(b),
            "sec": e.get("sec") or 0,             # 시작 초 (길이가 아니다)
            "length": _length(b),                 # 실제 영상 길이 — 보여주기만
            "provider": prov,
            "min_level": lv,
            # 링크 자체가 접근 권한인 provider 가 공개로 나가면 유출이다.
            "leaky": prov in ("drive", "link", "file") and lv <= 1,
            "starts": _question_starts(b),        # 문항별 시작 초 (아직 웹에 안 나감)
            "missing": b not in videos,
        })
    extra = [k for k in videos if k not in set(bundles)]
    filled = sum(1 for i in items if i["id"])
    return {
        "exists": exists, "path": p,
        "provider": raw.get("_provider") or ("youtube" if exists else ""),
        "bundles": len(bundles), "filled": filled,
        "empty": len(bundles) - filled,
        "missing": [i["bundle"] for i in items if i["missing"]],
        "extra": extra,          # 매핑에는 있는데 05/ 에는 없는 번들(예전 회차)
        "items": items,
    }


_BUNDLE_RE = re.compile(r"\bm(\d{1,2})-(\d{1,2})\b")
# 드라이브·유튜브 ID 는 10자 이상의 영숫자·`-`·`_` 다. URL 이든 맨 ID 든 이걸로 잡는다.
_ID_RE = re.compile(r"[A-Za-z0-9_-]{10,}")
# URL 안에서 ID 가 앉는 자리들 — 이게 있으면 우선한다(파일명이 먼저 잡히는 것을 막는다).
_URL_ID_RE = re.compile(
    r"(?:/file/d/|[?&]id=|youtu\.be/|[?&]v=|/embed/|/shorts/|/d/)([A-Za-z0-9_-]{10,})")


def fill_from_text(text: str) -> dict:
    """붙여넣은 목록으로 `id` 를 한 번에 채운다.

    ★ 이 기능이 있는 이유: 번들이 72개다. 드라이브에서 공유 링크를 하나씩 복사해
      파일에 붙여넣으면 그것만 한 시간이 넘고 중간에 한 줄이 밀리면 **영상이 엉뚱한
      회차에 붙는다**(그리고 그건 영상을 봐야 알 수 있다).

    한 줄에서 **번들코드**(m01-1)와 **ID/URL** 을 각각 찾아 맞춘다. 그래서 형식이
    느슨해도 된다 — 아래 전부 같은 결과가 된다:

        m01-1.static.mp4    1AbCdEf...
        m01-1  https://drive.google.com/file/d/1AbCdEf.../view?usp=sharing
        "m01-1.static.mp4","1AbCdEf..."
        m01-1 → https://youtu.be/dQw4w9WgXcQ

    번들코드가 없는 줄은 건너뛰고 그 줄을 돌려준다(조용히 버리지 않는다).
    URL 을 그대로 저장한다 — 빌더가 provider 를 보고 ID 를 뽑는다(손실 변환을 하지 않는다).
    """
    p = path()
    if not os.path.isfile(p):
        raise ValueError("매핑 파일이 없습니다 — [영상 매핑 만들기] 를 먼저 누르세요.")
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    videos: dict = raw.get("videos") or {}
    known = set(paths.all_bundles())

    filled, skipped, unknown, overwrote = [], [], [], []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        mb = _BUNDLE_RE.search(s)
        if not mb:
            skipped.append(s[:80])
            continue
        bundle = f"m{int(mb.group(1)):02d}-{int(mb.group(2))}"
        if bundle not in known:
            unknown.append(bundle)
            continue
        # URL 안의 ID 를 먼저 본다. 없으면 번들코드를 지운 뒤 남는 토큰에서 찾는다 —
        # 안 지우면 파일명(m01-1.static.mp4)의 조각이 ID 로 잡힌다.
        m = _URL_ID_RE.search(s)
        if m:
            vid = s[m.start(0) - 0:] if False else s      # URL 전체를 그대로 넣는다
            vid = next((t for t in s.split() if m.group(1) in t), m.group(1))
        else:
            rest = _BUNDLE_RE.sub(" ", s)
            rest = re.sub(r"\b\w*\.(mp4|mov|mkv|webm)\b", " ", rest, flags=re.I)
            cands = [t for t in _ID_RE.findall(rest) if not t.isdigit()]
            if not cands:
                skipped.append(s[:80])
                continue
            vid = max(cands, key=len)
        e = dict(videos.get(bundle) or {})
        if (e.get("id") or "").strip() and e["id"].strip() != vid.strip():
            overwrote.append(bundle)
        e["id"] = vid.strip()
        e.setdefault("label", _label(bundle))
        e.setdefault("sec", 0)
        videos[bundle] = e
        filled.append(bundle)

    raw["videos"] = videos
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)

    st = read()
    st["matched"] = sorted(set(filled))
    st["overwrote"] = sorted(set(overwrote))
    st["unknown"] = sorted(set(unknown))
    st["skipped"] = skipped[:10]
    return st


def sync(provider: str = "") -> dict:
    """없으면 만들고, 있으면 빠진 번들만 채운다. **id 는 보존한다.**

    provider 를 주면 파일 전역 `_provider` 를 그 값으로 바꾼다(빈 값이면 유지).
    """
    prov = (provider or "").strip()
    if prov and prov not in PROVIDERS:
        raise ValueError(f"모르는 provider: {prov} — {', '.join(PROVIDERS)} 중 하나여야 합니다. "
                         "모르는 값을 쓰면 화면이 유튜브로 오인해 빈 재생창이 뜹니다.")

    bundles = paths.all_bundles()
    if not bundles:
        raise ValueError(f"05/ 에 번들이 없습니다: {paths.book_dir()} — 먼저 #2 로 05/ 를 만드세요.")

    p = path()
    raw: dict = {}
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f) or {}
        except ValueError as e:
            raise ValueError(f"기존 매핑이 깨져 있어 덮어쓰지 않았습니다: {e}") from e

    videos: dict = dict(raw.get("videos") or {})
    added, touched = [], []
    for b in bundles:
        e = dict(videos.get(b) or {})
        new = b not in videos
        if new:
            added.append(b)
        # id 는 손대지 않는다. label·sec 은 비어 있을 때만 채운다.
        if not (e.get("id") or "").strip():
            e["id"] = e.get("id") or ""
        if not e.get("label"):
            e["label"] = _label(b)
            if not new:
                touched.append(b)
        # ★ sec 은 **시작 초**다(길이가 아니다). 기본 0 — 처음부터 재생.
        #   사람이 넣은 값이 있으면 그대로 둔다.
        e.setdefault("sec", 0)
        # 드라이브·link·file 은 링크 자체가 접근 권한이라 공개로 나가면 유출이다.
        # min_level 을 안 적었으면 5(강사)로 둔다 — 빌더가 lv<=1 이면 videos.js 에 굽는다.
        prov = (e.get("provider") or prov_file(raw, prov)).strip()
        if prov in ("drive", "link", "file") and not e.get("min_level"):
            e["min_level"] = 5
        videos[b] = {"id": e.get("id", ""), "label": e.get("label", ""),
                     "sec": e.get("sec", 0),
                     **({"provider": e["provider"]} if e.get("provider") else {}),
                     **({"min_level": e["min_level"]} if e.get("min_level") else {})}

    out = {
        "_note": ("수동 관리 파일 — 빌드가 덮어쓰지 않는다. "
                  "id 에 공유 URL 을 그대로 붙여넣어도 된다(빌더가 ID 만 뽑는다)."),
        "_provider": prov or raw.get("_provider") or "youtube",
        "videos": videos,
    }
    for k, v in raw.items():           # 사람이 손으로 넣은 다른 키는 남긴다
        if k not in out:
            out[k] = v

    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)

    st = read()
    st["added"] = added
    st["updated"] = sorted(set(touched))
    return st
