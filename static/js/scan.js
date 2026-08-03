/* 구조화 MD로 정리 (#1 OCR 검수)
 *
 * ★ 이 앱의 UX 핵심 — 목록은 패널(위층), 작업은 바탕(아래층).
 *     #/scan      → 위층 패널: OCR 본문 목록 (고르는 곳)
 *     #/scan/:id  → 아래층 바탕: 그 문항의 작업 화면 (일하는 곳)
 *   패널에서 고르면 패널이 닫히고 바탕이 그 문항으로 열린다.
 *
 * ★ 01/ 은 02/ 와 포맷이 다르다 — CRLF, front matter 19키(source_pdf·source_pages·
 *   has_latex·ocr_by), `## 지문` 섹션이 있다. services/book/scan.py 가 그 포맷을
 *   바이트 단위로 재현한다(실측 80/80 통과).
 */
"use strict";

import { $, $$, api, el, escapeHtml, toast, confirmModal, stateClass } from "./util.js";
import { getPref, setPref } from "./store.js";
import { icon, hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const GLYPHS = ["①", "②", "③", "④", "⑤"];
const DIFFS = ["상", "중", "하"];

const S = { list: null, rec: null, draft: null, dirty: false, raw: false,
            filters: { unconfirmed: false, q: "" } };

export const meta = {
  title: (ctx) => (ctx.panel ? "OCR 본문" : `구조화 MD로 정리 · ${ctx.args[0] || ""}`),
  subtitle: (ctx) => (ctx.panel
    ? "고르면 이 창이 닫히고 아래 바탕에서 열립니다."
    : "01/*.md 를 씁니다. 확정하면 verified · reviewed 가 true 로 바뀝니다."),
  actions: (ctx) => (ctx.panel
    ? [actionBtn("왕복 검증", () => runVerify(), { iconName: "check" })]
    : [
      // 목록은 좌측 레일에서 연다 — 여기 또 두지 않는다.
      actionBtn("원문 PDF", () => toggleSide(), { iconName: "panelRight", id: "sc-side-btn" }),
      actionBtn("원문 펴기", () => toggleRaw(), { iconName: "file", id: "sc-raw-btn" }),
    ]),
};

export async function mount(root, ctx) {
  return ctx.panel ? mountList(root, ctx) : mountWork(root, ctx);
}

/* ══════════ 위층: 패널 — OCR 본문 목록 ══════════ */
async function mountList(root, ctx) {
  Object.assign(S.filters, getPref("scanFilters", {}) || {});
  root.innerHTML = `
    <div class="qz-bar">
      <button class="chip" id="sc-unconf" type="button">미확정만</button>
      <div class="search-box">
        <span data-icon="search" data-icon-size="14"></span>
        <input id="sc-q" type="search" placeholder="id · 과목 · 본문 검색" />
      </div>
      <span class="qz-bar-note muted" id="sc-count"></span>
    </div>
    <div class="sc-list" id="sc-list"></div>
  `;
  hydrateIcons(root);

  const unconf = $("#sc-unconf");
  unconf.classList.toggle("on", S.filters.unconfirmed);
  unconf.addEventListener("click", () => {
    S.filters.unconfirmed = !S.filters.unconfirmed;
    unconf.classList.toggle("on", S.filters.unconfirmed);
    setPref("scanFilters", S.filters);
    refreshList(ctx);
  });

  const input = $("#sc-q");
  input.value = S.filters.q || "";
  let t = null;
  input.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => {
      S.filters.q = input.value;
      setPref("scanFilters", S.filters);
      refreshList(ctx);
    }, 250);
  });

  await refreshList(ctx);
  input.focus();
}

async function refreshList(ctx) {
  const qs = new URLSearchParams();
  if (S.filters.unconfirmed) qs.set("unconfirmed", "1");
  if (S.filters.q) qs.set("q", S.filters.q);
  const box = $("#sc-list");
  try {
    S.list = await api("/api/scan?" + qs.toString());
  } catch (e) {
    if (box) {
      box.innerHTML = "";
      box.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message));
    }
    return;
  }
  const d = S.list;
  const cnt = $("#sc-count");
  if (cnt) {
    cnt.textContent =
      (d.filtered === d.count ? `전체 ${d.count}문항` : `${d.filtered} / ${d.count}문항`)
      + `  ·  확정 ${d.confirmed} / ${d.count}`
      + (d.count - d.confirmed ? `  ·  남은 ${d.count - d.confirmed}` : "  ·  완료")
      + `  ·  ${(d.facets.pdfs || []).join(", ")}`;
  }
  renderList(ctx);
}

function renderList(ctx) {
  const box = $("#sc-list");
  if (!box) return;
  box.innerHTML = "";
  if (!S.list.items.length) {
    box.appendChild(el("div", "empty", "조건에 맞는 문항이 없습니다."));
    return;
  }
  S.list.items.forEach((it) => {
    // 상태 3색 규칙(util.stateClass) — 확정된 문항만 색이 있다. 미확정은 하얗게
    // 남아서 '할 일' 로 보인다. 목록마다 색을 새로 정하지 않는다.
    const row = el("div", "sc-row " + stateClass(1, it.confirmed ? 1 : 0));
    row.dataset.id = it.id;
    row.setAttribute("role", "button");
    row.tabIndex = 0;

    const head = el("div", "sc-row-head");
    head.appendChild(el("span", "sc-row-id", it.id));
    if (it.error) {
      head.appendChild(el("span", "badge err", "파싱 실패"));
    } else {
      head.appendChild(el("span", "sc-row-subj", (it.subject || "").replace(/^빅데이터\s*/, "")));
      head.appendChild(el("span", "badge " + diffTone(it.difficulty), it.difficulty || "?"));
      head.appendChild(el("span", "sc-row-ans", it.answer || ""));
      const marks = el("span", "sc-row-marks");
      if (it.has_jimun) marks.appendChild(el("span", "qz-mark fig", "지문"));
      if (it.has_table) marks.appendChild(el("span", "qz-mark fig", "표"));
      if (it.has_sql) marks.appendChild(el("span", "qz-mark fig", "SQL"));
      if (it.has_figure) marks.appendChild(el("span", "qz-mark fig", "그림"));
      if (it.has_latex) marks.appendChild(el("span", "qz-mark", "수식"));
      marks.appendChild(el("span", "qz-mark " + (it.confirmed ? "" : "todo"),
        it.confirmed ? "확정" : "미확정"));
      head.appendChild(marks);
    }
    row.appendChild(head);

    // OCR 본문이 목록에 그대로 보인다 — 이걸 읽고 고른다
    row.appendChild(el("div", "sc-row-body", it.error || it.preview || ""));

    // ★ 고르면 패널이 닫히고 바탕이 열린다
    const go = () => ctx.navigate("/scan/" + encodeURIComponent(it.id));
    row.addEventListener("click", go);
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
    });
    box.appendChild(row);
  });
}

const diffTone = (d) => (d === "상" ? "err" : d === "중" ? "warn" : "ok");

/* ══════════ 아래층: 바탕 — 문항 작업 ══════════ */
async function mountWork(root, ctx) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="qz-work">
      <section id="sc-editor"><div class="empty">불러오는 중…</div></section>
      <aside class="drawer" id="sc-side">
        <!-- 접혔을 때 뜨는 복원 띠. 이게 없으면 접는 순간 펼 버튼까지 사라진다. -->
        <div class="drawer-strip">
          <button id="sc-side-restore" type="button" title="원문 PDF 펼치기"
                  aria-label="원문 PDF 펼치기">
            <span data-icon="panelLeft" data-icon-size="15"></span>
          </button>
        </div>
        <div class="drawer-head">
          <span>원문 PDF</span>
          <button class="btn icon sm" id="sc-side-toggle" type="button" title="접기">
            <span data-icon="panelRight" data-icon-size="14"></span>
          </button>
        </div>
        <div class="drawer-body" id="sc-side-body"></div>
      </aside>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  $("#sc-side-toggle").addEventListener("click", () => toggleSide(false));
  $("#sc-side-restore").addEventListener("click", () => toggleSide(true));
  applySide(getPref("scanSide") !== "off");
  document.addEventListener("keydown", onKey);

  // 패널을 거치지 않고 바로 들어와도 이웃 이동이 되도록 목록을 조용히 받아 둔다.
  if (!S.list) {
    try { S.list = await api("/api/scan"); } catch (e) { /* 없어도 편집은 된다 */ }
  }
  await open(ctx.args[0], ctx);
}

/* 원문 PDF 드로어 — 헤더 버튼·드로어 버튼·복원 띠 세 곳에서 열고 닫는다. */
function applySide(open) {
  const d = $("#sc-side");
  if (!d) return;
  d.classList.toggle("collapsed", !open);
  setPref("scanSide", open ? "on" : "off");
  const b = $("#sc-side-btn");
  if (b && b.lastChild) b.lastChild.textContent = open ? "원문 PDF 숨기기" : "원문 PDF 보기";
}

function toggleSide(force) {
  const d = $("#sc-side");
  if (!d) return;
  applySide(force != null ? force : d.classList.contains("collapsed"));
}

async function open(qid, ctx) {
  if (S.dirty && !(await confirmModal({
    title: "저장하지 않은 편집을 버릴까요?",
    body: `<b>${escapeHtml(S.rec ? S.rec.id : "")}</b> 의 편집 내용이 사라집니다.`,
    ok: "버리고 이동", cancel: "머무르기", danger: true,
  }))) return;

  const box = $("#sc-editor");
  box.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    S.rec = await api("/api/scan/" + encodeURIComponent(qid));
  } catch (e) {
    box.innerHTML = "";
    box.appendChild(el("div", "empty", "문항을 불러오지 못했습니다: " + e.message));
    return;
  }
  S.draft = snapshot(S.rec);
  S.dirty = false;
  S.ctx = ctx || S.ctx;
  if (location.hash !== "#/scan/" + qid) {
    history.replaceState(null, "", "#/scan/" + encodeURIComponent(qid));
  }
  const h1 = $(".page-head h1");
  if (h1) h1.textContent = `구조화 MD로 정리 · ${qid}`;
  renderEditor();
  renderSide();
}

function snapshot(r) {
  return {
    question: r.question, jimun: r.jimun, choices: r.choices.slice(),
    explanation: r.explanation,
    answer_index: r.fm.answer_index,
    difficulty: r.fm.difficulty || "",
    subject: r.fm.subject || "",
    subject_no: r.fm.subject_no,
  };
}

function renderEditor() {
  const r = S.rec, d = S.draft;
  const box = $("#sc-editor");
  box.innerHTML = "";
  const card = el("div", "card qz-editor");

  const head = el("div", "qz-ed-head");
  head.appendChild(el("span", "badge brand", `${r.fm.round}회 기출`));
  head.appendChild(el("span", "qz-ed-id", r.id));
  head.appendChild(el("span", "badge", (d.subject || "").replace(/^빅데이터\s*/, "")));
  const seg = el("div", "seg sm");
  DIFFS.forEach((x) => {
    const b = el("button", d.difficulty === x ? "on" : "", x);
    b.type = "button";
    b.addEventListener("click", () => { d.difficulty = x; markDirty(); renderEditor(); });
    seg.appendChild(b);
  });
  head.appendChild(seg);
  head.appendChild(el("span", "badge " + (r.confirmed ? "ok" : "warn"),
    r.confirmed ? "확정" : "미확정"));
  card.appendChild(head);

  const der = el("div", "qz-derived");
  der.appendChild(chip(`정답 ${GLYPHS[d.answer_index] || "?"}`, "ok"));
  der.appendChild(chip(`보기 ${d.choices.length}개`, d.choices.length >= 2 ? "" : "bad"));
  der.appendChild(chip(d.jimun.trim() ? "지문 있음" : "지문 없음"));
  der.appendChild(chip(`${r.fm.ocr_by || "?"} 판독`));
  if (r.pdf.name) {
    der.appendChild(chip(`${r.pdf.name} p.${(r.pdf.pages || []).join(", ")}`,
      r.pdf.exists ? "" : "warn", r.pdf.exists ? "" : "00/ 에 PDF 가 없습니다."));
  }
  card.appendChild(der);

  card.appendChild(field("문제", ta(d.question, (v) => { d.question = v; markDirty(); }, 3)));

  const jw = el("div");
  jw.appendChild(ta(d.jimun, (v) => { d.jimun = v; markDirty(); }, 3));
  jw.appendChild(el("div", "field-hint",
    "01/ 에만 있는 섹션입니다. 표·SQL·그림이 여기 들어갑니다. "
    + "02/ 로 넘어갈 때는 문제문에 인라인됩니다."));
  card.appendChild(field("지문 (선택)", jw));

  const cbox = el("div", "qz-choices");
  d.choices.forEach((c, i) => {
    const row = el("label", "qz-choice" + (d.answer_index === i ? " has" : ""));
    const radio = el("input");
    radio.type = "radio";
    radio.name = "sc-answer";
    radio.checked = d.answer_index === i;
    radio.addEventListener("change", () => {
      d.answer_index = i; markDirty(); renderEditor();
    });
    row.appendChild(radio);
    row.appendChild(el("span", "qz-choice-glyph", GLYPHS[i] || `${i + 1}.`));
    const t = ta(c, (v) => { d.choices[i] = v; markDirty(); }, 1);
    t.classList.add("qz-choice-input");
    row.appendChild(t);
    cbox.appendChild(row);
  });
  card.appendChild(field("보기 — 라디오가 정답입니다 (Alt+1~4)", cbox));

  card.appendChild(field("해설",
    ta(d.explanation, (v) => { d.explanation = v; markDirty(); }, 3)));

  const rawBox = el("pre", "qz-md-preview");
  rawBox.id = "sc-raw";
  rawBox.hidden = !S.raw;
  rawBox.textContent = r.md;
  const rawWrap = el("div", "qz-preview-wrap");
  rawWrap.appendChild(rawBox);
  card.appendChild(rawWrap);

  const foot = el("div", "qz-foot");
  const conf = el("button", "btn primary",
    r.confirmed ? "저장 (확정 유지)" : "확정 + 다음 (Ctrl+Enter)");
  conf.type = "button";
  conf.addEventListener("click", () => doSave({ confirm: true, advance: !r.confirmed }));
  foot.appendChild(conf);

  const save = el("button", "btn", "저장 (Ctrl+S)");
  save.type = "button";
  save.addEventListener("click", () => doSave({}));
  foot.appendChild(save);

  if (r.confirmed) {
    const un = el("button", "btn", "확정 해제");
    un.type = "button";
    un.addEventListener("click", () => setConfirm(false));
    foot.appendChild(un);
  }

  const rev = el("button", "btn", "되돌리기");
  rev.type = "button";
  rev.addEventListener("click", () => {
    S.draft = snapshot(S.rec); S.dirty = false; renderEditor();
    toast("편집을 되돌렸습니다.");
  });
  foot.appendChild(rev);

  const prev = el("button", "btn", "← 이전");
  prev.type = "button";
  prev.addEventListener("click", () => step(-1));
  foot.appendChild(prev);

  const next = el("button", "btn", "다음 →");
  next.type = "button";
  next.addEventListener("click", () => step(1));
  foot.appendChild(next);

  const hint = el("span", "field-hint qz-foot-hint");
  hint.id = "sc-foot-hint";
  hint.textContent = S.dirty ? "저장하지 않은 편집이 있습니다." : r.path;
  foot.appendChild(hint);
  card.appendChild(foot);

  box.appendChild(card);
  hydrateIcons(card);
}

function chip(text, tone, title) {
  const c = el("span", "status-chip " + (tone || ""), text);
  if (title) c.title = title;
  return c;
}

function field(label, node) {
  const w = el("div", "qz-field");
  w.appendChild(el("label", "qz-label", label));
  w.appendChild(node);
  return w;
}

function ta(value, onInput, rows) {
  const t = el("textarea");
  t.rows = rows || 2;
  t.value = value || "";
  const grow = () => {
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight + 2, 420) + "px";
  };
  t.addEventListener("input", () => { onInput(t.value); grow(); });
  requestAnimationFrame(grow);
  return t;
}

function renderSide() {
  const box = $("#sc-side-body");
  const r = S.rec;
  box.innerHTML = "";
  if (!r.pdf.name) {
    box.appendChild(el("div", "empty", "source_pdf 가 비어 있습니다."));
    return;
  }
  box.appendChild(el("div", "muted", r.pdf.name));
  const pages = el("div", "vd-env");
  (r.pdf.pages || []).forEach((p) => pages.appendChild(el("span", "status-chip", `p.${p}`)));
  box.appendChild(pages);

  if (r.pdf.exists) {
    const a = el("a", "btn sm", "PDF 열기");
    a.href = r.pdf.url;
    a.target = "_blank";
    a.rel = "noopener";
    box.appendChild(a);
    const fr = el("iframe", "html-frame");
    fr.src = r.pdf.url + "#page=" + ((r.pdf.pages || [1])[0] || 1);
    fr.style.height = "48vh";
    box.appendChild(fr);
  } else {
    box.appendChild(el("div", "empty",
      `00/${r.pdf.name} 이 없습니다. 원문 대조를 하려면 그 폴더에 PDF 가 있어야 합니다.`));
  }
  box.appendChild(el("div", "field-hint",
    "확정하면 verified·reviewed 가 true 로, needs_review 가 false 로 바뀝니다."));
}

/* ══ 저장 ══ */
async function doSave({ confirm = false, advance = false } = {}) {
  try {
    const body = { values: S.draft, etag: S.rec.etag };
    if (confirm) body.flags = { verified: true, reviewed: true, needs_review: false };
    const res = await api("/api/scan/" + encodeURIComponent(S.rec.id), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    afterWrite(res);
    if (advance) await step(1);
  } catch (e) { handleErr(e); }
}

async function setConfirm(v) {
  try {
    const res = await api(`/api/scan/${encodeURIComponent(S.rec.id)}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed: v, etag: S.rec.etag }),
    });
    afterWrite(res);
  } catch (e) { handleErr(e); }
}

function afterWrite(res) {
  S.rec = res.record;
  S.draft = snapshot(S.rec);
  S.dirty = false;
  toast(res.written.length
    ? `저장했습니다 — ${res.written.join(" · ")}`
    : "바뀐 내용이 없습니다.");
  renderEditor();
  renderSide();
  // 목록 캐시도 갱신해 둔다 — 다음에 패널을 열면 확정 표시가 맞아야 한다
  api("/api/scan").then((d) => { S.list = d; }).catch(() => {});
}

function handleErr(e) {
  if (e.status === 409) {
    confirmModal({ title: "저장하지 못했습니다", body: escapeHtml(e.message),
      ok: "최신 내용 다시 읽기", cancel: "머무르기" }).then((again) => {
      if (again) { S.dirty = false; open(S.rec.id, S.ctx); }
    });
  } else {
    toast("저장 실패: " + e.message, "err");
  }
}

async function step(delta) {
  if (!S.rec) return;
  if (!S.list) {
    try { S.list = await api("/api/scan"); } catch (e) { return; }
  }
  const ids = S.list.items.map((i) => i.id);
  const i = ids.indexOf(S.rec.id);
  const next = ids[i + delta];
  if (!next) { toast(delta > 0 ? "목록의 마지막입니다." : "목록의 처음입니다."); return; }
  await open(next, S.ctx);
}

function markDirty() {
  S.dirty = true;
  const h = $("#sc-foot-hint");
  if (h) h.textContent = "저장하지 않은 편집이 있습니다.";
}

function toggleRaw() {
  S.raw = !S.raw;
  const b = $("#sc-raw-btn");
  if (b && b.lastChild) b.lastChild.textContent = S.raw ? "원문 접기" : "원문 펴기";
  const box = $("#sc-raw");
  if (box) box.hidden = !S.raw;
}

async function runVerify() {
  try {
    const r = await api("/api/scan/verify");
    confirmModal({
      title: r.ok ? "왕복 검증 통과" : "왕복 검증 실패",
      body: `01/*.md <b>${r.passed} / ${r.total}</b> 바이트 일치`
        + (r.ok ? "<br><br>저장 경로를 쓸 수 있습니다."
          : `<br><br>실패 ${r.fail_count}건 — 렌더러가 원본을 재현하지 못합니다. `
            + "저장이 막혀 있습니다."),
      ok: "닫기", cancel: "",
    });
  } catch (e) { toast("검증 실패: " + e.message, "err"); }
}

function onKey(e) {
  if (!location.hash.startsWith("#/scan/")) return;
  if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); doSave({}); return; }
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault(); doSave({ confirm: true, advance: true }); return;
  }
  if (e.altKey && ["1", "2", "3", "4"].includes(e.key) && S.draft) {
    e.preventDefault();
    const i = Number(e.key) - 1;
    if (i < S.draft.choices.length) { S.draft.answer_index = i; markDirty(); renderEditor(); }
    return;
  }
  if (e.altKey && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
    e.preventDefault(); step(e.key === "ArrowDown" ? 1 : -1);
  }
}

window.addEventListener("beforeunload", (e) => {
  if (S.dirty && location.hash.startsWith("#/scan")) { e.preventDefault(); e.returnValue = ""; }
});
