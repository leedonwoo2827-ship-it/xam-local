/* 화면 ③ 발행 — axexam 절차를 순서대로 강제한다
 *
 * 이 화면은 '버튼 하나' 가 아니다. 실수하면 되돌릴 수 없는 절차가 둘 있다.
 *   1) build_check.py 를 --book/--pd 없이 부르면 라이브 SQLD 를 덮어쓴다.
 *      pr_key 가 겹치고 pr_id 는 보존되므로 회원 오답노트 밑에 엉뚱한 문제가 앉는다.
 *   2) 임포트는 서버에 드라이런도 트랜잭션도 없다.
 * 그래서 카드 5장으로 순서를 못박고, 실행할 명령을 그대로 보여준다.
 */
"use strict";

import { $, $$, api, el, escapeHtml, toast, confirmModal, fmtBytes } from "./util.js";
import { pollJob, fireJobChanged } from "./store.js";
import { icon, hydrateIcons } from "./icons.js";
import { donut, stackedBar } from "./charts.js";
import { actionBtn } from "./panel.js";

const P = { pre: null, env: null, problems: null, ftp: null, checklist: null,
            ytmap: null, polling: false };

export const meta = {
  title: "발행 to XAMpass",
  subtitle: "로컬 산물 → axexam 빌드 → FTP + 관리자 화면 임포트. 순서대로 진행합니다.",
  actions: () => [
    actionBtn("사전점검 다시", () => refresh(), { iconName: "refresh" }),
    actionBtn("06/ 폴더 열기", () => openOut(), { iconName: "folder" }),
  ],
};

export async function mount(root, ctx) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card"><div class="card-title">① 사전점검</div><div id="pb-pre"></div></div>
    <div class="card"><div class="card-title">② 영상 매핑 — 링크를 여기 넣습니다</div>
      <div id="pb-ytmap"></div></div>
    <div class="card"><div class="card-title">③ 빌드 — axexam scripts/build_check.py</div>
      <div id="pb-build"></div></div>
    <div class="card"><div class="card-title">④ problems.json 검증 (임포트 드라이런)</div>
      <div id="pb-problems"></div></div>
    <div class="card"><div class="card-title">⑤ 업로드 — 폴더 하나를 /www/ 로</div>
      <div id="pb-ftp"></div></div>
    <div class="card"><div class="card-title">⑥ 서버 단계 — 여기서부터는 사람이 합니다</div>
      <div id="pb-server"></div></div>
  `;
  root.appendChild(page);
  hydrateIcons(page);
  await refresh();
}

async function refresh() {
  const set = (id, msg) => { const b = $(id); if (b) b.innerHTML = `<div class="empty">${msg}</div>`; };

  /* ★ 도착하는 대로 그린다 — 전부 기다리지 않는다.
   *
   *   사전점검은 720문항을 훑어 6초가 걸리고 나머지는 0.1초 안이다. 예전에는
   *   Promise.allSettled 로 여섯 개를 묶어 기다린 뒤 한 번에 그려서, **6초 동안
   *   화면이 통째로 비어 있었다.** 업로드 카드(0.0초)까지 사전점검을 기다린 것이다.
   *   빈 화면은 "고장" 처럼 보이고, 실제로 그렇게 오해했다.
   */
  const one = (url, key, render, msg) => {
    if (msg) set(msg[0], msg[1]);
    return api(url)
      .then((v) => { P[key] = v; })
      .catch((e) => { P[key] = { error: e.message }; })
      .then(() => { try { render(); } catch (err) { console.error(err); } });
  };

  await Promise.all([
    one("/api/publish/env", "env", renderBuild, ["#pb-build", "빌드 환경 확인 중…"]),
    one("/api/publish/ytmap", "ytmap", renderYtmap, ["#pb-ytmap", "매핑 확인 중…"]),
    one("/api/publish/problems", "problems", renderProblems,
        ["#pb-problems", "problems.json 확인 중…"]),
    one("/api/publish/checklist", "checklist", renderServer, null),
    // 업로드 카드는 사전점검과 무관하다 — 먼저 뜬다.
    Promise.resolve().then(() => renderStage()),
    // 가장 느린 것을 마지막에 둔다(순서는 무관하지만 읽는 사람에게 의도가 보인다).
    one("/api/publish/preflight", "pre", renderPre, ["#pb-pre", "점검 중… (720문항)"]),
  ]);
}

/* ── ① 사전점검 ────────────────────────────────────── */
function renderPre() {
  const box = $("#pb-pre");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const d = P.pre;
  if (d.error) {
    box.appendChild(el("div", "empty", d.error));
    return;
  }

  const head = el("div", "qz-head");
  const total = d.groups.reduce((a, g) => a + g.checks.length, 0);
  const passed = d.groups.reduce((a, g) => a + g.checks.filter((c) => c.ok).length, 0);
  const st = el("div", "qz-head-stat");
  st.appendChild(donut(Math.round((passed / Math.max(1, total)) * 100), { label: "통과", size: 76 }));
  const t = el("div");
  t.appendChild(el("div", "stat-value", `${passed} / ${total}`));
  t.appendChild(el("div", "muted",
    d.errors ? `오류 ${d.errors}건 · 경고 ${d.warnings}건` : `경고 ${d.warnings}건`));
  st.appendChild(t);
  head.appendChild(st);

  const bars = el("div", "qz-head-bars");
  bars.appendChild(stackedBar([
    { label: "통과", value: passed, seq: 4 },
    { label: "경고", value: d.warnings, seq: 2 },
    { label: "오류", value: d.errors, seq: 3 },
  ]));
  const c = d.counts;
  bars.appendChild(el("div", "muted",
    `문항 ${c.questions} (검수 ${c.reviewed}) · 회차 ${c.rounds} · 과목 ${c.subjects} · `
    + `그림 ${c.figures} · 영상 ${c.videos} · pd=${d.pd}`));
  head.appendChild(bars);
  box.appendChild(head);

  d.groups.forEach((g) => {
    const wrap = el("div", "pb-group");
    const title = el("div", "qz-label",
      `${g.label} — 오류 ${g.errors} · 경고 ${g.warnings}`);
    wrap.appendChild(title);
    const list = el("div", "pb-check");
    g.checks.forEach((chk) => {
      const tone = chk.ok ? "ok" : chk.level === "error" ? "err" : "warn";
      const row = el("div", "item " + tone);
      row.appendChild(icon(chk.ok ? "check" : chk.level === "error" ? "alert" : "bulb", 13));
      const mid = el("div");
      mid.appendChild(el("span", null, chk.label));
      if (chk.detail && !chk.ok) mid.appendChild(el("div", "muted", chk.detail));
      row.appendChild(mid);
      row.appendChild(el("span", "muted", chk.ok ? "" : chk.level === "error" ? "오류" : "경고"));
      list.appendChild(row);
    });
    wrap.appendChild(list);
    box.appendChild(wrap);
  });
}

/* ── ② 영상 매핑 ────────────────────────────────────
 *
 * 발행에서 손이 가장 많이 가는 칸이다. 번들이 72개라 손으로 쓰면 오타가 난다.
 * 빌더에 `--init-youtube-map` 이 있는데 앱이 노출하지 않아 명령줄을 따로 열어야 했다.
 *
 * ★ `sec` 은 **시작 초**다(영상 길이가 아니다). check.js 가 `&start=` 로 쓴다.
 *   길이를 넣으면 모든 영상이 끝에서 시작한다.
 */
function fmtSec(n) {
  const m = Math.floor((n || 0) / 60);
  return `${m}:${String((n || 0) % 60).padStart(2, "0")}`;
}

function renderYtmap() {
  const box = $("#pb-ytmap");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const d = P.ytmap;
  if (!d || d.error) {
    box.appendChild(el("div", "empty", "매핑 상태를 읽지 못했습니다: " + (d?.error || "")));
    return;
  }

  const chips = el("div", "vd-env");
  chips.appendChild(el("span", "status-chip " + (d.exists ? "ok" : "bad"),
    d.exists ? `매핑 파일 있음` : "매핑 파일 없음"));
  chips.appendChild(el("span", "status-chip " + (d.empty ? "bad" : "ok"),
    `링크 ${d.filled} / ${d.bundles}`));
  if (d.provider) chips.appendChild(el("span", "status-chip", `provider=${d.provider}`));
  const leaky = (d.items || []).filter((i) => i.leaky && i.id);
  if (leaky.length) {
    chips.appendChild(el("span", "status-chip bad", `공개 유출 위험 ${leaky.length}개`));
  }
  box.appendChild(chips);

  if (leaky.length) {
    const w = el("div", "qz-warn err");
    w.appendChild(icon("alert", 15));
    w.appendChild(el("span", null,
      `${leaky.slice(0, 6).map((i) => i.bundle).join(", ")} — provider 가 drive/link/file 인데 `
      + "min_level 이 1 입니다. 링크가 videos.js(정적 파일)에 구워져 누구나 내려받습니다. "
      + "링크 자체가 접근 권한이라 그게 곧 유출입니다 — min_level 을 5 로 두세요."));
    box.appendChild(w);
  }

  const acts = el("div", "qz-foot");
  const mk = el("button", "btn " + (d.exists ? "" : "primary"),
    d.exists ? "빠진 번들 채우기" : "영상 매핑 만들기");
  mk.type = "button";
  mk.addEventListener("click", () => syncYtmap());
  acts.appendChild(mk);
  if (d.exists) {
    const open = el("button", "btn", "매핑 파일 열기");
    open.type = "button";
    open.addEventListener("click", async () => {
      try { await api("/api/publish/ytmap/open", { method: "POST" }); }
      catch (e) { toast(e.message, "err"); }
    });
    acts.appendChild(open);
  }
  acts.appendChild(el("span", "field-hint qz-foot-hint",
    "공유 URL 을 그대로 id 에 붙여넣어도 됩니다 — 빌더가 ID 만 뽑습니다. "
    + "이미 넣은 링크는 다시 눌러도 지워지지 않습니다."));
  box.appendChild(acts);
  if (d.path) box.appendChild(el("pre", "pb-cmd", d.path));

  if (d.extra && d.extra.length) {
    box.appendChild(el("div", "field-hint",
      `매핑에만 있는 번들 ${d.extra.length}개(05/ 에 없음): ${d.extra.slice(0, 8).join(", ")} — `
      + "예전 회차라면 남겨도 되고, 지워도 빌드에 영향이 없습니다."));
  }

  // 번들 표 — 링크 유무와 문항 시작점을 함께 본다.
  const tbl = el("table", "tbl");
  tbl.innerHTML = `<thead><tr><th>번들</th><th>문항</th><th>길이</th>
    <th>링크</th><th>시작</th><th>레벨</th><th>문항 시작점</th></tr></thead>`;
  const tb = el("tbody");
  (d.items || []).forEach((i) => {
    const tr = el("tr", i.id ? "" : "state-todo");
    tr.appendChild(el("td", null, i.bundle));
    tr.appendChild(el("td", "muted", i.label || ""));
    tr.appendChild(el("td", "muted", i.length ? fmtSec(i.length) : "—"));
    const link = el("td");
    link.appendChild(el("span", "status-chip " + (i.id ? "ok" : ""),
      i.id ? (i.provider === "drive" ? "드라이브" : i.provider) : "비어 있음"));
    tr.appendChild(link);
    tr.appendChild(el("td", "muted", i.sec ? fmtSec(i.sec) : "처음"));
    tr.appendChild(el("td", "muted", i.min_level ? String(i.min_level) : "공개"));
    // 문항별 시작 초 — 강사가 "N번은 몇 분" 을 바로 볼 수 있게 펼쳐 둔다.
    const st = el("td", "muted");
    st.textContent = (i.starts || []).map((s) => `${s.number}번 ${fmtSec(s.startSec)}`).join(" · ");
    tr.appendChild(st);
    tb.appendChild(tr);
  });
  tbl.appendChild(tb);
  const wrap = el("div", "tbl-wrap");
  wrap.appendChild(tbl);
  box.appendChild(wrap);

  // 붙여넣기 — 72개를 손으로 넣으면 한 줄 밀려 영상이 엉뚱한 회차에 붙는다.
  const pd = el("details", "pb-paste");
  pd.open = d.empty > 0;
  const sm = el("summary", null, `링크 붙여넣기 (${d.empty}개 비어 있음)`);
  pd.appendChild(sm);
  pd.appendChild(el("div", "field-hint",
    "번들코드와 링크가 같은 줄에 있으면 됩니다 — 파일명·URL·따옴표 섞여도 잡습니다. "
    + "예: m01-1.static.mp4  https://drive.google.com/file/d/1AbC.../view"));
  const ta = el("textarea");
  ta.rows = 8;
  ta.placeholder = "m01-1.static.mp4  https://drive.google.com/file/d/1AbC.../view";
  ta.style.width = "100%";
  pd.appendChild(ta);
  const pb = el("button", "btn primary", "붙여넣은 링크 채우기");
  pb.type = "button";
  pb.addEventListener("click", async () => {
    const text = ta.value.trim();
    if (!text) { toast("붙여넣을 내용이 없습니다."); return; }
    try {
      const r = await api("/api/publish/ytmap/paste", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const bits = [`${r.matched.length}개 채움`];
      if (r.overwrote?.length) bits.push(`${r.overwrote.length}개 교체`);
      if (r.unknown?.length) bits.push(`모르는 번들 ${r.unknown.length}개`);
      if (r.skipped?.length) bits.push(`건너뜀 ${r.skipped.length}줄`);
      toast(bits.join(" · "), r.matched.length ? "" : "err");
      await refresh();
    } catch (e) { toast("채우지 못했습니다: " + e.message, "err"); }
  });
  pd.appendChild(pb);
  box.appendChild(pd);

  box.appendChild(el("div", "field-hint",
    "★ 문항 시작점은 review.json 에서 계산한 값입니다(영상 시간축 기준). "
    + "지금 웹은 번들 하나에 시작점 하나(sec)만 씁니다 — 문항별로 뛰려면 "
    + "웹·빌더 스키마를 늘려야 합니다(추후)."));
}

async function syncYtmap() {
  try {
    const r = await api("/api/publish/ytmap/sync", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: P.ytmap?.provider || "drive" }),
    });
    toast(r.added?.length ? `번들 ${r.added.length}개를 추가했습니다.` : "이미 다 있습니다.");
    await refresh();
  } catch (e) {
    toast("매핑을 만들지 못했습니다: " + e.message, "err");
  }
}

/* ── ③ 빌드 ────────────────────────────────────────── */
function renderBuild() {
  const box = $("#pb-build");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const e = P.env;
  if (!e) { box.appendChild(el("div", "empty", "빌드 환경을 확인할 수 없습니다.")); return; }

  const chips = el("div", "vd-env");
  const chip = (ok, text, title) => {
    const c = el("span", "status-chip " + (ok ? "ok" : "bad"));
    c.appendChild(icon(ok ? "check" : "alert", 13));
    c.appendChild(el("span", null, text));
    if (title) c.title = title;
    return c;
  };
  chips.appendChild(chip(e.cloned, "axexam 클론됨", e.script));
  // ★ 이 배지는 '없어도 정상' 이다. 경고(빨강)로 두면 매번 뭔가 잘못된 것처럼 보인다.
  //
  //   상류 빌더는 `--youtube-map` 플래그가 없고, 대신 `--pd` 로
  //   `data/youtube_map.<pd>.json` 을 스스로 고른다(더 나은 방식이라 그대로 쓴다).
  //   그래서 '미적용' 이 맞는 상태다 — 옆의 youtube_map.<pd>.json 배지가 실제 상태다.
  chips.appendChild(chip(true,
    e.patch_youtube_map ? "--youtube-map 플래그 있음" : "품목별 매핑 (--pd 로 자동 선택)",
    e.patch_youtube_map
      ? "빌더가 그 플래그를 받아 명령에 넣습니다."
      : "상류 빌더는 --pd 로 data/youtube_map.<pd>.json 을 스스로 고릅니다. "
        + "플래그가 없는 것이 정상이며, 품목별로 갈려 SQLD 와 겹치지 않습니다."));
  chips.appendChild(chip(e.youtube_map_exists, `youtube_map.${e.pd}.json`, e.youtube_map));
  box.appendChild(chips);

  if (!e.cloned) {
    const warn = el("div", "qz-warn err");
    warn.appendChild(icon("alert", 15));
    warn.appendChild(el("span", null,
      `axexam 저장소가 없습니다. 다음을 실행하세요:\n`
      + `git clone https://github.com/leedonwoo2827-ship-it/axexam "${e.axexam}"`));
    box.appendChild(warn);
  }

  // ★ 품목 코드가 없으면 명령 자체를 만들지 않는다. 상수로 되돌리면 엉뚱한 품목을 덮어쓴다.
  if (e.pd_ok === false) {
    const warn = el("div", "qz-warn err");
    warn.appendChild(icon("alert", 15));
    warn.appendChild(el("span", null, e.pd_error || "품목 코드(pd)가 정해지지 않았습니다."));
    box.appendChild(warn);
    const go = el("button", "btn sm", "작업 폴더 열기");
    go.type = "button";
    go.addEventListener("click", () => { location.hash = "#/books"; });
    box.appendChild(go);
    return;
  }

  // ★ 실행할 명령을 그대로 보여준다. --book 과 --pd 가 눈에 보여야 한다.
  box.appendChild(el("div", "qz-label", "실행할 명령"));
  const cmd = el("pre", "pb-cmd", e.command);
  box.appendChild(cmd);
  const note = el("div", "field-hint");
  note.innerHTML = "★ <b>--book</b> 과 <b>--pd</b> 는 항상 명시합니다. 둘 다 기본값이 "
    + "SQLD 라서, 하나라도 빠지면 라이브 SQLD 문제은행을 덮어씁니다.";
  box.appendChild(note);

  const acts = el("div", "qz-foot");
  const btn = el("button", "btn primary", "빌드 실행");
  btn.type = "button";
  btn.disabled = !e.cloned;
  btn.addEventListener("click", () => startBuild(false));
  acts.appendChild(btn);
  acts.appendChild(el("span", "field-hint qz-foot-hint",
    `출력: ${e.out}  ·  problems.json: ${e.problems_json}`));
  box.appendChild(acts);

  const prog = el("div");
  prog.id = "pb-build-prog";
  box.appendChild(prog);
  const log = el("pre", "log-pane");
  log.id = "pb-build-log";
  log.hidden = true;
  box.appendChild(log);
}

async function startBuild(force) {
  const e = P.env;
  const ok = await confirmModal({
    title: "이 명령으로 빌드할까요?",
    body: `<pre class="pb-cmd">${escapeHtml(e.command)}</pre>`
      + `<br>품목 <b>${escapeHtml(e.pd)}</b> · BOOK <b>${escapeHtml(e.book)}</b><br><br>`
      + "이 두 값이 맞는지 확인하세요. 잘못된 pd 로 빌드하면 다른 품목의 문제은행을 "
      + "덮어쓰게 되고 되돌릴 수 없습니다.",
    ok: "빌드 실행", cancel: "취소",
  });
  if (!ok) return;

  try {
    const job = await api("/api/publish/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force_ignore_warnings: !!force }),
    });
    attachBuild(job.id);
  } catch (err) {
    if (err.status === 409) {
      const again = await confirmModal({
        title: "빌드를 시작하지 않았습니다",
        body: `<pre class="pb-cmd">${escapeHtml(err.message)}</pre>`
          + (err.message.includes("경고")
            ? "<br>경고만 남았다면 확인 후 진행할 수 있습니다."
            : "<br>오류는 우회할 수 없습니다. 먼저 고치세요."),
        ok: err.message.includes("경고") ? "경고 무시하고 진행" : "닫기",
        cancel: err.message.includes("경고") ? "취소" : "",
      });
      if (again && err.message.includes("경고")) return startBuild(true);
    } else {
      toast("빌드를 시작하지 못했습니다: " + err.message, "err");
    }
  }
}

function attachBuild(jobId) {
  const log = $("#pb-build-log");
  log.hidden = false;
  log.textContent = "";
  if (P.polling) return;
  P.polling = true;
  pollJob(jobId, (job) => {
    renderBuildProgress(job);
    const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 24;
    (job.log?.lines || []).forEach((line) => {
      const cls = /ERROR|\[error\]|FAIL/.test(line) ? "lv-err"
        : /\[warn\]|warn /.test(line) ? "lv-warn"
        : /OK  |\[done\]/.test(line) ? "lv-ok" : "";
      log.appendChild(el("span", cls, line + "\n"));
    });
    if (atBottom) log.scrollTop = log.scrollHeight;
  }).then(async (final) => {
    P.polling = false;
    if (final) {
      const bad = final.status === "error";
      toast(bad ? `빌드 종료 — ${final.error || "검증 실패"}` : "빌드를 마쳤습니다.",
        bad ? "err" : "");
    }
    fireJobChanged({ id: jobId });
    await refresh();
  });
}

function renderBuildProgress(job) {
  const box = $("#pb-build-prog");
  if (!box) return;
  box.innerHTML = "";
  const labels = { build: "build_check.py 실행", assert: "리포트 어서션", problems: "problems.json 검증" };
  ["build", "assert", "problems"].forEach((k, i) => {
    const it = (job.items || {})[k] || {};
    const cls = it.status === "done" ? "done" : it.status === "running" ? "on"
      : it.status === "error" ? "err" : "";
    const row = el("div", "pb-step " + cls);
    row.appendChild(el("span", "n", String(i + 1)));
    const mid = el("div");
    mid.appendChild(el("span", null, labels[k]));
    if (it.error) mid.appendChild(el("div", "muted", it.error));
    row.appendChild(mid);
    box.appendChild(row);
  });
  (job.asserts || []).forEach((a) => {
    const row = el("div", "pb-check");
    const item = el("div", "item " + (a.ok ? "ok" : "err"));
    item.appendChild(icon(a.ok ? "check" : "alert", 13));
    const mid = el("div");
    mid.appendChild(el("span", null, a.label));
    if (a.detail && !a.ok) mid.appendChild(el("div", "muted", a.detail));
    item.appendChild(mid);
    item.appendChild(el("span", "muted", a.ok ? "" : "실패"));
    row.appendChild(item);
    box.appendChild(row);
  });
}

/* ── ③ problems.json ──────────────────────────────── */
function renderProblems() {
  const box = $("#pb-problems");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  renderPartial(box);
  const d = P.problems;
  if (!d) { box.appendChild(el("div", "empty", "확인할 수 없습니다.")); return; }

  const chips = el("div", "vd-env");
  const add = (ok, text, title) => {
    const c = el("span", "status-chip " + (ok ? "ok" : "bad"), text);
    if (title) c.title = title;
    chips.appendChild(c);
  };
  if (!d.count) {
    box.appendChild(el("div", "empty",
      d.errors?.[0] || "problems.json 이 아직 없습니다. ② 빌드를 먼저 실행하세요."));
    return;
  }
  add(d.pd_id === (P.env?.pd), `pd_id = ${d.pd_id}`);
  add(d.count === 240, `문항 ${d.count}`);
  add(d.rounds === 3, `회차 ${d.rounds}`);
  add(d.subjects === 4, `과목 ${d.subjects}`, (d.subject_list || []).join("  "));
  chips.appendChild(el("span", "status-chip", fmtBytes(d.bytes)));
  box.appendChild(chips);

  const list = el("div", "pb-check");
  (d.errors || []).forEach((t) => {
    const row = el("div", "item err");
    row.appendChild(icon("alert", 13));
    row.appendChild(el("div", null, t));
    row.appendChild(el("span", "muted", "오류"));
    list.appendChild(row);
  });
  (d.warnings || []).forEach((t) => {
    const row = el("div", "item warn");
    row.appendChild(icon("bulb", 13));
    row.appendChild(el("div", null, t));
    row.appendChild(el("span", "muted", "경고"));
    list.appendChild(row);
  });
  if (!list.childElementCount) {
    const row = el("div", "item ok");
    row.appendChild(icon("check", 13));
    row.appendChild(el("div", null, "검증을 모두 통과했습니다."));
    row.appendChild(el("span"));
    list.appendChild(row);
  }
  box.appendChild(list);

  const exp = d.expected_report || {};
  const note = el("div", "field-hint");
  note.textContent = `임포트 리포트 기대값 — 신규 ${exp.new} · 갱신 ${exp.updated} · `
    + `변경없음 ${exp.unchanged} · 건너뜀 ${exp.skipped_edited} · 실패 ${exp.failed} · `
    + `회차 ${exp.rounds}행`;
  box.appendChild(note);
}

/* ── ④-b 부분 임포트 ─────────────────────────────────
 *
 * ★ 임포트는 DELETE 를 하지 않는다(problem.php:13) — 기존 행은 UPDATE 만 한다.
 *   그래서 고친 문항만 담아 올려도 나머지는 서버에 그대로 남는다.
 *
 *   용량(714KB → 2.6KB)보다 **확인**이 이득이다. 전체를 올리면 리포트가
 *   "갱신 1 · 변경없음 719" 로 나와서 내가 고친 것이 들어갔는지 알기 어렵다.
 */
async function renderPartial(box) {
  if (!box) return;
  let d = null;
  try { d = await api("/api/publish/partial"); } catch (e) { return; }

  const wrap = el("details", "pb-partial");
  wrap.appendChild(el("summary", null,
    `부분 임포트 — 고친 것만 올리기 (전체 ${d.total}문항 · ${Math.round(d.bytes / 1024)}KB)`));
  wrap.appendChild(el("div", "field-hint",
    "임포트는 없는 문항을 지우지 않습니다 — 고친 회차·번들·문항만 담아 올리면 "
    + "나머지는 서버에 그대로 남습니다. 리포트가 '갱신 N' 만 찍혀 확인이 쉬워집니다."));

  const row = el("div", "qz-foot");
  const sel = el("select");
  Object.entries(d.rounds || {}).forEach(([rd, n]) => {
    const o = el("option", null, `${rd}회 (${n}문항)`);
    o.value = "r:" + rd;
    sel.appendChild(o);
  });
  Object.keys(d.bundles || {}).forEach((b) => {
    const o = el("option", null, `${b} (${d.bundles[b]}문항 · 영상 1편)`);
    o.value = "b:" + b;
    sel.appendChild(o);
  });
  row.appendChild(sel);

  const key = el("input");
  key.placeholder = "또는 문항 키 — m04-2#12 (쉼표로 여러 개)";
  key.style.minWidth = "250px";
  row.appendChild(key);

  const out = el("pre", "pb-cmd");
  out.hidden = true;

  const mk = el("button", "btn", "부분 파일 만들기");
  mk.type = "button";
  mk.addEventListener("click", async () => {
    const body = {};
    const ks = key.value.split(",").map((x) => x.trim()).filter(Boolean);
    if (ks.length) body.keys = ks;
    else if (sel.value.startsWith("r:")) body.rounds = [Number(sel.value.slice(2))];
    else if (sel.value.startsWith("b:")) body.bundles = [sel.value.slice(2)];
    try {
      const r = await api("/api/publish/partial", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      toast(`${r.picked}문항 · ${Math.round(r.bytes / 1024)}KB`);
      out.textContent = r.path + "\n기대 리포트: " + r.expect
        + "\n★ skip_edited 가 0 인지 확인하세요 — 0 이 아니면 그 문항을 전에 웹에서 "
        + "고친 것입니다(problem.php:18). 관리자 화면에서 '원본 복원' 을 누른 뒤 "
        + "다시 임포트해야 로컬 수정이 들어갑니다.";
      out.hidden = false;
    } catch (e) { toast(e.message, "err"); }
  });
  row.appendChild(mk);
  wrap.appendChild(row);
  wrap.appendChild(out);
  box.appendChild(wrap);
}

/* ── ⑤ 업로드 — 폴더 하나로 끝낸다 ────────────────────────────
 *
 * ★ 왜 파일 목록이 아니라 폴더를 만드는가
 *
 *   올릴 것이 로컬 두 곳에서 서버 세 곳으로 간다:
 *     06/              → /www/exam/
 *     axexam/web/exam/ → /www/exam/   (같은 자리에 섞인다)
 *     axexam/web/adm/  → /www/adm/    (/exam/ 밖!)
 *   이 매핑을 머릿속으로 하면서 FileZilla 를 쓰면 반드시 틀리고, **틀려도 업로드는
 *   성공한 것처럼 보인다** — 웹에서 증상이 엉뚱한 얼굴로 나타날 뿐이다.
 *
 *   그래서 앱이 서버와 똑같은 모양의 폴더(`_upload/`)를 만든다. 왼쪽에 그 폴더,
 *   오른쪽에 /www/ 를 놓고 통째로 끌어놓으면 끝. 다 올리면 [지우기].
 */
async function renderStage() {
  const box = $("#pb-ftp");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  let st = null;
  try { st = await api("/api/publish/stage"); } catch (e) { /* 아래에서 처리 */ }

  const head = el("div", "field-hint");
  head.innerHTML = "왼쪽(로컬)에 <b>업로드 폴더</b>, 오른쪽(서버)에 <b>/www/</b> 를 놓고 "
    + "통째로 끌어놓으세요. 폴더 안이 이미 서버와 같은 모양입니다 — "
    + "<b>어디로 갈지 생각할 것이 없습니다.</b>";
  box.appendChild(head);

  // ★ 빌드보다 낡았으면 크게 알린다. 파일 수만 보면 그럴듯해서 사람이 못 알아챈다 —
  //   실제로 빌드 10:21 · 폴더 08:58 인 채로 "다 만들어졌다" 로 보였고,
  //   그대로 올리면 새 videos.private.json 이 빠진다.
  if (st?.exists && st.stale) {
    const w = el("div", "qz-warn err");
    w.appendChild(icon("alert", 15));
    w.appendChild(el("span", null, st.stale_text
      || "빌드가 이 폴더보다 새롭습니다 — 다시 만드세요."));
    box.appendChild(w);
  }

  const acts = el("div", "qz-foot");
  const mk = el("button", "btn primary",
    st?.exists ? (st.stale ? "★ 업로드 폴더 다시 만들기 (빌드가 더 새롭습니다)"
                           : "업로드 폴더 다시 만들기")
               : "업로드 폴더 만들기");
  mk.type = "button";
  mk.addEventListener("click", async () => {
    try {
      const r = await api("/api/publish/stage", { method: "POST" });
      toast(`${r.files}개 · ${(r.bytes / 1048576).toFixed(2)}MB — ${r.dir}`);
      await renderStage();
    } catch (e) { toast(e.message, "err"); }
  });
  acts.appendChild(mk);

  if (st?.exists) {
    const open = el("button", "btn", "폴더 열기");
    open.type = "button";
    open.addEventListener("click", async () => {
      try { await api("/api/publish/stage/open", { method: "POST" }); }
      catch (e) { toast(e.message, "err"); }
    });
    acts.appendChild(open);

    const del = el("button", "btn", "다 올렸습니다 — 지우기");
    del.type = "button";
    del.addEventListener("click", async () => {
      if (!(await confirmModal({
        title: "업로드 폴더를 지울까요?",
        body: "서버에 다 올렸다면 지워도 됩니다. 남겨 두면 다음에 무엇이 새것인지 "
          + "헷갈립니다. 언제든 다시 만들 수 있습니다.",
        ok: "지우기", cancel: "취소",
      }))) return;
      try {
        await api("/api/publish/stage/clear", { method: "POST" });
        toast("지웠습니다.");
        await renderStage();
      } catch (e) { toast(e.message, "err"); }
    });
    acts.appendChild(del);
  }
  box.appendChild(acts);

  if (st?.exists) {
    box.appendChild(el("div", "qz-label", "왼쪽 = 이 폴더"));
    box.appendChild(el("pre", "pb-cmd", st.dir));
    box.appendChild(el("div", "qz-label", "오른쪽 = 서버"));
    box.appendChild(el("pre", "pb-cmd", "/www/"));
    box.appendChild(el("div", "muted",
      `${st.files}개 · ${(st.bytes / 1048576).toFixed(2)}MB · 최상위: ${(st.tops || []).join("  ")}`));
  }

  box.appendChild(el("div", "field-hint",
    "FileZilla 설정(한 번만): 전송 유형 바이너리 · 동시 전송 2 · 문자셋 UTF-8 강제"
    + "(요약노트 파일명이 한글입니다)."));
  box.appendChild(el("div", "field-hint",
    "★ problems.json 은 이 폴더에 넣지 않았습니다 — 관리자 화면(/adm/exam_import.php)에서 "
    + "올리거나 붙여넣습니다. .htaccess 가 .json 을 403 으로 막아서 FTP 로는 읽히지 않습니다."));
}

/* ── ④ FTP ────────────────────────────────────────── */
function renderFtp() {
  const box = $("#pb-ftp");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const d = P.ftp;
  if (d.error) {
    box.appendChild(el("div", "empty", d.error));
    return;
  }
  box.appendChild(el("div", "muted",
    `${d.out}  →  ${d.site}   ·   파일 ${d.totals.files}개 · ${fmtBytes(d.totals.bytes)}`));

  const grouped = {};
  d.upload.forEach((u) => {
    const top = u.path.includes("/") ? u.path.split("/")[0] + "/" : u.path;
    grouped[top] = grouped[top] || { n: 0, bytes: 0 };
    grouped[top].n += 1;
    grouped[top].bytes += u.bytes;
  });
  const tree = el("div", "pb-tree");
  Object.entries(grouped).forEach(([k, v]) => {
    const row = el("label");
    row.appendChild(icon(k.endsWith("/") ? "folder" : "file", 14));
    row.appendChild(el("span", null, k));
    row.appendChild(el("span", "sz", `${v.n}개 · ${fmtBytes(v.bytes)}`));
    tree.appendChild(row);
  });
  box.appendChild(el("div", "qz-label", "올릴 것"));
  box.appendChild(tree);

  if (d.skip.length) {
    box.appendChild(el("div", "qz-label", "올리지 않을 것"));
    const list = el("div", "pb-check");
    d.skip.forEach((s) => {
      const row = el("div", "item warn");
      row.appendChild(icon("alert", 13));
      const mid = el("div");
      mid.appendChild(el("span", null, s.path + (s.count ? ` (${s.count}개)` : "")));
      mid.appendChild(el("div", "muted", s.reason));
      row.appendChild(mid);
      row.appendChild(el("span", "muted", fmtBytes(s.bytes)));
      list.appendChild(row);
    });
    box.appendChild(list);
  }

  const acts = el("div", "qz-foot");
  const open = el("button", "btn primary", "06/ 폴더 열기 (FileZilla 로 끌어놓기)");
  open.type = "button";
  open.addEventListener("click", openOut);
  acts.appendChild(open);
  acts.appendChild(el("span", "field-hint qz-foot-hint",
    "전송 유형 바이너리 · 동시 전송 2개 이하 · 파일명 인코딩 UTF-8 강제"));
  box.appendChild(acts);
}

async function openOut() {
  try {
    const r = await api("/api/publish/open", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ which: "out" }),
    });
    toast("탐색기에서 열었습니다: " + r.path);
  } catch (e) {
    toast("폴더를 열지 못했습니다: " + e.message, "err");
  }
}

/* ── ⑤ 서버 단계 ──────────────────────────────────── */
function renderServer() {
  const box = $("#pb-server");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const d = P.checklist;
  if (!d) { box.appendChild(el("div", "empty", "체크리스트를 불러올 수 없습니다.")); return; }

  const note = el("div", "field-hint");
  note.textContent = "임포트는 1회용 관리자 토큰을 쓰기 때문에 스크립트로 부를 수 없습니다 — "
    + "브라우저 단계입니다. 서버에서는 이력을 되읽을 수 없으므로(.htaccess 가 .json 을 "
    + "403 으로 막습니다) 이 로컬 기록이 유일한 발행 이력입니다.";
  box.appendChild(note);

  d.items.forEach((it, i) => {
    const st = (d.state || {})[it.key] || {};
    const card = el("div", "pb-step " + (st.done ? "done" : ""));
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = !!st.done;
    cb.addEventListener("change", async () => {
      try {
        const r = await api("/api/publish/checklist", {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: it.key, done: cb.checked }),
        });
        d.state = r.state;
        card.classList.toggle("done", cb.checked);
        toast(cb.checked ? `완료로 기록했습니다 — ${it.label}` : "기록을 해제했습니다.");
      } catch (e) { toast("기록 실패: " + e.message, "err"); }
    });
    card.appendChild(cb);
    const mid = el("div");
    mid.appendChild(el("b", null, `${i + 1}. ${it.label}`));
    mid.appendChild(el("div", "muted", `${it.where} — ${it.detail}`));
    if (it.sql) {
      const btn = el("button", "btn sm", "SQL 보기");
      btn.type = "button";
      btn.addEventListener("click", () => confirmModal({
        title: it.label,
        body: `<pre class="pb-cmd">${escapeHtml(it.sql)}</pre>`,
        ok: "닫기", cancel: "",
      }));
      mid.appendChild(btn);
    }
    if (st.at) mid.appendChild(el("div", "muted", `기록 ${st.at}`));
    card.appendChild(mid);
    box.appendChild(card);
  });
}
