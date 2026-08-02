/* 셸 — 2층 해시 라우터, 좌측 레일(접기), 최근 작업, 전역 단축키
 *
 * 라우터가 2층인 이유: 사전점검·잡 로그·HTML 미리보기는 작업 본문 위에 뜨는 부유
 * 패널이다. 패널을 열고 닫아도 베이스는 언마운트되지 않으므로, 24번들 렌더(최대
 * 두 시간)의 2초 폴링과 문항 에디터의 미저장 텍스트가 살아 있다.
 *
 *   layer "base"  → #view 를 갈아치운다  (/questions /video /publish /summary)
 *   layer "panel" → 패널을 띄운다        (/precheck/:code /job/:id /preview/:key)
 */
"use strict";

import { $, $$, el, toast } from "./util.js";
import { getBook, getJobs, getVersion } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { openPanel, closePanel, isOpen as panelOpen, setCloseHandler, setActions } from "./panel.js";

const view = $("#view");

/* ── 라우트 테이블 ──────────────────────────────────
 * 일하는 화면은 전부 바탕(base)이다. 패널은 "보고 닫는" 표면만 맡는다 —
 * 미저장 텍스트를 든 화면을 패널에 두면 Esc·스크림 클릭에 편집이 날아간다.
 */
const routes = [
  // 바탕(아래층) — 실제로 일하는 화면
  { re: /^\/home$/,             nav: "",   layer: "base",  load: () => import("./home.js") },
  { re: /^\/scan\/(.+)$/,       nav: "sc", layer: "base",  load: () => import("./scan.js") },
  { re: /^\/questions\/(.+)$/,  nav: "q",  layer: "base",  load: () => import("./questions.js") },
  { re: /^\/video\/(.+)$/,      nav: "v",  layer: "base",  load: () => import("./video.js") },
  // 일괄 렌더의 진행·터미널. 목록(패널)에서 시작하면 여기로 온다 — 작업은 바탕에서.
  { re: /^\/render\/(.+)$/,     nav: "v",  layer: "base",  load: () => import("./video.js") },
  { re: /^\/publish$/,          nav: "p",  layer: "base",  load: () => import("./publish.js") },
  { re: /^\/summary$/,          nav: "s",  layer: "base",  load: () => import("./summary.js") },
  { re: /^\/summary\/(.+)$/,    nav: "s",  layer: "base",  load: () => import("./summary.js") },

  // 부유 패널(위층) — 고르는 곳
  { re: /^\/books$/,     nav: "",   layer: "panel", group: "books",     load: () => import("./books.js") },
  { re: /^\/scan$/,      nav: "sc", layer: "panel", group: "scan",      load: () => import("./scan.js") },
  { re: /^\/questions$/, nav: "q",  layer: "panel", group: "questions", load: () => import("./questions.js") },
  { re: /^\/video$/,     nav: "v",  layer: "panel", group: "video",     load: () => import("./video.js") },

  { re: /^\/precheck\/(.+)$/, nav: "v", layer: "panel", group: "video",   load: () => import("./video.js") },
  { re: /^\/job\/(.+)$/,      nav: "v", layer: "panel", group: "video",   load: () => import("./video.js") },
  { re: /^\/preview\/(.+)$/,  nav: "s", layer: "panel", group: "summary", load: () => import("./summary.js") },
];

const HOME = routes[0];   // 바헉의 기본 — 패널을 지우면 여기로 돌아온다

function parseHash() {
  const raw = (location.hash || "#/home").slice(1) || "/home";
  const [path, qs] = raw.split("?");
  const params = new URLSearchParams(qs || "");
  for (const rt of routes) {
    const m = path.match(rt.re);
    if (m) return { path, rt, args: m.slice(1).map(decodeURIComponent), params };
  }
  return { path: "/home", rt: HOME, args: [], params };
}

let baseToken = 0;      // 레이어별로 취소 토큰을 따로 둬야 경쟁 상태가 안 생긴다
let panelToken = 0;
let basePath = null;

export function navigate(path) {
  if (location.hash === "#" + path) render();
  else location.hash = path;
}

/* ── 렌더 ─────────────────────────────────────────── */
async function render() {
  const { path, rt, args, params } = parseHash();
  $$("#side-nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === rt.nav));

  if (rt.layer === "panel") {
    if (!basePath) await mountBase(HOME, "/home", [], new URLSearchParams());
    await mountPanel(rt, path, args, params);
    return;
  }

  if (panelOpen()) closePanel();

  // 이미 이 화면이 바탕에 떠 있으면 다시 마운트하지 않는다.
  // 이게 2층 구조의 존재 이유다 — 재마운트하면 폴링과 입력이 날아간다.
  if (path === basePath && view.firstElementChild) {
    view.focus({ preventScroll: true });
    return;
  }
  await mountBase(rt, path, args, params);
}

async function mountBase(rt, path, args, params) {
  const token = ++baseToken;
  view.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    const mod = await rt.load();
    if (token !== baseToken) return;
    view.innerHTML = "";
    basePath = path;
    const ctx = { args, params, path, navigate };
    await mod.mount(view, ctx);
    // 제목·부제·액션 줄은 셸이 만든다. 패널에서든 바탕에서든 같은 계약이라
    // 화면을 다른 레이어로 옮겨도 모듈을 고칠 필요가 없다.
    if (mod.meta) applyBaseHead(mod, ctx);
  } catch (e) {
    console.error(e);
    if (token !== baseToken) return;
    view.innerHTML = "";
    basePath = path;
    view.appendChild(el("div", "empty", "화면을 불러오지 못했습니다: " + e.message));
  }
  view.focus({ preventScroll: true });
  window.scrollTo({ top: 0 });
}

async function mountPanel(rt, path, args, params) {
  const token = ++panelToken;
  const host = openPanel({ group: rt.group, path: rt.railPath || path });
  host.body.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    const mod = await rt.load();
    if (token !== panelToken) return;
    host.body.innerHTML = "";
    const ctx = { args, params, path, navigate, panel: host };
    if (mod.meta) {
      host.setHead(resolve(mod.meta.title, ctx) || "", resolve(mod.meta.subtitle, ctx));
      setActions(mod.meta.actions ? mod.meta.actions(ctx) : []);
    }
    await mod.mount(host.body, ctx);
  } catch (e) {
    console.error(e);
    if (token !== panelToken) return;
    host.body.innerHTML = "";
    host.body.appendChild(el("div", "empty", "화면을 불러오지 못했습니다: " + e.message));
  }
  host.focusBody();
}

const resolve = (v, ctx) => (typeof v === "function" ? v(ctx) : v);

/** meta → 바탕 화면의 제목 줄. 모듈이 만든 .page 맨 앞에 끼워 넣어 폭이 정확히 맞는다. */
function applyBaseHead(mod, ctx) {
  const page = view.querySelector(".page");
  if (!page) return;
  const head = el("div", "page-head");
  const left = el("div");
  left.appendChild(el("h1", null, resolve(mod.meta.title, ctx) || ""));
  const sub = resolve(mod.meta.subtitle, ctx);
  if (sub) left.appendChild(el("p", null, sub));
  head.appendChild(left);

  const actions = (mod.meta.actions ? mod.meta.actions(ctx) : []).filter(Boolean);
  if (actions.length) {
    const box = el("div", "head-actions");
    actions.forEach((n) => box.appendChild(n));
    head.appendChild(box);
  }
  page.insertBefore(head, page.firstChild);
}

/* 패널 닫기는 언제나 바탕 라우트로 돌아간다. history.back() 을 쓰면 안 된다 —
 * 이너 레일로 옮겨 다녔다면 바로 이전 기록도 또 다른 패널이라서, 닫히는 대신
 * 한 칸 되돌아간 것처럼 보인다. 닫기는 "레이어를 벗는" 동작이다. */
setCloseHandler(() => navigate(basePath || "/home"));

/* ── 좌측 레일 접기 ───────────────────────────────── */
const RAIL_KEY = "xam.rail";
function applyRail(state) {
  document.body.dataset.rail = state;
  const btn = $("#rail-toggle");
  if (btn) btn.setAttribute("aria-label", state === "collapsed" ? "메뉴 펼치기" : "메뉴 접기");
}
function toggleRail() {
  const next = document.body.dataset.rail === "collapsed" ? "expanded" : "collapsed";
  localStorage.setItem(RAIL_KEY, next);
  applyRail(next);
}
applyRail(localStorage.getItem(RAIL_KEY) === "collapsed" ? "collapsed" : "expanded");

/* ── 사이드바 머리 — 품목 · 검수 진행률 ───────────────
 * 240문항 중 몇 개를 검수했는지가 이 앱에서 가장 중요한 숫자다. 어느 화면에
 * 있어도 보이도록 레일에 박아 둔다. */
export async function renderBrandStatus() {
  const [v, book] = await Promise.all([getVersion(), getBook(true)]);
  $("#su-name").textContent = v.pd_label || v.pd || "품목 미설정";
  const team = $("#su-team");
  if (!book.exists) {
    team.textContent = "BOOK 경로 오류";
    team.classList.add("bad");
    return;
  }
  team.classList.remove("bad");
  team.textContent = `검수 ${book.reviewed} / ${book.total}`;
}

const STATUS_KO = { done: "완료", running: "진행 중", queued: "대기", error: "오류" };

export async function renderRecent() {
  const box = $("#side-recent");
  const jobs = await getJobs(12);
  box.innerHTML = "";
  if (!jobs.length) {
    box.appendChild(el("div", "side-empty", "아직 작업이 없습니다."));
    return;
  }
  jobs.forEach((j) => {
    const a = el("a", "recent-item");
    a.href = j.kind === "publish" ? "#/publish" : `#/job/${encodeURIComponent(j.id)}`;
    a.title = `${j.label || j.kind} · ${STATUS_KO[j.status] || j.status}`;
    a.appendChild(el("span", "ri-dot " + (j.status === "done" ? "done" : j.status || "ready")));
    a.appendChild(el("span", "ri-name", j.label || j.kind));
    box.appendChild(a);
  });
}

/* ── 전역 액션: 다음 미검수 문항 ─────────────────────
 * 240개를 도는 것이 이 앱의 핵심 루프다. 어느 화면에서든 한 번에 큐로 돌아온다. */
async function gotoNextUnreviewed() {
  try {
    const { api } = await import("./util.js");
    // 지금 보고 있는 문항 뒤부터 찾는다 — 같은 문항으로 되돌아오지 않게.
    const cur = (basePath || "").startsWith("/questions/")
      ? basePath.slice("/questions/".length) : "";
    const d = await api("/api/questions/next-unreviewed?after=" + encodeURIComponent(cur));
    if (!d.id) {
      toast("미검수 문항이 없습니다. 검수를 모두 마쳤습니다.");
      return;
    }
    navigate("/questions/" + encodeURIComponent(d.id));
  } catch (e) {
    toast("미검수 문항을 찾지 못했습니다: " + e.message, "err");
  }
}

/* ── 부팅 ─────────────────────────────────────────── */
hydrateIcons(document);

$("#btn-next-unreviewed").addEventListener("click", gotoNextUnreviewed);
$("#rail-toggle").addEventListener("click", toggleRail);
$("#brand-mark").addEventListener("click", () => {
  if (document.body.dataset.rail === "collapsed") toggleRail();
});
// 좌하단 칩 = 품목 전환 진입점. 누르면 작업 폴더 패널이 뜼다.
$("#side-user").addEventListener("click", () => navigate("/books"));

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && (e.key === "b" || e.key === "B")) {
    e.preventDefault(); toggleRail();
  }
});

window.addEventListener("hashchange", render);

if (!location.hash) location.hash = "#/scan";
render();
renderBrandStatus();
renderRecent();

window.addEventListener("xam:job-changed", renderRecent);
window.addEventListener("xam:review-changed", renderBrandStatus);
// 폴더를 바꿀면 품목·진행률이 전부 달라진다.
window.addEventListener("xam:book-changed", async () => {
  await renderBrandStatus();
  await renderRecent();
});

// 전역 오류를 조용히 삼키지 않는다(로컬 앱이라 콘솔을 잘 안 본다)
window.addEventListener("unhandledrejection", (e) => {
  console.error(e.reason);
  toast("처리 중 오류: " + (e.reason?.message || e.reason), "err");
});
