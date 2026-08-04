/* 화면 ② 영상 제작·검수 — 목록은 위, 실행은 바닥
 *
 * UX 규칙: 위에 번들 목록이 떠 있고, 행을 누르면 바닥이 그 번들의 실행 판으로 열린다.
 *   바닥 = 슬라이드 + 씬 목록 + 씬별 자막·낭독 + 음성 재생.
 *
 * ★ 렌더는 동시에 하나만. chodangi 의 munje/chNN 스크래치가 exist_ok=True 라서 같은
 *   cid 두 프로세스가 서로를 덮어쓰고, Chromium·TTS·ffmpeg 가 자원을 다 쓴다.
 * ★ 자막 시각: review.json 의 timebase 로 가른다. "video" 면 startSec 이 이미 crossfade
 *   를 반영한 값이라 그대로 쓰고, 표식이 없으면 옛 번들이라 씬순번×crossfade 를 뺀다.
 * ★ 로그 스트림은 화면에 두지 않는다 — 터미널은 서버 창(run.bat) 하나다.
 */
"use strict";

import { $, $$, api, el, escapeHtml, toast, confirmModal, fmtBytes, fmtSec } from "./util.js";
import { pollJob, fireJobChanged, getPref, setPref } from "./store.js";
import { icon, hydrateIcons } from "./icons.js";
import { stackedBar } from "./charts.js";
import { actionBtn } from "./panel.js";

const STATUS_KO = { done: "완료", stale: "재렌더 필요", missing: "미생성", broken: "1:1 깨짐" };
const STATUS_TONE = { done: "ok", stale: "warn", missing: "idle", broken: "err" };
const KIND_KO = { cover: "표지", section: "과목", problem: "문제", answer: "해설",
                  countdown: "생각할 시간", gap: "여백" };

const V = { env: null, list: null, sel: new Set(), bundle: null, data: null,
            scene: null, polling: false, audio: null, beat: null };

export const meta = {
  title: (ctx) => (ctx.panel ? panelTitle(ctx) : `영상 제작·검수 · ${ctx.args[0] || ""}`),
  subtitle: (ctx) => (ctx.panel ? "" :
    "슬라이드·음성·자막을 확인하고 고칩니다. 렌더는 동시에 하나만."),
  actions: (ctx) => {
    if (ctx.panel && ctx.path === "/video") return [
      actionBtn("미완성만 렌더", () => startRender("missing"), { iconName: "play" }),
      actionBtn("전체 렌더", () => startRender("all"), { iconName: "film" }),
    ];
    if (ctx.panel) return [];
    if (ctx.path.startsWith("/render/")) return [
      actionBtn("번들 목록", () => (location.hash = "#/video"), { iconName: "film" }),
      actionBtn("새로고침", () => refresh(), { iconName: "refresh" }),
    ];
    return [
      // 목록은 좌측 레일에서 연다 — 여기 또 두지 않는다.
      actionBtn("사전점검", () => (location.hash = "#/precheck/" + (V.bundle || "")),
        { iconName: "check" }),
      actionBtn("새로고침", () => refresh(), { iconName: "refresh" }),
    ];
  },
};

function panelTitle(ctx) {
  if (ctx.path.startsWith("/precheck/")) return `사전점검 · ${ctx.args[0]}`;
  if (ctx.path.startsWith("/job/")) return "렌더 로그";
  return "영상";
}

/* ★ 이 앱의 UX 핵심 — 목록은 패널(위층), 작업은 바탕(아래층).
 *     #/video        → 위층 패널: 번들 목록 (고르는 곳)
 *     #/video/:code  → 아래층 바탕: 그 번들의 작업 화면 (일하는 곳)
 *   패널을 닫아도 바탕은 언마운트되지 않으므로 렌더 폴링이 살아 있다.
 */
export async function mount(root, ctx) {
  if (ctx.panel) {
    if (ctx.path.startsWith("/precheck/")) return mountPrecheck(root, ctx);
    if (ctx.path.startsWith("/job/")) return mountJobPanel(root, ctx);
    return mountList(root, ctx);
  }
  // #/render/:jobId — 일괄 렌더 진행·터미널. 목록에서 [전체 렌더] 를 누르면 여기로 온다.
  if (ctx.path.startsWith("/render/")) return mountRun(root, ctx);
  return mountWork(root, ctx);
}

/* ══════════ 위층: 패널 — 번들 목록 ══════════ */
async function mountList(root, ctx) {
  root.innerHTML = `
    <div class="qz-bar"><span class="qz-bar-note muted" id="vd-envline"></span></div>
    <div class="table-wrap"><table class="data" id="vd-table"></table></div>
  `;
  await refresh(ctx);
}

/* ══════════ 아래층: 바탕 — 일괄 렌더 진행·터미널 ══════════
 * ★ 렌더 진행판이 바탕에 있어야 하는 이유가 둘이다.
 *   1) 패널은 Esc·스크림 클릭으로 닫히고, 닫히면 마크업이 사라진다. 24번들 2시간을
 *      폴링할 표면이 못 된다. (예전에는 목록 패널에서 렌더를 시작하면서 바탕 카드
 *      #vd-run-card 를 건드려 null.hidden 으로 터졌다.)
 *   2) 2층 라우터는 패널을 열고 닫아도 바탕을 언마운트하지 않는다 — 폴링이 살아 있다.
 */
async function mountRun(root, ctx) {
  const jobId = ctx.args[0];
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card" id="vd-run-card">
      <div class="card-title">렌더 진행</div>
      <div class="term-bar" id="vd-beatbar">
        <span class="term-dot"></span>
        <span id="vd-heartbeat">연결 중…</span>
      </div>
      <div id="vd-prog"></div>
    </div>
    <div class="card">
      <div class="card-title">번들 현황</div>
      <div class="table-wrap"><table class="data" id="vd-table"></table></div>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  try {
    [V.env, V.list] = await Promise.all([
      api("/api/render/env"), api("/api/render/bundles"),
    ]);
    renderTable();
  } catch (e) {
    toast("번들 상태를 불러오지 못했습니다: " + e.message, "err");
  }

  // 이미 끝난 잡이어도 마지막 상태와 로그 전문을 보여준다 — 원인을 봐야 한다.
  //
  // ★ 여기서 로그를 그리면 안 된다. pollJob 이 커서 0 부터 다시 받아 첫 틱에 같은 줄을
  //   또 붙인다(실제로 "[make] m01-1 시작" 이 두 번 찍혔다). 진행률만 즉시 그려서
  //   빈 화면을 피하고, 로그는 폴링 한 곳에서만 쓴다 — 끝난 잡도 첫 틱에 전문이 온다.
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    renderProgress(job);
    attachJob(jobId, job);
  } catch (e) {
    const box = $("#vd-prog");
    if (box) box.appendChild(el("div", "empty", "이 작업을 찾을 수 없습니다: " + e.message));
  }
}

/* ══════════ 본 화면 ══════════ */
/* ══════════ 아래층: 바탕 — 번들 작업 판 ══════════ */
async function mountWork(root, ctx) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card" id="vd-run-card" hidden>
      <div class="card-title">렌더 진행</div>
      <div id="vd-prog"></div>
    </div>
    <div id="vd-work"><div class="empty">불러오는 중…</div></div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  try {
    [V.env, V.list] = await Promise.all([
      api("/api/render/env"), api("/api/render/bundles"),
    ]);
  } catch (e) {
    toast("번들 상태를 불러오지 못했습니다: " + e.message, "err");
  }
  await openBundle(ctx.args[0]);

  // 진행 중인 렌더가 있으면 폴링을 다시 붙인다(화면 이동 후 복귀).
  try {
    const d = await api("/api/jobs?limit=5&kind=render");
    const live = (d.jobs || []).find((j) => j.status === "running" || j.status === "queued");
    if (live) attachJob(live.id);
  } catch (e) { /* 잡 계층 없으면 무시 */ }
}

async function refresh(ctx) {
  try {
    [V.env, V.list] = await Promise.all([
      api("/api/render/env"), api("/api/render/bundles"),
    ]);
  } catch (e) {
    toast("번들 상태를 불러오지 못했습니다: " + e.message, "err");
    return;
  }
  if ($("#vd-table")) { renderEnvLine(); renderTable(ctx); }
  if ($("#vd-work") && V.bundle) await openBundle(V.bundle);
}

/** 실행 환경은 카드 하나를 잡아먹을 값이 아니라 제목 옆 한 줄로 압축한다. */
function renderEnvLine() {
  const e = V.env, box = $("#vd-envline");
  if (!box) return;
  const c = V.list.counts;
  const bad = [];
  if (!e.python_ok) bad.push("chodangi python 없음");
  if (!e.driver_ok) bad.push("make_bundle_video.py 없음");
  box.innerHTML = "";
  box.appendChild(el("span", null,
    ` 완료 ${c.done || 0} · 재렌더 ${c.stale || 0} · 미생성 ${c.missing || 0}`
    + (c.broken ? ` · 1:1 깨짐 ${c.broken}` : "")));
  // 렌더가 돌고 있으면 어디서든 그 터미널로 갈 수 있어야 한다.
  if (e.busy) {
    const go = el("button", "badge brand", "렌더 진행 중 — 터미널 보기");
    go.type = "button";
    go.style.cursor = "pointer";
    go.addEventListener("click", async () => {
      try {
        const d = await api("/api/jobs?limit=5&kind=render");
        const live = (d.jobs || []).find((j) => j.status === "running" || j.status === "queued");
        location.hash = live ? "#/render/" + live.id : "#/video";
      } catch (err) { toast("작업을 찾지 못했습니다: " + err.message, "err"); }
    });
    box.appendChild(go);
  }
  if (bad.length) {
    const w = el("span", "badge err", bad.join(" · "));
    w.title = `${e.python}\n${e.driver}\n.env 의 XAM_CHODANGI 를 확인하세요.`;
    box.appendChild(w);
  }
}

function renderTable(ctx) {
  const t = $("#vd-table");
  t.innerHTML = `<thead><tr>
    <th style="width:28px"></th><th>번들</th><th>문항</th>
    <th>슬라이드/씬</th><th>길이</th><th>MP4</th><th>자막</th><th>상태</th><th></th>
  </tr></thead>`;
  const tb = el("tbody");
  V.list.items.forEach((b) => {
    const tr = el("tr");
    tr.style.cursor = "pointer";

    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = V.sel.has(b.code);
    cb.disabled = b.status === "broken";
    cb.addEventListener("click", (e) => e.stopPropagation());
    cb.addEventListener("change", () => {
      cb.checked ? V.sel.add(b.code) : V.sel.delete(b.code);
      updateSelAction();
    });
    tr.appendChild(td(cb));

    const name = el("td");
    name.appendChild(el("b", null, b.code));
    if (b.title) name.appendChild(el("div", "muted", b.title.slice(0, 46)));
    tr.appendChild(name);

    tr.appendChild(td(b.questions));
    const ratio = el("td");
    ratio.appendChild(el("span", b.ok_1to1 ? "" : "badge err",
      `${b.deck_slides < 0 ? "?" : b.deck_slides} / ${b.capture_scenes}`));
    ratio.appendChild(el("div", "muted", `전체 씬 ${b.scenes}`));
    tr.appendChild(ratio);

    tr.appendChild(td(b.review.total_seconds ? fmtSec(b.review.total_seconds) : "—"));
    tr.appendChild(td(b.mp4.exists ? fmtBytes(b.mp4.bytes) : "—"));
    tr.appendChild(td(b.vtt.exists ? "있음" : "—"));

    const st = el("td");
    const badge = el("span", "badge " + STATUS_TONE[b.status], STATUS_KO[b.status]);
    if (b.reason) badge.title = b.reason;
    st.appendChild(badge);
    tr.appendChild(st);

    const act = el("td", "vd-acts");
    act.appendChild(miniBtn("사전점검", (e) => {
      e.stopPropagation(); location.hash = "#/precheck/" + b.code;
    }));
    act.appendChild(miniBtn("렌더", (e) => {
      e.stopPropagation(); startRender([b.code]);
    }, { disabled: !b.ok_1to1 || !V.env.python_ok }));
    tr.appendChild(act);

    // ★ 행 전체가 클릭 대상 — 누르면 패널이 닫히고 바탕이 그 번들로 열린다
    tr.addEventListener("click", () => {
      if (ctx && ctx.navigate) ctx.navigate("/video/" + encodeURIComponent(b.code));
      else location.hash = "#/video/" + encodeURIComponent(b.code);
    });
    tb.appendChild(tr);
  });
  t.appendChild(tb);
  updateSelAction();
}

const td = (v) => {
  const c = el("td");
  if (v instanceof Node) c.appendChild(v); else c.textContent = v;
  return c;
};

function miniBtn(label, fn, { disabled = false } = {}) {
  const b = el("button", "btn sm", label);
  b.type = "button";
  b.disabled = disabled;
  b.addEventListener("click", fn);
  return b;
}

function updateSelAction() {
  const head = $("#panel-actions") || $(".head-actions");
  if (!head) return;
  let btn = $("#vd-sel-btn");
  if (!V.sel.size) { if (btn) btn.remove(); return; }
  if (!btn) {
    btn = actionBtn("", () => startRender([...V.sel]),
      { primary: true, iconName: "play", id: "vd-sel-btn" });
    head.insertBefore(btn, head.firstChild);
  }
  btn.lastChild.textContent = `선택 ${V.sel.size}개 렌더`;
}

/* ══════════ 바닥: 실행 판 ══════════ */
async function openBundle(code) {
  V.bundle = code;
  setPref("vd.bundle", code);
  const box = $("#vd-work");
  if (!box) return;
  box.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    V.data = await api(`/api/render/bundles/${encodeURIComponent(code)}/scenes`);
  } catch (e) {
    box.innerHTML = "";
    box.appendChild(el("div", "empty", "씬을 불러오지 못했습니다: " + e.message));
    return;
  }
  V.scene = V.data.scenes.find((s) => !s.silent) || V.data.scenes[0] || null;
  renderWork();
}

function renderWork() {
  const d = V.data, info = d.info;
  const box = $("#vd-work");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = `
    <div class="card">
      <div class="card-title">${escapeHtml(d.bundle)} — 씬 ${d.count}개
        <span class="muted"> ${escapeHtml(d.title || "")} · 음성 ${escapeHtml(d.voice || "?")} · ${d.speed || 1}배</span>
      </div>
      <div class="vd-env" id="vd-w-chips"></div>
      <div id="vd-w-warn"></div>
      <div class="vd-work-split">
        <aside class="vd-scenes" id="vd-scenes"></aside>
        <section id="vd-stage"></section>
      </div>
    </div>
  `;

  const chips = $("#vd-w-chips");
  const chip = (text, tone, title) => {
    const c = el("span", "status-chip " + (tone || ""), text);
    if (title) c.title = title;
    return c;
  };
  chips.appendChild(chip(STATUS_KO[info.status], STATUS_TONE[info.status] === "ok" ? "ok"
    : STATUS_TONE[info.status] === "err" ? "bad" : "warn", info.reason || ""));
  chips.appendChild(chip(`슬라이드 ${info.deck_slides} / 캡처 씬 ${info.capture_scenes}`,
    info.ok_1to1 ? "ok" : "bad"));
  chips.appendChild(chip(`음성 ${info.audio}개`));
  chips.appendChild(chip(`이미지 ${info.images}개`));
  if (info.mp4.exists) chips.appendChild(chip(`mp4 ${fmtBytes(info.mp4.bytes)}`));
  chips.appendChild(chip(info.vtt.exists ? "자막 있음" : "자막 없음",
    info.vtt.exists ? "ok" : "warn"));

  // 자막 시각 드리프트 — 고친 뒤에 만든 번들(timebase="video")은 뜨지 않는다.
  if (!d.compensated && d.drift_sec > 1) {
    const w = el("div", "qz-warn warn");
    w.appendChild(icon("alert", 15));
    w.appendChild(el("span", null,
      `이 번들은 crossfade 보정 전에 만들어졌습니다 — mp4 에 구워진 자막이 최대 `
      + `${d.drift_sec}초 앞섭니다 (씬 경계마다 ${d.crossfade_sec}초). `
      + `아래 시크는 보정한 값을 쓰므로 검수는 정확합니다. `
      + `다시 렌더하면 자막 자체가 맞게 나옵니다.`));
    $("#vd-w-warn").appendChild(w);
  }

  renderSceneList();
  renderStage();
}

function renderSceneList() {
  const box = $("#vd-scenes");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = "";
  V.data.scenes.forEach((s) => {
    const row = el("div", "vd-scene" + (V.scene && V.scene.scene === s.scene ? " on" : "")
      + (s.silent ? " silent" : ""));
    row.appendChild(el("span", "vd-scene-no", String(s.scene).padStart(2, "0")));
    const mid = el("span", "vd-scene-t");
    mid.textContent = s.heading || KIND_KO[s.kind] || s.kind || "";
    if (s.silent) mid.textContent += " (무음)";
    row.appendChild(mid);
    row.appendChild(el("span", "vd-scene-d", s.dur_sec != null ? fmtSec(s.dur_sec) : "—"));
    row.addEventListener("click", () => {
      V.scene = s;
      $$("#vd-scenes .vd-scene").forEach((r) => r.classList.remove("on"));
      row.classList.add("on");
      renderStage();
    });
    box.appendChild(row);
  });
}

/* 바탕 실행 판의 순서 — 요청대로 고정한다.
 *   1) 자막 / 발음 2단
 *   2) 버튼들
 *   3) 자막 미리보기 (재생하면 그 시간의 큐가 뜬다)
 *   4) 자막 시간 · 자막 텍스트 (큐별 편집)
 *   5) 슬라이드
 *   6) 영상에서 확인
 */
function renderStage() {
  const stage = $("#vd-stage");
  const s = V.scene;
  stage.innerHTML = "";
  if (!s) {
    stage.appendChild(el("div", "empty", "씬을 고르세요."));
    return;
  }
  const pad = (n) => String(n).padStart(2, "0");
  const cueTexts = splitCues(s.narration, Math.max(1, s.cues.length));

  // ── 머리줄
  const head = el("div", "qz-ed-head");
  head.appendChild(el("span", "badge brand", `씬 ${pad(s.scene)}`));
  head.appendChild(el("span", "qz-ed-id", s.heading || KIND_KO[s.kind] || s.kind));
  head.appendChild(el("span", "badge", s.kind || ""));
  if (s.dur_sec != null) head.appendChild(el("span", "badge info", fmtSec(s.dur_sec)));
  if (s.silent) head.appendChild(el("span", "badge idle", "무음"));
  stage.appendChild(head);

  // ── 1) 자막 / 발음 2단
  const two = el("div", "vd-2col");

  const subCol = el("div");
  subCol.appendChild(el("label", "qz-label",
    "자막 — 화면에 뜨는 글자 (고쳐도 mp4 재렌더는 불필요합니다)"));
  const subTa = el("textarea");
  subTa.id = "vd-subtitle";
  subTa.rows = 5;
  subTa.value = s.silent ? "" : cueTexts.join("\n");
  subTa.disabled = !!s.silent;
  subTa.addEventListener("input", () => { markStageDirty(); renderSubPreview(); });
  subCol.appendChild(subTa);
  subCol.appendChild(el("div", "field-hint", s.silent
    ? "무음 씬이라 자막이 없습니다."
    : "한 줄이 한 큐입니다. TTS 는 이 글을 읽지 않습니다 — 오른쪽 발음을 읽습니다."));
  two.appendChild(subCol);

  const narCol = el("div");
  narCol.appendChild(el("label", "qz-label",
    "발음 — TTS 가 읽는 문장. 슬라이드 해설보다 길게 써도 됩니다 (고치면 재합성 + 재렌더)"));
  if (s.silent) {
    const info = el("div", "qz-warn info");
    info.appendChild(icon("bulb", 15));
    info.appendChild(el("span", null, s.kind === "countdown"
      ? `생각할 시간 ${s.countdown_seconds ?? 5}초 — 무음 구간입니다.`
      : `여백 ${s.gap_seconds ?? 2}초 — 무음 구간입니다.`));
    narCol.appendChild(info);
  } else {
    const narTa = el("textarea");
    narTa.id = "vd-narration";
    narTa.rows = 5;
    narTa.value = s.narration || "";
    narTa.addEventListener("input", () => { markStageDirty(); renderSpeechChips(); });
    narCol.appendChild(narTa);
    const chips = el("div", "qz-speech-check");
    chips.id = "vd-speech-chips";
    narCol.appendChild(chips);
  }

  // 음성 플레이어 — 발음의 결과물이라 이 칼럼에 둔다
  if (s.audio.exists) {
    narCol.appendChild(el("label", "qz-label",
      `음성 — audio/scene_${pad(s.scene)}.wav · ${fmtBytes(s.audio.bytes)}`));
    const a = el("audio", "vd-audio");
    a.id = "vd-audio-el";
    a.controls = true;
    a.preload = "metadata";
    a.src = s.audio.url;
    a.addEventListener("timeupdate", () => renderSubPreview(a.currentTime));
    a.addEventListener("seeked", () => renderSubPreview(a.currentTime));
    narCol.appendChild(a);
    V.audio = a;
  } else {
    narCol.appendChild(el("div", "empty", "이 씬의 음성 파일이 없습니다."));
    V.audio = null;
  }
  two.appendChild(narCol);
  stage.appendChild(two);

  // ── 2) 버튼들
  const foot = el("div", "qz-foot");
  const save = el("button", "btn primary", "자막 저장 (mp4 유지)");
  save.type = "button";
  save.id = "vd-save";
  save.disabled = true;
  save.addEventListener("click", () => notYet("자막 저장"));
  foot.appendChild(save);

  const resynth = el("button", "btn", "이 씬 재합성 (발음 반영)");
  resynth.type = "button";
  resynth.id = "vd-resynth";
  resynth.disabled = true;
  resynth.addEventListener("click", () => notYet("씬 재합성"));
  foot.appendChild(resynth);

  foot.appendChild(miniBtn("이 번들 재렌더", () => startRender([V.bundle]),
    { disabled: !V.env || !V.env.python_ok }));
  foot.appendChild(miniBtn("▶ 이 씬 듣기", () => {
    if (V.audio) { V.audio.currentTime = 0; V.audio.play(); }
  }, { disabled: !s.audio.exists }));
  foot.appendChild(miniBtn("영상에서 이 지점", () => seekVideo(s)));

  const hint = el("span", "field-hint qz-foot-hint");
  hint.id = "vd-stage-hint";
  hint.textContent = `05/${V.bundle}/ · 씬 ${s.scene}`;
  foot.appendChild(hint);
  stage.appendChild(foot);

  // ── 3) 자막 미리보기
  const pv = el("div", "qz-field");
  pv.appendChild(el("label", "qz-label",
    "자막 미리보기 — 재생하면 그 시간의 큐가 뜹니다"));
  const stagePv = el("div", "vd-subpv");
  stagePv.id = "vd-subpv";
  pv.appendChild(stagePv);
  stage.appendChild(pv);

  // ── 4) 자막 시간 · 자막 텍스트
  const cue = el("div", "qz-field");
  cue.appendChild(el("label", "qz-label",
    `자막 시간 · 자막 텍스트 (${s.cues.length}개 큐)`));
  if (!s.cues.length) {
    cue.appendChild(el("div", "empty", s.silent
      ? "무음 씬이라 자막이 없습니다."
      : "이 씬의 큐가 review.json 에 없습니다."));
  } else {
    s.cues.forEach((c, i) => {
      const row = el("div", "vd-cue");
      row.dataset.i = String(i);
      row.appendChild(el("span", "vd-cue-t",
        `${fmtClock(c.start)} → ${fmtClock(c.end)}`));
      const ta = el("textarea");
      ta.rows = 1;
      ta.value = cueTexts[i] || "";
      ta.addEventListener("input", () => { markStageDirty(); syncSubtitleFromCues(); });
      row.appendChild(ta);
      row.appendChild(miniBtn("▶", () => {
        if (!V.audio) return;
        V.audio.currentTime = c.start || 0;
        V.audio.play();
      }));
      cue.appendChild(row);
    });
    cue.appendChild(el("div", "field-hint",
      "review.json 의 cues 는 시각만 들고 있어서 글자는 발음에서 잘라 보여줍니다. "
      + "자막을 발음과 다르게 쓰려면 분리해 저장해야 합니다 — "
      + "TTS 는 “아이알오아이”로 읽고 화면엔 “ROI”로 뜨게 하려면 이게 필요합니다."));
  }
  stage.appendChild(cue);

  // ── 5) 슬라이드
  const slide = el("div", "qz-field");
  slide.appendChild(el("label", "qz-label", "슬라이드 — " + (s.image.exists
    ? `images/slide_${pad(s.scene)}.png` : "이미지 없음")));
  if (s.image.exists) {
    const img = el("img", "vd-slide");
    img.src = s.image.url;
    img.alt = `씬 ${s.scene} 슬라이드`;
    img.loading = "lazy";
    slide.appendChild(img);
  } else {
    slide.appendChild(el("div", "empty", "이 씬의 슬라이드 이미지가 없습니다."));
  }
  stage.appendChild(slide);

  // ── 6) 영상에서 확인
  if (V.data.info.mp4.exists) {
    const card = el("div", "card");
    card.appendChild(el("div", "card-title", "영상에서 확인"));
    const v = el("video", "vd-video");
    v.id = "vd-video";
    v.controls = true;
    v.preload = "metadata";
    v.src = V.data.info.mp4.url;
    if (V.data.info.vtt.exists) {
      const tr = document.createElement("track");
      tr.src = V.data.info.vtt.url;
      tr.kind = "subtitles";
      tr.srclang = "ko";
      tr.label = "한국어";
      tr.default = true;
      v.appendChild(tr);
    }
    card.appendChild(v);
    card.appendChild(el("div", "field-hint",
      V.data.compensated
        ? "[영상에서 이 지점] 은 review.json 의 startSec 으로 그대로 이동합니다 "
          + "(이 번들은 crossfade 가 반영돼 있습니다)."
        : "[영상에서 이 지점] 은 crossfade 보정한 위치로 이동합니다 "
          + `(review.json 보다 약 ${V.data.drift_sec}초 늦은 지점).`));
    stage.appendChild(card);
  }

  renderSpeechChips();
  renderSubPreview();
}

/** 큐 편집 → 왼쪽 자막 전체 텍스트 동기화 */
function syncSubtitleFromCues() {
  const rows = $$("#vd-stage .vd-cue textarea");
  const ta = $("#vd-subtitle");
  if (!ta || !rows.length) return;
  ta.value = rows.map((r) => r.value).join("\n");
  renderSubPreview();
}

/** 자막 미리보기 — 영상 위에 뜨는 모습. 재생 위치의 큐를 띄운다. */
function renderSubPreview(atSec) {
  const box = $("#vd-subpv");
  const s = V.scene;
  if (!box || !s) return;
  const ta = $("#vd-subtitle");
  const lines = (ta ? ta.value : "").split("\n").filter((l) => l.trim());
  let idx = 0;
  if (atSec != null && s.cues.length) {
    const hit = s.cues.findIndex((c) => atSec >= (c.start || 0) && atSec < (c.end || 0));
    if (hit >= 0) idx = hit;
    else if (atSec >= (s.cues[s.cues.length - 1].end || 0)) idx = s.cues.length - 1;
  }
  box.innerHTML = "";
  if (!lines.length) {
    box.appendChild(el("div", "vd-subpv-empty",
      s.silent ? "무음 씬 — 자막 없음" : "자막이 비어 있습니다"));
    return;
  }
  box.appendChild(el("div", "vd-subpv-text", lines[Math.min(idx, lines.length - 1)]));
  const c = s.cues[idx];
  box.appendChild(el("div", "vd-subpv-meta", c
    ? `큐 ${idx + 1} / ${lines.length} · ${fmtClock(c.start)} → ${fmtClock(c.end)}`
    : `큐 ${idx + 1} / ${lines.length}`));

  // 큐 행 강조 — 지금 어느 줄이 뜨는지 표에서도 보인다
  $$("#vd-stage .vd-cue").forEach((r) => {
    r.classList.toggle("on", Number(r.dataset.i) === idx);
  });
}

/** 발음 검사 칩 — 낭독문을 고칠 때마다 갱신 */
function renderSpeechChips() {
  const box = $("#vd-speech-chips");
  const s = V.scene;
  if (!box || !s) return;
  const ta = $("#vd-narration");
  const built = speechCheck({ ...s, narration: (ta ? ta.value : s.narration) || "" });
  box.innerHTML = "";
  while (built.firstChild) box.appendChild(built.firstChild);
}

function speechCheck(s) {
  const KOR = ["일", "이", "삼", "사", "오"];
  const box = el("div", "qz-speech-check");
  const t = (s.narration || "").trim();
  const m = t.match(/^정답은\s*(일|이|삼|사|오)\s*번/);
  if (s.kind === "answer") {
    if (!m) {
      box.appendChild(el("span", "status-chip warn",
        "해설 씬인데 ‘정답은 N 번입니다.’ 로 시작하지 않습니다"));
    } else {
      box.appendChild(el("span", "status-chip ok", `낭독문 정답 ${m[1]} 번`));
    }
  }
  const chars = t.length;
  box.appendChild(el("span", "status-chip", `${chars}자`));
  if (chars && s.dur_sec) {
    box.appendChild(el("span", "status-chip",
      `${(chars / s.dur_sec).toFixed(1)}자/초`));
  }
  return box;
}

/** review.json 의 cues 는 시각만 있으므로 낭독문을 큐 수만큼 나눠 보여준다. */
function splitCues(text, n) {
  const t = (text || "").trim();
  if (!t || n <= 0) return [];
  if (n === 1) return [t];
  // 문장 끝 → 쉼표 순으로 자른다 (voicewright.srt.split_into_cues 와 같은 취지)
  const parts = t.split(/(?<=[.!?。])\s+/).filter(Boolean);
  if (parts.length >= n) {
    const out = [];
    const per = Math.ceil(parts.length / n);
    for (let i = 0; i < n; i++) out.push(parts.slice(i * per, (i + 1) * per).join(" "));
    return out;
  }
  const per = Math.ceil(t.length / n);
  const out = [];
  for (let i = 0; i < n; i++) out.push(t.slice(i * per, (i + 1) * per));
  return out;
}

function fmtClock(sec) {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60);
  const s = (sec % 60).toFixed(1).padStart(4, "0");
  return `${m}:${s}`;
}

function seekVideo(s) {
  const v = $("#vd-video");
  if (!v) { toast("이 번들은 아직 mp4 가 없습니다."); return; }
  const at = s.mp4_start_sec != null ? s.mp4_start_sec : (s.start_sec || 0);
  v.currentTime = at;
  v.scrollIntoView({ behavior: "smooth", block: "center" });
  v.play();
}

function markStageDirty() {
  const save = $("#vd-save"), re = $("#vd-resynth");
  if (save) save.disabled = false;
  if (re) re.disabled = false;
  const h = $("#vd-stage-hint");
  if (h) h.textContent = "저장하지 않은 수정이 있습니다.";
}

function notYet(what) {
  confirmModal({
    title: `${what} — 아직 연결되지 않았습니다`,
    body: "이 화면의 읽기·확인은 동작합니다. 쓰기(자막 저장 · 씬 재합성)는 "
      + "chodangi 의 TTS(<code>Engine.synth</code>)를 호출해야 해서 다음 단계에서 붙입니다.<br><br>"
      + "지금은 낭독문을 고치신 뒤 <b>[이 번들 재렌더]</b> 로 전체를 다시 만드시면 됩니다.",
    ok: "닫기", cancel: "",
  });
}

/* ══════════ 렌더 실행 ══════════ */
async function startRender(codes) {
  // ★ 개수를 상수로 쓰지 않는다. 회차 수는 폴더마다 다르다(3회차 24개 / 21회차 168개).
  const rows = (V.list && V.list.items) || [];
  const nAll = rows.length;
  const nTodo = rows.filter((b) => b.status === "missing" || b.status === "stale").length;
  const label = codes === "all" ? `전체 ${nAll}개 번들`
    : codes === "missing" ? `미완성·재렌더 필요 ${nTodo}개 번들`
    : `${codes.length}개 번들 (${codes.slice(0, 3).join(", ")}${codes.length > 3 ? " …" : ""})`;
  const n = codes === "all" ? nAll : codes === "missing" ? nTodo : codes.length;
  if (!n) { toast("렌더할 번들이 없습니다.", "err"); return; }

  const ok = await confirmModal({
    title: "영상을 렌더할까요?",
    body: `<b>${escapeHtml(label)}</b><br><br>`
      + `번들당 약 5분 — <b>합쳐서 약 ${Math.round(n * 5 / 60 * 10) / 10}시간</b> 걸립니다. `
      + "동시에 하나만 실행되며 순차로 진행합니다.<br>"
      + "도구 #3 이 Chromium·TTS·ffmpeg 를 모두 씁니다 — 그 사이 이 PC 는 느려집니다.",
    ok: "렌더 시작", cancel: "취소",
  });
  if (!ok) return;

  try {
    const job = await api("/api/render/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codes, stop_on_error: true }),
    });
    V.sel.clear();
    fireJobChanged({ id: job.id });
    toast("렌더를 시작했습니다.");
    // ★ 목록(패널)에서 시작했으면 패널을 닫고 바탕의 진행·터미널로 내려간다.
    //   패널 안에서 폴링을 붙이면 안 된다 — 패널이 닫히는 순간 표면이 사라진다.
    if (location.hash.replace(/^#/, "") !== "/render/" + job.id) {
      location.hash = "#/render/" + job.id;
    } else {
      attachJob(job.id, job);
    }
  } catch (e) {
    if (e.status === 400) {
      confirmModal({ title: "렌더를 시작하지 않았습니다",
        body: `<pre class="pb-cmd">${escapeHtml(e.message)}</pre>`, ok: "닫기", cancel: "" });
    } else {
      toast("렌더를 시작하지 못했습니다: " + e.message, "err");
    }
  }
}

function attachJob(jobId, initial) {
  const card = $("#vd-run-card");
  if (!card) return;          // 이 화면에는 진행판이 없다(목록 패널). 조용히 넘긴다.
  card.hidden = false;
  renderJobActions(jobId);
  // 폴링 루프는 하나만. 콜백이 매 틱마다 id 로 DOM 을 다시 찾으므로,
  // 화면을 갈아탄 뒤에도 같은 루프가 새 마크업에 그린다.
  if (V.polling) return;
  V.polling = true;
  // 이미 끝난 잡을 열어본 것뿐이면 완료 토스트를 띄우지 않는다.
  const wasLive = !initial || initial.status === "running" || initial.status === "queued";
  pollJob(jobId, (job) => renderProgress(job))
    .then(async (final) => {
      V.polling = false;
      // ★ final 이 null 이면 폴링이 상한에 걸려 스스로 포기한 것이다. 잡이 아직 돌고
      //   있으면 다시 붙는다 — 안 그러면 화면이 그 시점에 얼어붙고, 서버는 정상인데
      //   사람은 렌더가 멈춘 줄 안다(실제로 7시간 렌더에서 그랬다).
      if (!final) {
        try {
          const j = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
          if (j.status === "running" || j.status === "queued") {
            attachJob(jobId, j);
            return;
          }
        } catch (e) { /* 못 물으면 아래로 떨어져 마무리한다 */ }
      }
      if (final && wasLive) {
        const bad = final.status === "error";
        toast(bad ? `렌더가 끝났습니다 — ${final.error || "오류"}` : "렌더를 모두 마쳤습니다.",
          bad ? "err" : "");
      }
      fireJobChanged({ id: jobId });
      await refresh();
    });
}

function renderJobActions(jobId) {
  const card = $("#vd-run-card");
  if (!card) return;
  let bar = $("#vd-job-acts");
  if (!bar) {
    bar = el("div", "vd-env");
    bar.id = "vd-job-acts";
    card.insertBefore(bar, $("#vd-prog"));
  }
  bar.innerHTML = "";
  bar.appendChild(miniBtn("취소", async () => {
    const ok = await confirmModal({
      title: "렌더를 취소할까요?",
      body: "진행 중인 번들의 작업이 버려집니다. 이미 만들어진 mp4 는 그대로 남습니다.",
      ok: "취소하기", cancel: "계속 진행", danger: true,
    });
    if (!ok) return;
    try {
      await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
      toast("취소를 요청했습니다.");
    } catch (e) { toast("취소 실패: " + e.message, "err"); }
  }));
  // ★ 별도 콘솔 창은 두지 않는다. 터미널이 여러 개면 어디를 봐야 하는지 헷갈린다.
  //   서버 창(run.bat)이 유일한 터미널이고, 이 화면은 같은 줄을 그대로 비춘다.
  const a = el("a", "btn sm", "전체 로그 내려받기");
  a.href = `/api/jobs/${encodeURIComponent(jobId)}/log`;
  bar.appendChild(a);
}

function renderProgress(job) {
  const box = $("#vd-prog");
  if (!box) return;           // 화면이 갈렸다 — 폴링은 계속 돌아도 그릴 곳이 없다
  box.innerHTML = "";
  // ★ done_count 는 "대기가 아닌 것" 이라 실패·건너뜀까지 센다. 그대로 쓰면
  //   전부 실패한 잡도 "24 / 24" 로 나와 완료처럼 읽힌다. 내역을 그대로 낸다.
  const st = Object.values(job.items || {});
  const n = (s) => st.filter((v) => v.status === s).length;
  const okN = n("done"), errN = n("error"), skipN = n("skipped");
  const leftN = Math.max(0, (job.total_count || st.length) - okN - errN - skipN);
  // ★ 살아 있다는 표시. chodangi 는 deck 캡처·TTS 구간에서 몇 분씩 한 줄도 안 뱉는다.
  //   로그만 보고 있으면 멈춘 것처럼 보이므로, 경과 시간을 1초마다 스스로 센다.
  startHeartbeat(job);

  const head = el("div", "muted");
  head.textContent = `완료 ${okN} / ${job.total_count}`
    + (errN ? ` · 실패 ${errN}` : "") + (skipN ? ` · 건너뜀 ${skipN}` : "")
    + (leftN ? ` · 남음 ${leftN}` : "")
    + (job.current ? ` · 진행 중 ${job.current}` : "")
    + ` · ${{ running: "실행 중", queued: "대기", done: "끝남", error: "중단됨" }[job.status]
           || job.status}`;
  box.appendChild(head);

  const ol = el("ol", "prog");
  (job.targets || []).forEach((code, i) => {
    const it = (job.items || {})[code] || {};
    const cls = it.status === "done" ? "on" : it.status === "running" ? "busy"
      : it.status === "error" ? "err" : "";
    const li = el("li", "prog-row " + cls);
    li.dataset.stage = code;
    const mark = el("span", "prog-mark");
    mark.appendChild(el("span", "prog-num", String(i + 1)));
    li.appendChild(mark);
    const txt = el("div", "prog-text");
    txt.appendChild(el("b", null, code));
    const sub = el("span");
    if (it.status === "running" && it.scene_total) sub.textContent = `씬 ${it.scene_done}/${it.scene_total}`;
    else if (it.status === "running" && it.tts_total)
      sub.textContent = `${it.stage || "음성·자막 합성"} — ${it.tts_done}/${it.tts_total}`;
    else if (it.status === "running") sub.textContent = it.stage || "시작하는 중…";
    else if (it.status === "done") sub.textContent = it.seconds ? `완료 · ${fmtSec(it.seconds)} 소요` : "완료";
    else if (it.status === "error") sub.textContent = it.error || "오류";
    else if (it.status === "skipped") sub.textContent = it.error || "건너뜀";
    else sub.textContent = "대기";
    txt.appendChild(sub);
    li.appendChild(txt);
    if (it.status === "running" && it.scene_total) {
      const bar = el("div", "prog-bar");
      bar.appendChild(stackedBar([
        { label: "완료", value: it.scene_done, seq: 4 },
        { label: "남음", value: Math.max(0, it.scene_total - it.scene_done), seq: 1 },
      ]));
      li.appendChild(bar);
    }
    ol.appendChild(li);
  });
  box.appendChild(ol);
}

/* 심장박동 — 로그가 조용해도 1초마다 움직인다.
 *
 * chodangi 는 deck 캡처(Chromium)와 TTS 구간에서 몇 분씩 아무것도 출력하지 않는다.
 * 그동안 화면이 굳어 보이면 사람은 죽은 줄 알고 창을 닫는다. 서버를 더 자주 찌르는
 * 대신(폴링은 2초 그대로) 브라우저가 스스로 경과 시간을 센다.
 */
function startHeartbeat(job) {
  const live = job.status === "running" || job.status === "queued";
  if (V.beat) { clearInterval(V.beat); V.beat = null; }

  const cur = (job.items || {})[job.current] || {};
  const stage = cur.stage || (live ? "시작하는 중…" : "");
  const t0 = Date.parse(job.started_at || "") || Date.now();

  const paint = () => {
    const box = $("#vd-heartbeat");
    if (!box) { clearInterval(V.beat); V.beat = null; return; }
    if (!live) {
      box.textContent = { done: "끝남", error: "중단됨" }[job.status] || job.status;
      ($("#vd-beatbar") || box).classList.remove("on");
      return;
    }
    ($("#vd-beatbar") || box).classList.add("on");
    const sec = Math.max(0, Math.round((Date.now() - t0) / 1000));
    const prog = cur.tts_total ? ` · 음성 ${cur.tts_done}/${cur.tts_total}`
      : cur.scene_total ? ` · 씬 ${cur.scene_done}/${cur.scene_total}` : "";
    box.textContent = `${job.current || "준비 중"} · ${stage}${prog}`
      + ` · 전체 ${fmtSec(sec)} 경과 · 자세한 로그는 서버 창(run.bat)에서`;
  };
  paint();
  if (live) V.beat = setInterval(paint, 1000);
}


/* ══════════ 패널: 사전점검 ══════════ */
async function mountPrecheck(root, ctx) {
  const code = ctx.args[0];
  root.innerHTML = '<div class="empty">점검 중…</div>';
  let d;
  try {
    d = await api(`/api/render/bundles/${encodeURIComponent(code)}/precheck`);
  } catch (e) {
    root.innerHTML = "";
    root.appendChild(el("div", "empty", "점검 실패: " + e.message));
    return;
  }
  root.innerHTML = "";

  const head = el("div", "vd-env");
  head.appendChild(el("span", "status-chip " + (d.ok ? "ok" : "bad"),
    d.ok ? "1:1 정상" : "1:1 깨짐"));
  head.appendChild(el("span", "status-chip", `deck 슬라이드 ${d.deck_slides}`));
  head.appendChild(el("span", "status-chip", `캡처 씬 ${d.capture_scenes}`));
  head.appendChild(el("span", "status-chip", `전체 씬 ${d.scene_total}`));
  root.appendChild(head);

  d.messages.forEach((m) => {
    const box = el("div", "qz-warn " + (m.level === "error" ? "err"
      : m.level === "warn" ? "warn" : "info"));
    box.appendChild(icon(m.level === "error" ? "alert" : "bulb", 15));
    box.appendChild(el("span", null, m.text));
    root.appendChild(box);
  });

  const card = el("div", "card");
  card.appendChild(el("div", "card-title", "deck 슬라이드 ↔ 캡처 씬"));
  const cmp = el("div", "vd-cmp");
  cmp.appendChild(el("div", "hd", "deck.html"));
  cmp.appendChild(el("div", "hd", "script JSON (capture:true)"));
  d.rows.forEach((r) => {
    const bad = !r.ok;
    const a = el("div", "row" + (bad ? " bad" : ""));
    a.appendChild(el("span", "muted", String(r.i + 1)));
    a.appendChild(el("span", null, r.deck ?? "(없음)"));
    const b = el("div", "row" + (bad ? " bad" : ""));
    b.appendChild(el("span", "muted", r.scene_no != null ? String(r.scene_no) : "—"));
    b.appendChild(el("span", null, r.scene ?? "(없음)"));
    cmp.appendChild(a);
    cmp.appendChild(b);
  });
  card.appendChild(cmp);
  root.appendChild(card);
}

/* ══════════ 패널: 잡 로그 ══════════ */
async function mountJobPanel(root, ctx) {
  const jobId = ctx.args[0];
  root.innerHTML = "";
  const pre = el("pre", "log-pane");
  pre.style.maxHeight = "60vh";
  root.appendChild(pre);
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    (job.log?.lines || []).forEach((l) => pre.appendChild(el("span", null, l + "\n")));
    const a = el("a", "btn sm", "전체 로그 내려받기");
    a.href = `/api/jobs/${encodeURIComponent(jobId)}/log`;
    root.appendChild(a);
  } catch (e) {
    pre.textContent = "로그를 불러오지 못했습니다: " + e.message;
  }
}
