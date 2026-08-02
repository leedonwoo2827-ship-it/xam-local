"""chodangi-mp4-forge 필수 패치 — 자막 시간축을 영상에 맞춘다.

★ 왜 이 파일이 XAM LOCAL 안에 있는가
  chodangi-mp4-forge 저장소는 언젠가 없어지고 렌더 엔진이 이 앱으로 들어온다. 그러면
  거기에 직접 커밋한 수정은 함께 사라진다. 그래서 고친 내용을 **재현 가능한 패치**로
  이쪽에 남긴다. tools/patch_axexam.py 와 같은 방식이다.

── 무엇을 고치는가 ─────────────────────────────────────────────────────────────
자막이 영상보다 앞서는 버그 두 개다. 둘이 합쳐 m01-1(46씬)에서 83.6초 어긋났다.

1) crossfade 미보정 — 27.0초
   mp4maker 는 씬 경계마다 xfade/acrossfade 로 crossfade 초만큼 **겹쳐서** 잇는다.
   그래서 완성 영상에서 scene N 이 시작하는 시각은 앞 길이의 합이 아니라
       sum(dur[0..N-1]) - N * crossfade        (mp4maker/timeline.py:22-24)
   인데, 자막을 합치는 voicewright/srt.py::merge_scene_cues 는 그냥 더하고 있었다.
   같은 저장소 안에서 두 코드가 서로 다른 시간축을 쓰고 있었다.

2) 무음 씬 누락 — 56.6초 (이게 더 크다)
   app/synth.py::rebuild_chapter_srt 가 씬을 `subtitles/*_narration.srt` **파일 목록**
   으로 훑었다. 카운트다운·여백 씬은 TTS 를 타지 않아 SRT 가 없으므로 통째로 빠지고,
   두 가지가 동시에 틀어졌다.
     - 그 씬들의 길이가 누적 offset 에 안 들어간다 (m01-1: 5초×10 + 2초×10 = 70초)
     - crossfade 를 뺄 때 쓰는 씬 순번이 낭독 씬만 세어 작아진다 (25 vs 진짜 44)
   무음 씬도 wav 는 반드시 있으므로 **오디오 기준**으로 훑고 큐만 비운다.

덤으로 지켜보기 편하게:

3) 진행 로그 — deck 캡처와 TTS 구간이 번들당 몇 분인데 한 줄도 안 뱉어서 멈춘 것처럼
   보였다. voicewright 의 on_progress 를 연결해 씬마다 한 줄 찍는다.
4) 스크래치 비우고 시작 — create_bundle 이 exist_ok=True 라, 취소·비정상 종료 뒤
   남은 munje/chNN 을 다음 실행이 재사용한다. 씬 수가 줄어든 경우 고아 wav 가 남아
   (2) 의 오디오 기준 훑기에서 시간축이 그만큼 늘어난다.

── 실측 검증 (m01-1, 46씬) ────────────────────────────────────────────────────
  merge_scene_cues 수식        mp4maker 와 [0.0, 9.4, 18.8] 완전 일치
  review.json startSec         공식 46/46 일치
  totalSeconds vs mp4 실제     897.354 vs 897.842 (0.49초). 패치 전이면 924.354
  씬 44 자막 위치              패치 전 -56.600초 → 패치 후 +0.000초
  마지막 큐 끝                 895.954초 = 마지막 낭독 씬 끝 (뒤 2초는 무음 여백)

사용:
    venv\\Scripts\\python -m tools.patch_chodangi            # 적용
    venv\\Scripts\\python -m tools.patch_chodangi --check    # 상태만 확인
    venv\\Scripts\\python -m tools.patch_chodangi --revert   # .xam.bak 에서 되돌리기
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

from core.constants import CHODANGI_DIR

BAK = ".xam.bak"

# mp4maker/cli.py 의 --crossfade 기본값과 같아야 한다. 패치 4개가 이 값을 공유한다.
CROSSFADE_SEC = 0.6


def _p(*parts: str) -> str:
    return os.path.join(CHODANGI_DIR, *parts)


def _read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write(path: str, text: str) -> None:
    if not os.path.isfile(path + BAK):
        shutil.copy2(path, path + BAK)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _swap(path: str, pairs: list[tuple[str, str]], marker: str,
          check: bool) -> tuple[bool, str]:
    """앵커 문자열들을 바꿔치기한다. marker 가 이미 있으면 적용된 것으로 본다."""
    if not os.path.isfile(path):
        return False, f"없음: {path}"
    src = _read(path)
    if marker in src:
        return True, "이미 적용됨"
    if check:
        return False, "미적용"
    for old, _new in pairs:
        if src.count(old) != 1:
            return False, (f"앵커가 {src.count(old)}개입니다 — 수동 확인 필요: "
                           f"{old.strip()[:60]!r}")
    for old, new in pairs:
        src = src.replace(old, new, 1)
    _write(path, src)
    return True, "적용"


# ── 패치 1: merge_scene_cues 가 crossfade 를 받는다 ──────────────────────────
P1_OLD = '''def merge_scene_cues(scenes: list[tuple[list[Cue], float]]) -> str:
    """scene별 (큐목록, scene오디오길이)을 누적 offset으로 이어붙여 챕터 SRT 생성.

    각 scene의 큐는 scene 내부 기준(0부터)이라 가정하고, 앞선 scene들의
    오디오 길이 합만큼 밀어서 전역 타임코드로 변환 + 전역 재번호.
    """
    merged: list[Cue] = []
    cursor = 0.0
    for cues, scene_dur in scenes:
        for c in cues:
            merged.append(Cue(text=c.text, start=cursor + c.start, end=cursor + c.end))
        cursor += max(float(scene_dur), 0.0)
    return make_multi_srt(merged)'''

P1_NEW = '''def merge_scene_cues(scenes: list[tuple[list[Cue], float]],
                     crossfade: float = 0.0) -> str:
    """scene별 (큐목록, scene오디오길이)을 누적 offset으로 이어붙여 챕터 SRT 생성.

    각 scene의 큐는 scene 내부 기준(0부터)이라 가정하고, 앞선 scene들의
    오디오 길이 합만큼 밀어서 전역 타임코드로 변환 + 전역 재번호.

    ★ crossfade — 씬을 이어붙일 때 경계마다 겹치는 초.

      wav 를 단순히 이어 붙이면 총 길이는 합이지만, mp4maker 는 씬 경계마다
      xfade/acrossfade 로 crossfade 초만큼 **겹쳐서** 합친다. 그래서 완성된 영상에서
      scene N 이 시작하는 시각은 앞 길이의 합이 아니라

          sum(dur[0..N-1]) - N * crossfade        (mp4maker/timeline.py:22-24 와 동일)

      이다. 이 보정을 빼먹으면 자막이 씬마다 crossfade 초씩 앞서고, 오차가 누적된다.
      42씬 × 0.6초면 마지막 자막이 24.6초 빨리 뜬다 — 실제로 그렇게 나갔다.

      기본값 0.0 은 crossfade 없이 그냥 이어 붙이는 경우(voicewright 단독 사용)다.
      영상 합성에 쓸 SRT 라면 **반드시** 합성에 쓰는 값과 같은 값을 넘겨야 한다.
    """
    merged: list[Cue] = []
    cumulative = 0.0
    xf = max(float(crossfade), 0.0)
    for n, (cues, scene_dur) in enumerate(scenes):
        # 클램프 위치도 mp4maker 와 같아야 한다. 첫 씬들이 crossfade 보다 짧으면
        # 음수 시작이 나오는데, ffmpeg 는 그걸 0 으로 깔아뭉갠다.
        cursor = max(0.0, cumulative - n * xf)
        for c in cues:
            merged.append(Cue(text=c.text, start=cursor + c.start, end=cursor + c.end))
        cumulative += max(float(scene_dur), 0.0)
    return make_multi_srt(merged)'''


def patch1(check: bool) -> tuple[bool, str]:
    return _swap(_p("voicewright", "srt.py"), [(P1_OLD, P1_NEW)],
                 marker="crossfade: float = 0.0) -> str:", check=check)


# ── 패치 2: run_batch 가 crossfade 를 넘긴다 ────────────────────────────────
P2_PAIRS = [
    ("    on_progress: ProgressCb | None = None,\n"
     "    flat_layout: bool = False,\n"
     ") -> BatchResult:\n",
     "    on_progress: ProgressCb | None = None,\n"
     "    flat_layout: bool = False,\n"
     "    crossfade: float = 0.0,\n"
     ") -> BatchResult:\n"
     "    # crossfade: 씬을 이어붙일 때 경계마다 겹치는 초. 통합 SRT 의 시간축을 완성\n"
     "    #   영상에 맞추는 데만 쓴다(merge_scene_cues 주석). 0 이면 기존 동작.\n"),
    ("    chapter_srt_text = merge_scene_cues(scene_seq)\n",
     "    chapter_srt_text = merge_scene_cues(scene_seq, crossfade)\n"),
]


def patch2(check: bool) -> tuple[bool, str]:
    return _swap(_p("voicewright", "batch.py"), P2_PAIRS,
                 marker="merge_scene_cues(scene_seq, crossfade)", check=check)


# ── 패치 3: 무음 씬을 시간축에 넣는다 (오디오 기준 훑기) + crossfade 전달 ────
P3_PAIRS = [
    ('_PER_SCENE_SRT_RE = re.compile(r"^ch[^_]+_(\\d+)_narration\\.srt$")\n',
     '_PER_SCENE_SRT_RE = re.compile(r"^ch[^_]+_(\\d+)_narration\\.srt$")\n'
     '_PER_SCENE_WAV_RE = re.compile(r"^ch[^_]+_(\\d+)_narration\\.wav$")\n'),

    ("    total_step: int | None = None,\n"
     "    on_progress=None,\n"
     ") -> dict:\n",
     "    total_step: int | None = None,\n"
     "    on_progress=None,\n"
     "    crossfade: float = 0.0,\n"
     ") -> dict:\n"),

    ("            on_progress=on_progress,\n"
     "            flat_layout=True,\n"
     "        )\n",
     "            on_progress=on_progress,\n"
     "            flat_layout=True,\n"
     "            crossfade=crossfade,\n"
     "        )\n"),

    ("    # 통합 SRT는 항상 디스크의 모든 per-scene SRT/WAV 기준으로 다시 만든다.\n"
     "    chapter_srt = rebuild_chapter_srt(bundle)\n",
     "    # 통합 SRT는 항상 디스크의 모든 per-scene SRT/WAV 기준으로 다시 만든다.\n"
     "    # ★ crossfade 를 같이 넘긴다 — 이 한 줄이 최종 자막의 시간축을 정한다.\n"
     "    chapter_srt = rebuild_chapter_srt(bundle, crossfade)\n"),

    ("def rebuild_chapter_srt(bundle_dir: str | Path) -> Path | None:\n"
     '    """번들의 audio/*.wav + subtitles/*_narration.srt 를 모아 통합 chNN.srt 재생성.\n'
     "\n"
     "    per-scene SRT(멀티큐)를 실측 오디오 길이만큼 누적 offset으로 병합한다.\n"
     "    audio가 없는 씬은 통합 SRT에 넣지 못하므로 건너뛴다.\n"
     '    """\n',
     "def rebuild_chapter_srt(bundle_dir: str | Path, crossfade: float = 0.0) -> Path | None:\n"
     '    """번들의 audio/*.wav + subtitles/*_narration.srt 를 모아 통합 chNN.srt 재생성.\n'
     "\n"
     "    per-scene SRT(멀티큐)를 실측 오디오 길이만큼 누적 offset으로 병합한다.\n"
     "    씬 목록은 **audio/*_narration.wav** 기준이다 — 무음 씬은 SRT 가 없어도 길이를\n"
     "    시간축에 넣어야 한다(아래 주석 참고). wav 가 없는 씬만 빠진다.\n"
     "\n"
     "    ★ crossfade — mp4maker 가 씬 경계마다 겹치는 초와 **같은 값**을 넘겨야 한다.\n"
     "      이 함수가 최종 통합 SRT 를 정한다(synthesize 가 마지막에 항상 다시 부른다).\n"
     "      0 으로 두면 자막이 씬마다 그 초만큼 앞서고 오차가 누적된다.\n"
     '    """\n'),

    ("    scene_data: list[tuple[int, list, float]] = []\n"
     '    for srt_p in sorted(sub_dir.glob("*_narration.srt")):\n'
     "        m = _PER_SCENE_SRT_RE.match(srt_p.name)\n"
     "        if not m:\n"
     "            continue\n"
     "        scene_num = int(m.group(1))\n"
     "        wav_p = audio_dir / narration_filename(chapter_id, scene_num)\n"
     "        if not wav_p.exists():\n"
     "            continue\n"
     '        cues = parse_srt_cues(srt_p.read_text(encoding="utf-8"))\n'
     "        scene_data.append((scene_num, cues, _wav_duration(wav_p)))\n",

     "    # ★ 씬을 **오디오** 기준으로 훑는다. SRT 기준으로 훑으면 안 된다.\n"
     "    #\n"
     "    #   무음 씬(countdown·gap)은 TTS 를 타지 않아서 *_narration.srt 가 없다. 그래서\n"
     "    #   SRT 파일 목록으로 훑으면 그 씬들이 아예 빠지고, 두 가지가 동시에 틀어진다.\n"
     "    #     1) 무음 씬의 길이가 누적 offset 에 들어가지 않아 이후 자막이 전부 앞선다\n"
     "    #        (m01-1 실측: countdown 5초 × 10 + gap 2초 × 10 = 70초 누락)\n"
     "    #     2) crossfade 를 뺄 때 쓰는 씬 순번이 낭독 씬만 세어 작아진다\n"
     "    #        (실측: 25 로 계산 → 진짜 44. 씬44 오프셋 751.9 vs 실제 808.5)\n"
     "    #   무음 씬도 wav 는 반드시 있다(synthesize 가 무음 wav 를 쓴다). 그걸 기준으로\n"
     "    #   삼고 자막 큐만 비워 둔다 — 길이는 시간축에 기여하고, 글자는 뜨지 않는다.\n"
     "    scene_data: list[tuple[int, list, float]] = []\n"
     "    if audio_dir.exists():\n"
     '        for wav_p in sorted(audio_dir.glob("*_narration.wav")):\n'
     "            m = _PER_SCENE_WAV_RE.match(wav_p.name)\n"
     "            if not m:\n"
     "                continue\n"
     "            scene_num = int(m.group(1))\n"
     "            srt_p = sub_dir / srt_filename(chapter_id, scene_num)\n"
     '            cues = (parse_srt_cues(srt_p.read_text(encoding="utf-8"))\n'
     "                    if srt_p.exists() else [])\n"
     "            scene_data.append((scene_num, cues, _wav_duration(wav_p)))\n"),

    ("    scene_data.sort(key=lambda t: t[0])\n"
     "    text = merge_scene_cues([(cues, dur) for _, cues, dur in scene_data])\n",
     "    scene_data.sort(key=lambda t: t[0])\n"
     "    text = merge_scene_cues([(cues, dur) for _, cues, dur in scene_data], crossfade)\n"),
]


def patch3(check: bool) -> tuple[bool, str]:
    return _swap(_p("app", "synth.py"), P3_PAIRS,
                 marker="_PER_SCENE_WAV_RE", check=check)


# ── 패치 4: 상수 하나에서 세 곳으로 · 진행 로그 · 스크래치 비우기 ───────────
P4_PAIRS = [
    ("CPS = 6.5\nMIN_SECONDS = 4\n",
     "CPS = 6.5\nMIN_SECONDS = 4\n"
     "\n"
     "# ★ 씬 경계 crossfade — 자막·타이밍·합성이 **같은 값**을 써야 하는 단 하나의 상수.\n"
     "#\n"
     "#   mp4maker 는 씬을 xfade/acrossfade 로 이 초만큼 겹쳐서 잇는다. 그래서 완성\n"
     "#   영상에서 scene N 이 시작하는 시각은 `합 - N*CROSSFADE_SEC` 이다. 예전에는\n"
     "#   합성에만 이 값이 있고 자막·review.json 은 몰라서 자막이 앞섰다. 값이 두\n"
     "#   군데로 갈리지 않게 여기서 한 번 정해 내려보낸다.\n"
     "#     → app.synth.synthesize(crossfade=...)   통합 SRT / .ko.vtt\n"
     "#     → python -m mp4maker --crossfade ...    실제 합성\n"
     "#     → _finalize_bundle()                    review.json 의 startSec\n"
     f"CROSSFADE_SEC = {CROSSFADE_SEC}\n"),

    ("    scratch = bundles.create_bundle(cid)\n"
     '    (scratch / "clips").mkdir(parents=True, exist_ok=True)\n'
     '    print(f"[make] round={round_code} scratch={scratch}")\n',

     "    # ★ 스크래치를 먼저 비운다. create_bundle 은 exist_ok=True 라 예전 내용이 남는다.\n"
     "    #\n"
     "    #   보통은 이 스크립트가 끝나면서 rmtree 하지만, **취소하거나 중간에 죽으면\n"
     "    #   남는다.** 그 상태로 다시 돌리면 지난 실행의 wav/srt/png 가 섞인다. 특히\n"
     "    #   씬 수가 줄어든 경우 고아 wav 가 남아 자막 시간축이 그만큼 늘어난다 —\n"
     "    #   rebuild_chapter_srt 가 audio/*.wav 를 훑기 때문이다.\n"
     "    #   사람이 '이전 것을 지워야 하나' 를 고민하지 않아도 되게 코드가 보장한다.\n"
     "    scratch = bundles.bundle_path(cid)\n"
     "    if scratch.exists():\n"
     "        shutil.rmtree(scratch, ignore_errors=True)\n"
     "    scratch = bundles.create_bundle(cid)\n"
     '    (scratch / "clips").mkdir(parents=True, exist_ok=True)\n'
     '    print(f"[make] round={round_code} scratch={scratch} (비우고 시작)", flush=True)\n'),

    ('    print("[make] 음성/자막 (Supertonic3) …")\n'
     "    from app.synth import synthesize   # 늦은 import(env 설정 후, 모델 로드 무거움)\n"
     '    asyncio.run(synthesize(scratch, voice_override=series.get("voice"),\n'
     '                           speed=series.get("speed")))\n',

     '    print("[make] 음성/자막 (Supertonic3) …", flush=True)\n'
     "    from app.synth import synthesize   # 늦은 import(env 설정 후, 모델 로드 무거움)\n"
     "\n"
     "    # ★ 씬마다 한 줄 찍는다. 이 구간이 번들당 몇 분인데 예전에는 아무것도 안 뱉어서\n"
     "    #   지켜보는 쪽에서 멈춘 것처럼 보였다. XAM LOCAL 이 이 줄로 진행률을 센다.\n"
     "    #   flush 하지 않으면 파이프에 갇혀 끝나야 한꺼번에 나온다.\n"
     "    def _tts_progress(done: int, total: int, scene: int | None = None) -> None:\n"
     '        tag = f" (씬 {scene})" if scene is not None else ""\n'
     '        print(f"[tts] 음성 {done}/{total}{tag}", flush=True)\n'
     "\n"
     '    asyncio.run(synthesize(scratch, voice_override=series.get("voice"),\n'
     '                           speed=series.get("speed"), crossfade=CROSSFADE_SEC,\n'
     "                           on_progress=_tts_progress))\n"),

    ('    rc = subprocess.run([sys.executable, "-m", "mp4maker", str(scratch),\n'
     '                         "--kenburns", "off", "--no-subs", "--no-soft-sub"],\n',
     '    rc = subprocess.run([sys.executable, "-m", "mp4maker", str(scratch),\n'
     "                         # ★ 명시한다. mp4maker 기본값도 0.6 이지만, 자막을 그 값에\n"
     "                         #   맞춰 만들어 놓고 합성만 딴 값을 쓰면 조용히 다시 어긋난다.\n"
     '                         "--crossfade", str(CROSSFADE_SEC),\n'
     '                         "--kenburns", "off", "--no-subs", "--no-soft-sub"],\n'),

    ("    # 타이밍 누적\n"
     "    start = 0.0\n"
     "    timing = []\n"
     "    for r in recs:\n"
     '        si = r["si"]\n'
     "        d = durations.get(si, 0.0)\n"
     '        timing.append({"scene": si, "kind": r["kind"], "durSec": d, '
     '"startSec": round(start, 3)})\n'
     "        start += d\n"
     "    total = round(start, 3)\n",

     "    # 타이밍 누적\n"
     "    # ★ startSec 은 **완성된 mp4 기준**이다. 오디오 길이 합이 아니다.\n"
     "    #   mp4maker 가 씬 경계마다 CROSSFADE_SEC 만큼 겹치므로 scene N 은\n"
     "    #   `합 - N*CROSSFADE_SEC` 에 시작한다(mp4maker/timeline.py:22-24 와 같은 식).\n"
     "    #   예전에는 합을 그대로 넣어서, 이 값으로 시크하면 씬마다 0.6초씩 빗나갔다.\n"
     "    cumulative = 0.0\n"
     "    timing = []\n"
     "    for n, r in enumerate(recs):\n"
     '        si = r["si"]\n'
     "        d = durations.get(si, 0.0)\n"
     "        start = max(0.0, cumulative - n * CROSSFADE_SEC)\n"
     '        timing.append({"scene": si, "kind": r["kind"], "durSec": d,\n'
     '                       "startSec": round(start, 3)})\n'
     "        cumulative += d\n"
     "    # 완성 영상의 총 길이도 겹친 만큼 짧다.\n"
     "    total = round(max(0.0, cumulative - max(0, len(recs) - 1) * CROSSFADE_SEC), 3)\n"),

    ('    review["totalSeconds"] = total\n',
     '    review["totalSeconds"] = total\n'
     "    # ★ 이 번들의 startSec·자막이 어느 시간축인지 밝힌다.\n"
     '    #   "video"  = crossfade 보정 완료(이 패치 이후에 만든 것). 그대로 시크하면 맞는다.\n'
     "    #   키 없음  = 예전 번들. 오디오 길이 합이라 읽는 쪽이 n*crossfade 를 빼야 한다.\n"
     "    #   이게 없으면 보정한 번들을 또 보정해서 반대로 틀어진다.\n"
     '    review["timebase"] = "video"\n'
     '    review["crossfadeSec"] = CROSSFADE_SEC\n'),
]


def _deck_notice(src: str) -> str | None:
    """deck 캡처 시작을 알리는 줄을 capture_deck 호출 바로 앞에 끼운다.

    ★ 이 조각만 들여쓰기를 코드에서 읽어 맞춘다. 상류는 --reuse-images 때문에 이
      호출이 if/else 안에 들어가 있어 8칸이고, 예전 스냅샷은 4칸이었다. 앵커를 통째로
      박아 두면 저장소가 조금만 바뀌어도 패치가 깨진다.
    """
    key = "deck_capture.capture_deck("
    i = src.find(key)
    if i < 0:
        return None
    bol = src.rfind("\n", 0, i) + 1
    indent = src[bol:i]
    indent = indent[: len(indent) - len(indent.lstrip())]
    add = (f"{indent}# Chromium 을 띄우고 슬라이드를 찍는 동안 1~2분 조용하다. 시작을 알려 둔다.\n"
           f'{indent}print(f"[make] deck 캡처 시작 — 슬라이드 {{n_cap}}장 (Chromium)", flush=True)\n')
    return src[:bol] + add + src[bol:]


def patch4(check: bool) -> tuple[bool, str]:
    path = _p("make_bundle_video.py")
    ok, msg = _swap(path, P4_PAIRS, marker="CROSSFADE_SEC", check=check)
    if not ok or check or msg == "이미 적용됨":
        return ok, msg
    src = _read(path)
    if "deck 캡처 시작" not in src:
        out = _deck_notice(src)
        if out is None:
            return True, "적용 (deck 캡처 시작 알림은 건너뜀 — capture_deck 호출을 못 찾음)"
        _write(path, out)
    return True, "적용"


PATCHES = [
    ("1. merge_scene_cues 가 crossfade 를 받는다 (자막 시간축)", patch1),
    ("2. run_batch → merge_scene_cues 로 crossfade 전달", patch2),
    ("3. 무음 씬을 시간축에 포함 (오디오 기준 훑기) + crossfade 전달", patch3),
    ("4. CROSSFADE_SEC 단일 상수 · review.json timebase · 진행 로그 · 스크래치 비우기", patch4),
]

TOUCHED = [
    ("voicewright", "srt.py"),
    ("voicewright", "batch.py"),
    ("app", "synth.py"),
    ("make_bundle_video.py",),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="patch_chodangi")
    ap.add_argument("--check", action="store_true", help="상태만 확인(쓰지 않음)")
    ap.add_argument("--revert", action="store_true", help=f"{BAK} 에서 되돌리기")
    args = ap.parse_args(argv)

    print(f"chodangi: {CHODANGI_DIR}")
    if not os.path.isdir(CHODANGI_DIR):
        print("[error] chodangi 폴더가 없습니다. .env 의 XAM_CHODANGI 를 확인하세요.")
        return 2

    if args.revert:
        n = 0
        for parts in TOUCHED:
            b = _p(*parts) + BAK
            if os.path.isfile(b):
                shutil.copy2(b, b[: -len(BAK)])
                os.remove(b)
                print(f"  되돌림: {os.path.join(*parts)}")
                n += 1
        print(f"{n}개 파일을 되돌렸습니다." if n else "되돌릴 백업이 없습니다.")
        return 0

    fails = 0
    for label, fn in PATCHES:
        ok, msg = fn(args.check)
        print(f"  [{'OK  ' if ok else 'FAIL'}] {label} — {msg}")
        if not ok:
            fails += 1

    if args.check:
        print("\n확인만 했습니다. 적용하려면 --check 없이 다시 실행하세요.")
        return 1 if fails else 0

    if fails:
        print(f"\n{fails}개 패치를 적용하지 못했습니다. 위 메시지를 확인하세요.")
        return 1

    # 문법 확인 — 고친 파일이 실제로 컴파일되는지. 3시간 렌더가 1번 번들에서
    # 죽는 것보다 여기서 걸리는 게 낫다.
    import py_compile
    for parts in TOUCHED:
        try:
            py_compile.compile(_p(*parts), doraise=True)
        except py_compile.PyCompileError as e:
            print(f"\n[error] 패치 후 문법 오류: {e}")
            return 2
    print("\n문법 확인 OK (4개 파일)")

    print(f"\n적용 완료. 원본은 *{BAK} 로 남아 있습니다.\n"
          "되돌리려면: python -m tools.patch_chodangi --revert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
