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

const P = { pre: null, env: null, problems: null, ftp: null, checklist: null, polling: false };

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
    <div class="card"><div class="card-title">② 빌드 — axexam scripts/build_check.py</div>
      <div id="pb-build"></div></div>
    <div class="card"><div class="card-title">③ problems.json 검증 (임포트 드라이런)</div>
      <div id="pb-problems"></div></div>
    <div class="card"><div class="card-title">④ FTP 업로드 목록</div><div id="pb-ftp"></div></div>
    <div class="card"><div class="card-title">⑤ 서버 단계 — 여기서부터는 사람이 합니다</div>
      <div id="pb-server"></div></div>
  `;
  root.appendChild(page);
  hydrateIcons(page);
  await refresh();
}

async function refresh() {
  const set = (id, msg) => { const b = $(id); if (b) b.innerHTML = `<div class="empty">${msg}</div>`; };
  set("#pb-pre", "점검 중…");
  const results = await Promise.allSettled([
    api("/api/publish/preflight"),
    api("/api/publish/env"),
    api("/api/publish/problems"),
    api("/api/publish/ftplist"),
    api("/api/publish/checklist"),
  ]);
  const [pre, env, problems, ftp, checklist] = results;
  P.pre = pre.status === "fulfilled" ? pre.value : { error: pre.reason?.message };
  P.env = env.status === "fulfilled" ? env.value : null;
  P.problems = problems.status === "fulfilled" ? problems.value : null;
  P.ftp = ftp.status === "fulfilled" ? ftp.value : { error: ftp.reason?.message };
  P.checklist = checklist.status === "fulfilled" ? checklist.value : null;

  renderPre();
  renderBuild();
  renderProblems();
  renderFtp();
  renderServer();
}

/* ── ① 사전점검 ────────────────────────────────────── */
function renderPre() {
  const box = $("#pb-pre");
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

/* ── ② 빌드 ────────────────────────────────────────── */
function renderBuild() {
  const box = $("#pb-build");
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
  chips.appendChild(chip(e.patch_youtube_map, "--youtube-map 패치",
    e.patch_youtube_map ? "적용됨"
      : "미적용 — 공용 youtube_map.json 을 쓰면 SQLD 의 번들 키와 겹칩니다."));
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
  box.innerHTML = "";
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

/* ── ④ FTP ────────────────────────────────────────── */
function renderFtp() {
  const box = $("#pb-ftp");
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
