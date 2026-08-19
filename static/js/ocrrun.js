/* OCR 실행 — PDF 를 고르고 돌리고, 로그가 **아래로 흐른다.**
 *
 * ★ 왜 패널이 아니라 바탕인가. 판독은 장당 40~60초, 151장이면 두 시간이다. 부유 패널은
 *   Esc·스크림 클릭으로 닫히고 닫히면 마크업이 사라진다 — 두 시간을 흘릴 표면이 못 된다.
 *   그리고 사람이 원한 모양이 「실행 누르면 밑으로 쭈욱」이다(2026-08-18 지시).
 *
 * ★ 왜 확인 모달이 아닌가. 모달 안에서는 로그가 흐를 자리가 없다. 고르는 것과 흐르는 것이
 *   한 화면에 있어야 "지금 무엇이 돌고 있나" 를 눈으로 잇는다.
 *
 * 두 단계를 한 화면에 둔다:
 *     ① 스캔 뜨기   00/*.pdf → data/raw_pages/   (품목당 한 번)
 *     ② 판독        raw_pages → data/ocr_draft/  (회차마다)
 *   ②는 ①이 끝나야 할 일이 생긴다. 그래서 위아래로 둔다.
 */
"use strict";

import { $, api, el, toast } from "./util.js";
import { pollJob } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const R = { plan: null, over: null, live: false };

export const meta = {
  title: () => "OCR 실행",
  subtitle: () => "PDF 를 고르고 [실행] 을 누르면 아래로 진행이 흐릅니다.",
  actions: () => [
    actionBtn("OCR 검수로", () => (location.hash = "#/ocr"), { iconName: "folder" }),
    actionBtn("새로고침", () => load(), { iconName: "refresh" }),
  ],
};

export async function mount(root) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card">
      <div class="card-title">① 스캔 뜨기 — 00/ 의 PDF 를 페이지 이미지로</div>
      <div id="or-render"><div class="empty">불러오는 중…</div></div>
    </div>
    <div class="card">
      <div class="card-title">② 판독 — 스캔을 읽어 초안으로</div>
      <div id="or-read"><div class="empty">불러오는 중…</div></div>
    </div>
    <div class="card" id="or-logcard" hidden>
      <div class="card-title">진행</div>
      <div class="vd-env" id="or-head"></div>
      <pre class="log-pane" id="or-log" style="max-height:52vh"></pre>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);
  await load();
}

async function load() {
  try {
    [R.plan, R.over] = await Promise.all([
      api("/api/ocr/render/plan"), api("/api/ocr/overview"),
    ]);
  } catch (e) {
    const b = $("#or-render");
    if (b) { b.innerHTML = ""; b.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message)); }
    return;
  }
  renderStep1();
  renderStep2();
}

/* ── ① 스캔 뜨기 ─────────────────────────────────────────────────────── */
function renderStep1() {
  const box = $("#or-render");
  if (!box) return;
  box.innerHTML = "";
  const p = R.plan || {};
  if (!p.exists) {
    box.appendChild(el("div", "empty", p.error || "00/ 에 PDF 가 없습니다."));
    return;
  }
  box.appendChild(el("pre", "pb-cmd", p.pdf_dir || ""));

  const done = new Set((R.over?.info?.srcs || []).map((s) => String(s.src)));
  const rows = el("div");
  const picks = new Map();
  for (const it of p.items || []) {
    const row = el("label", "or-row");
    const cb = el("input");
    cb.type = "checkbox";
    // ★ **기본은 켠 상태**다(2026-08-18 지시: "기본적으로 OCR을 체크하게 해줘..
    //   누르면 다 스캔했습니다 뜨겠지뭐"). 꺼 두면 처음 온 사람이 왜 아무 일도
    //   안 일어나는지 모른다 — 이미 뜬 소스는 서버가 건너뛰므로 켜 둬도 해가 없다.
    cb.checked = true;
    picks.set(it.src, cb);
    row.append(cb, el("b", null, it.file || it.src));
    row.appendChild(el("span", "muted",
      `→ ${it.src}/` + (it.role ? ` · ${it.role}` : "")
      + (done.has(String(it.src)) ? " · 이미 뜸" : "")));
    if (it.dup_of) row.appendChild(el("span", "status-chip warn", `중복 — ${it.dup_of} 과 같음`));
    rows.appendChild(row);
  }
  box.appendChild(rows);

  const foot = el("div", "qz-foot");
  const btn = el("button", "btn primary", "스캔 뜨기 실행");
  btn.type = "button";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    logLine("[스캔] 시작합니다 — 이미 뜬 소스는 건너뜁니다.");
    try {
      const r = await api("/api/ocr/render", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      (r.log || []).forEach((l) => logLine(l.trimEnd()));
      logLine(`[스캔] 끝 — ${r.pages}페이지`);
      toast(`스캔 ${r.pages}페이지를 떴습니다.`);
      await load();
    } catch (e) {
      logLine("[스캔] 실패 — " + e.message);
      toast("스캔을 뜨지 못했습니다: " + e.message, "err");
    } finally {
      btn.disabled = false;
    }
  });
  foot.appendChild(btn);
  foot.appendChild(el("span", "field-hint qz-foot-hint",
    "품목당 한 번이면 됩니다. 내용이 같은 중복 PDF 는 건너뜁니다."));
  box.appendChild(foot);
}

/* ── ② 판독 ──────────────────────────────────────────────────────────── */
function renderStep2() {
  const box = $("#or-read");
  if (!box) return;
  box.innerHTML = "";
  const pages = R.over?.pages || [];
  if (!pages.length) {
    box.appendChild(el("div", "empty", "뜬 스캔이 없습니다. 위 ① 을 먼저 하세요."));
    return;
  }

  // 소스별로 묶는다. 이어지는 면(문항 0개가 정상인 면)은 할 일에서 뺀다.
  const g = new Map();
  for (const p of pages) {
    if (!g.has(p.src)) g.set(p.src, { all: [], todo: [] });
    const e = g.get(p.src);
    e.all.push(p);
    if (!p.n_questions && !p.continuation) e.todo.push(p.page);
  }

  const picks = new Map();
  const rows = el("div");
  for (const [src, e] of g) {
    const row = el("label", "or-row");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = true;          // 기본 켬 — 할 일이 없으면 눌렀을 때 알려 준다
    picks.set(src, cb);
    const name = (R.over?.info?.srcs || []).find((s) => String(s.src) === String(src));
    row.append(cb, el("b", null, `${src}.pdf`));
    if (e.todo.length) {
      const lo = e.todo[0], hi = e.todo[e.todo.length - 1];
      row.appendChild(el("span", null,
        `미판독 ${e.todo.length}장 (p.${lo}~${hi}) · 전체 ${e.all.length}장`));
      row.appendChild(el("span", "muted",
        `· 대략 ${Math.max(1, Math.round(e.todo.length * 45 / 60))}분`));
    } else {
      row.appendChild(el("span", "muted", `전체 ${e.all.length}장 · 다 읽었습니다`));
    }
    rows.appendChild(row);
  }
  box.appendChild(rows);

  const total = [...g.values()].reduce((n, e) => n + e.todo.length, 0);
  const foot = el("div", "qz-foot");
  const btn = el("button", "btn primary",
    total ? `판독 실행 (${total}장)` : "판독 실행");
  btn.type = "button";
  // ★ 0장이어도 **누를 수 있게** 둔다. 비활성 버튼은 이유를 말해 주지 않는다 —
  //   누르면 "다 읽었습니다" 가 뜨는 편이 낫다. 돌고 있을 때만 막는다.
  btn.disabled = R.live;
  btn.addEventListener("click", async () => {
    const srcs = [...picks.entries()].filter(([, c]) => c.checked).map(([s]) => s);
    if (!srcs.length) { toast("고른 PDF 가 없습니다."); return; }
    if (!total) {
      toast("판독할 페이지가 없습니다 — 이미 다 읽었습니다.");
      logLine("[판독] 할 일이 없습니다 — 151장 모두 읽혀 있습니다.");
      return;
    }
    // 잡은 동시에 하나만 — 고른 것 중 첫 소스를 돌리고, 끝나면 다시 누르면 된다.
    await startRead(srcs[0], srcs.length > 1 ? srcs.slice(1) : []);
  });
  foot.appendChild(btn);
  foot.appendChild(el("span", "field-hint qz-foot-hint",
    "한 장에 40~60초입니다. 이미 판독된 페이지와 '이어짐' 면은 건너뜁니다. "
    + "중간에 창을 닫아도 서버에서 계속 돌고, 읽은 페이지는 남습니다."));
  box.appendChild(foot);
}

/* ── 진행 · 로그 ─────────────────────────────────────────────────────── */
function logCard() {
  const c = $("#or-logcard");
  if (c) c.hidden = false;
  return $("#or-log");
}

function logLine(text) {
  const pre = logCard();
  if (!pre) return;
  pre.appendChild(el("span", null, text + "\n"));
  pre.scrollTop = pre.scrollHeight;      // 밑으로 쭈욱
}

async function startRead(src, rest) {
  let job;
  try {
    job = await api("/api/ocr/read", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src }),
    });
  } catch (e) {
    toast("판독을 시작하지 못했습니다: " + e.message, "err");
    logLine("[판독] 시작 실패 — " + e.message);
    return;
  }
  R.live = true;
  renderStep2();
  logLine(`[판독] ${src}.pdf 시작 — ${job.total_count || "?"}장`);

  const head = $("#or-head");
  const badge = el("span", "status-chip", "진행 중");
  const clock = el("span", "status-chip info", "0:00");
  const prog = el("span", "status-chip", "");
  if (head) { head.innerHTML = ""; head.append(badge, clock, prog); }

  const t0 = Date.now();
  const iv = setInterval(() => {
    const v = Math.floor((Date.now() - t0) / 1000);
    clock.textContent = `${Math.floor(v / 60)}:${String(v % 60).padStart(2, "0")}`;
  }, 1000);

  // ★ 로그는 pollJob 이 커서를 관리한다 — 받은 줄만 붙인다(안 그러면 매 틱 중복).
  const final = await pollJob(job.id, (j) => {
    prog.textContent = `${j.done_count || 0} / ${j.total_count || 0}`
      + (j.current ? ` · ${j.current}` : "");
    (j.log?.lines || []).forEach((l) => logLine(l.trimEnd()));
  });
  clearInterval(iv);
  R.live = false;
  badge.textContent = final?.status === "error" ? "오류" : "완료";
  badge.className = "status-chip " + (final?.status === "error" ? "err" : "ok");
  const r = final?.result || {};
  if (r.questions != null) logLine(`[판독] 끝 — ${r.pages}장 · ${r.questions}문항`);
  toast(final?.status === "error" ? "판독이 중단됐습니다." : "판독을 마쳤습니다.",
    final?.status === "error" ? "err" : "");
  await load();
  // 고른 소스가 더 있으면 이어서 — 잡이 하나씩만 돌기 때문이다.
  if (rest && rest.length) {
    logLine(`[판독] 다음 소스 ${rest[0]}.pdf 로 이어갑니다.`);
    await startRead(rest[0], rest.slice(1));
  }
}
