/* 화면 ① 문항 교정 — 240문항 검수 큐 + 에디터
 *
 * base 레이어인 이유: 에디터가 미저장 텍스트를 들고 있다. 패널은 Esc·스크림
 * 클릭으로 닫히도록 설계돼 있어서 편집이 날아간다. 240문항을 한 세션에 끊기지
 * 않고 도는 것이 이 화면의 존재 이유다.
 *
 * ★ 저장은 다섯 곳을 쓴다 — _rounds · 02/md · 02/assets · 02 색인 · 05/lesson.
 *   05/lesson 이 빠지면 본문 수정이 웹에 전혀 반영되지 않는다(서버 store.py 참고).
 *   그래서 저장 결과의 '쓴 파일 목록' 을 화면에 그대로 보여준다.
 */
"use strict";

import { $, $$, api, el, html, escapeHtml, toast, confirmModal, renderMarkdown } from "./util.js";
import { getPref, setPref, fireReviewChanged } from "./store.js";
import { icon, hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const GLYPHS = ["①", "②", "③", "④", "⑤"];
const DIFFS = ["상", "중", "하"];

/* ★ 이 앱의 UX 핵심 — 목록은 패널(위층), 작업은 바탕(아래층).
 *     #/questions      → 위층 패널: 문항 목록 (고르는 곳)
 *     #/questions/:id  → 아래층 바탕: 그 문항의 작업 화면 (일하는 곳)
 */
export const meta = {
  title: (ctx) => (ctx.panel ? "문항" : `문항 교정 · ${ctx.args[0] || ""}`),
  subtitle: (ctx) => (ctx.panel
    ? "고르면 이 창이 닫히고 아래 바탕에서 열립니다."
    : "02/ 와 05/lesson 을 함께 갱신합니다. 본문 수정은 05/lesson 을 거쳐 웹에 반영됩니다."),
  actions: (ctx) => (ctx.panel
    ? [actionBtn("재색인", () => reindex(), { iconName: "refresh" })]
    : [
      // 목록은 좌측 레일에서 연다 — 여기 또 두지 않는다.
      actionBtn("기출 원문", () => toggleSource(), { iconName: "panelRight", id: "qz-src-btn" }),
      actionBtn("단축키", () => showShortcuts(), { iconName: "keyboard" }),
    ]),
};

/* ── 화면 상태 ─────────────────────────────────────── */
const S = {
  filters: { round: "", subject: "", difficulty: "", unreviewed: false, q: "" },
  list: null,      // 마지막 목록 응답
  rec: null,       // 열려 있는 문항 레코드
  draft: null,     // 편집 중 값
  dirty: false,
  ctx: null,
  saving: false,
};

export async function mount(root, ctx) {
  S.ctx = ctx;
  return ctx.panel ? mountList(root, ctx) : mountWork(root, ctx);
}

/* ══════════ 위층: 패널 — 문항 목록 ══════════ */
async function mountList(root, ctx) {
  Object.assign(S.filters, getPref("qfilters", {}) || {});
  root.innerHTML = `
    <div class="qz-bar">
      <div class="seg" id="qz-round"></div>
      <button class="chip" id="qz-unrev" type="button">미검수만</button>
      <div class="search-box">
        <span data-icon="search" data-icon-size="14"></span>
        <input id="qz-q" type="search" placeholder="id · 과목 · 태그 검색" />
      </div>
      <span class="qz-bar-note muted" id="qz-count"></span>
    </div>
    <div class="qz-list" id="qz-list"></div>
  `;
  hydrateIcons(root);
  buildFilterBar();
  await refreshList();
  const q = $("#qz-q");
  if (q) q.focus();
}

/* ══════════ 아래층: 바탕 — 문항 작업 ══════════ */
async function mountWork(root, ctx) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="qz-work">
      <section id="qz-editor"><div class="empty">불러오는 중…</div></section>
      <aside class="drawer" id="qz-source">
        <!-- 접혔을 때 뜨는 복원 띠. 이게 없으면 접는 순간 펼 버튼까지 사라진다. -->
        <div class="drawer-strip">
          <button id="qz-source-restore" type="button" title="기출 원문 펼치기"
                  aria-label="기출 원문 펼치기">
            <span data-icon="panelLeft" data-icon-size="15"></span>
          </button>
        </div>
        <div class="drawer-head">
          <span>기출 원문</span>
          <button class="btn icon sm" id="qz-source-toggle" type="button" title="접기">
            <span data-icon="panelRight" data-icon-size="14"></span>
          </button>
        </div>
        <div class="drawer-body" id="qz-source-body"></div>
      </aside>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  $("#qz-source-toggle").addEventListener("click", () => toggleSource(false));
  $("#qz-source-restore").addEventListener("click", () => toggleSource(true));
  applySource(getPref("qsource") !== "off");
  bindKeys();

  // 패널을 거치지 않고 바로 들어와도 이웃 이동이 되도록 목록을 조용히 받아 둔다.
  if (!S.list) {
    try { S.list = await api("/api/questions"); } catch (e) { /* 없어도 편집은 된다 */ }
  }
  await openQuestion(ctx.args[0]);
}

/* 기출 원문 드로어 — 접었다 펴는 것을 헤더 버튼·드로어 버튼·복원 띠 세 곳에서 할 수 있다.
 * 예전에는 접으면 드로어 헤더까지 숨어서 다시 펼 수단이 화면에 하나도 남지 않았다. */
function applySource(open) {
  const d = $("#qz-source");
  if (!d) return;
  d.classList.toggle("collapsed", !open);
  setPref("qsource", open ? "on" : "off");
  const b = $("#qz-src-btn");
  if (b && b.lastChild) b.lastChild.textContent = open ? "기출 원문 숨기기" : "기출 원문 보기";
}

function toggleSource(force) {
  const d = $("#qz-source");
  if (!d) return;
  const open = force != null ? force : d.classList.contains("collapsed");
  applySource(open);
}

/* ── 필터 바 — 문제집이니 회차만 ────────────
 * 회차 수는 서버가 디스크를 스캔해 준 facets.rounds 를 그대로 쓴다 —
 * 3회든 9회든 21회든, 초기에 1~2회만 있어도 그대로 뜨다. */
function buildFilterBar() {
  const unrev = $("#qz-unrev");
  unrev.classList.toggle("on", S.filters.unreviewed);
  unrev.addEventListener("click", () => {
    S.filters.unreviewed = !S.filters.unreviewed;
    unrev.classList.toggle("on", S.filters.unreviewed);
    onFilterChange();
  });

  const input = $("#qz-q");
  input.value = S.filters.q || "";
  let t = null;
  input.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => { S.filters.q = input.value; onFilterChange(); }, 250);
  });

}

/** 회차 세그먼트 — 목록을 받은 뒤에 한 번 만들고, 이후엔 on 만 바꿈. */
function buildRoundSeg(rounds) {
  const segBox = $("#qz-round");
  if (segBox.dataset.built === "1") return;
  segBox.dataset.built = "1";
  const mk = (label, value) => {
    const b = el("button", S.filters.round === value ? "on" : "", label);
    b.type = "button";
    b.dataset.round = value;
    b.addEventListener("click", () => { S.filters.round = value; onFilterChange(); });
    return b;
  };
  segBox.appendChild(mk("전체", ""));
  // ★ m0${r} 로 조립하면 10회차부터 m010 이 된다. 둘 자리로 패딩한다.
  rounds.forEach((r) => {
    const code = "m" + String(r).padStart(2, "0");
    segBox.appendChild(mk(`${r}회`, code));
  });
}

async function onFilterChange() {
  setPref("qfilters", S.filters);
  $$("#qz-round button").forEach((b) => {
    b.classList.toggle("on", (b.dataset.round || "") === S.filters.round);
  });
  await refreshList();
}

/* ── 목록 ───────────────────────────── */
async function refreshList() {
  if (!$("#qz-list")) return;          // 패널이 닫혀 있으면 그릴 곳이 없다
  const f = S.filters;
  const params = { round: f.round, q: f.q, unreviewed: f.unreviewed ? 1 : "" };
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null));
  try {
    S.list = await api("/api/questions?" + qs.toString());
  } catch (e) {
    $("#qz-list").innerHTML = "";
    $("#qz-list").appendChild(el("div", "empty", "목록을 불러오지 못했습니다: " + e.message));
    return;
  }
  buildRoundSeg(S.list.facets.rounds || []);
  renderCount();
  renderList();
}

/** 큰 진행률 패널 대신 한 줄 — 목록을 높이 쓰는 것이 이 화면의 목적이다. */
function renderCount() {
  const d = S.list;
  const box = $("#qz-count");
  if (!box) return;
  const remain = d.total - d.reviewed;
  box.textContent = (d.filtered === d.total
    ? `전체 ${d.total}문항`
    : `${d.filtered} / ${d.total}문항`)
    + `  ·  검수 ${d.reviewed} / ${d.total}`
    + (remain ? `  ·  남은 ${remain}` : "  ·  완료");
}

function renderList() {
  const box = $("#qz-list");
  box.innerHTML = "";
  if (!S.list.items.length) {
    box.appendChild(el("div", "empty", "조건에 맞는 문항이 없습니다."));
    return;
  }
  S.list.items.forEach((it) => {
    // ★ 링크로 둔다 — 딥링크·새 탭이 되어야 하고, 누르면 셸이 패널을 닫고
    //   바탕에 그 문항을 마운트한다(라우터가 레이어를 갈아준다).
    const a = el("a", "qz-row");
    a.href = "#/questions/" + encodeURIComponent(it.id);
    a.dataset.id = it.id;
    a.appendChild(el("span", "qz-row-id", it.id));
    // 정답·난이도는 오른쪽으로 띄우고(첫 줄), 과목·표시는 둘째 줄에 붙인다.
    a.appendChild(el("span", "qz-row-ans", it.answer));
    a.appendChild(el("span", "badge " + diffTone(it.difficulty), it.difficulty));
    a.appendChild(el("span", "qz-row-subj", it.subject.replace(/^빅데이터\s*/, "")));
    const marks = el("span", "qz-row-marks");
    if (it.has_figure) marks.appendChild(el("span", "qz-mark fig", "그림"));
    if (!it.reviewed) marks.appendChild(el("span", "qz-mark todo", "미검수"));
    a.appendChild(marks);
    box.appendChild(a);
  });
}

const diffTone = (d) => (d === "상" ? "err" : d === "중" ? "warn" : "ok");

/* ── 에디터 ────────────────────────────────────────── */
async function openQuestion(qid) {
  if (S.dirty && !(await confirmDiscard())) return;

  const box = $("#qz-editor");
  box.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    S.rec = await api("/api/questions/" + encodeURIComponent(qid));
  } catch (e) {
    box.innerHTML = "";
    box.appendChild(el("div", "empty", "문항을 불러오지 못했습니다: " + e.message));
    return;
  }
  S.draft = snapshot(S.rec);
  S.dirty = false;

  const hash = "#/questions/" + encodeURIComponent(qid);
  if (location.hash !== hash) history.replaceState(null, "", hash);
  const h1 = $(".page-head h1");
  if (h1) h1.textContent = `문항 교정 · ${qid}`;

  renderEditor();
  loadSource(qid);
}

function snapshot(rec) {
  return {
    question: rec.question,
    choices: rec.choices.slice(),
    answer_index: rec.answer_index,
    explanation: rec.explanation,
    explanation_speech: rec.explanation_speech,
    difficulty: rec.difficulty,
    subject: rec.subject,
    subject_no: rec.subject_no,
    tags: rec.tags.slice(),
  };
}

function renderEditor() {
  const r = S.rec, d = S.draft;
  const box = $("#qz-editor");
  box.innerHTML = "";

  const card = el("div", "card qz-editor");

  // ── 머리줄
  const head = el("div", "qz-ed-head");
  head.appendChild(el("span", "badge brand", `${r.round}회`));
  head.appendChild(el("span", "qz-ed-id", r.id));
  head.appendChild(el("span", "badge", r.subject.replace(/^빅데이터\s*/, "")));
  const seg = el("div", "seg sm");
  DIFFS.forEach((x) => {
    const b = el("button", d.difficulty === x ? "on" : "", x);
    b.type = "button";
    b.addEventListener("click", () => { d.difficulty = x; markDirty(); renderEditor(); });
    seg.appendChild(b);
  });
  head.appendChild(seg);
  const bundleLink = el("a", "badge info", `${r.bundle} (${r.bundle_range[0]}–${r.bundle_range[1]}번)`);
  bundleLink.href = "#/video";
  bundleLink.title = "이 문항이 실린 영상 번들";
  head.appendChild(bundleLink);
  card.appendChild(head);

  // ── 파생 미리보기
  card.appendChild(derivedRow());

  // ── 경고
  (r.warnings || []).forEach((w) => card.appendChild(warnBanner(w)));

  // ── 문제문
  card.appendChild(field("문제", textarea(d.question, (v) => { d.question = v; markDirty(); }, 3)));

  // ── 보기 4개 (라디오가 곧 정답)
  const cbox = el("div", "qz-choices");
  d.choices.forEach((c, i) => {
    const row = el("label", "qz-choice" + (d.answer_index === i ? " has" : ""));
    const radio = el("input");
    radio.type = "radio";
    radio.name = "qz-answer";
    radio.checked = d.answer_index === i;
    radio.addEventListener("change", () => { setAnswer(i); });
    row.appendChild(radio);
    row.appendChild(el("span", "qz-choice-glyph", GLYPHS[i]));
    const ta = textarea(c, (v) => { d.choices[i] = v; markDirty(); }, 1);
    ta.classList.add("qz-choice-input");
    row.appendChild(ta);
    cbox.appendChild(row);
  });
  card.appendChild(field("보기 — 라디오가 정답입니다 (Alt+1~4)", cbox));

  // ── 해설
  const explWrap = el("div");
  explWrap.appendChild(textarea(d.explanation, (v) => { d.explanation = v; markDirty(); refreshFigures(); }, 4));
  const figNote = el("div", "field-hint");
  figNote.id = "qz-fig-note";
  explWrap.appendChild(figNote);
  card.appendChild(field("해설", explWrap));

  // ── 그림
  if (r.assets.length || r.inline_figures.length) card.appendChild(figureBlock(r));

  // ── 낭독문
  const spWrap = el("div");
  spWrap.appendChild(textarea(d.explanation_speech,
    (v) => { d.explanation_speech = v; markDirty(); renderSpeechCheck(); }, 3));
  const spChk = el("div", "qz-speech-check");
  spChk.id = "qz-speech-check";
  spWrap.appendChild(spChk);
  card.appendChild(field("해설 낭독 (영상 내레이션)", spWrap));

  // ── 태그
  const tagIn = el("input", "qz-tags");
  tagIn.type = "text";
  tagIn.value = d.tags.join(", ");
  tagIn.placeholder = "쉼표로 구분";
  tagIn.addEventListener("input", () => {
    d.tags = tagIn.value.split(",").map((t) => t.trim()).filter(Boolean);
    markDirty();
  });
  card.appendChild(field("태그", tagIn));

  // ── md 미리보기 토글
  const prevBtn = el("button", "btn sm", "재생성될 02/*.md 보기");
  prevBtn.type = "button";
  const prevBox = el("pre", "preview qz-md-preview");
  prevBox.hidden = true;
  prevBtn.addEventListener("click", async () => {
    prevBox.hidden = !prevBox.hidden;
    if (!prevBox.hidden) {
      prevBox.textContent = "불러오는 중…";
      try {
        const p = await api(`/api/questions/${encodeURIComponent(r.id)}/preview`);
        prevBox.textContent = p.md;
      } catch (e) {
        prevBox.textContent = "미리보기 실패: " + e.message;
      }
    }
  });
  const prevWrap = el("div", "qz-preview-wrap");
  prevWrap.appendChild(prevBtn);
  prevWrap.appendChild(prevBox);
  card.appendChild(prevWrap);

  // ── 바닥 액션
  card.appendChild(footer());
  box.appendChild(card);
  hydrateIcons(card);

  renderSpeechCheck();
  refreshFigures();
}

function field(label, node) {
  const wrap = el("div", "qz-field");
  wrap.appendChild(el("label", "qz-label", label));
  wrap.appendChild(node);
  return wrap;
}

function textarea(value, onInput, rows) {
  const ta = el("textarea");
  ta.rows = rows || 2;
  ta.value = value || "";
  const grow = () => {
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight + 2, 460) + "px";
  };
  ta.addEventListener("input", () => { onInput(ta.value); grow(); });
  requestAnimationFrame(grow);
  return ta;
}

function derivedRow() {
  const d = S.draft, r = S.rec;
  const row = el("div", "qz-derived");
  const chip = (text, tone, title) => {
    const c = el("span", "status-chip " + (tone || ""), text);
    if (title) c.title = title;
    return c;
  };
  row.appendChild(chip(`정답 ${GLYPHS[d.answer_index] || "?"}`, "ok"));
  row.appendChild(chip(`보기 ${d.choices.length}개`, d.choices.length === 4 ? "" : "bad"));
  row.appendChild(chip(r.derived.has_figure ? "그림 있음" : "그림 없음", ""));
  const est = r.derived.flags_source === "estimated";
  row.appendChild(chip(`SQL ${r.derived.has_sql ? "있음" : "없음"}${est ? " (추정)" : ""}`,
    est ? "warn" : "", est ? "02/*.md 가 없어 본문에서 추정한 값입니다." : "02/*.md 에서 보존한 값입니다."));
  row.appendChild(chip(`표 ${r.derived.has_table ? "있음" : "없음"}${est ? " (추정)" : ""}`,
    est ? "warn" : ""));
  row.appendChild(chip(r.md_flags.reviewed ? "검수완료" : "미검수",
    r.md_flags.reviewed ? "ok" : "warn"));
  return row;
}

function warnBanner(w) {
  const tone = w.level === "error" ? "err" : w.level === "warn" ? "warn" : "info";
  const box = el("div", "qz-warn " + tone);
  box.appendChild(icon(w.level === "error" ? "alert" : "bulb", 15));
  box.appendChild(el("span", null, w.text));
  return box;
}

function figureBlock(r) {
  const wrap = el("div", "qz-figs");
  r.assets.forEach((a) => {
    const fig = el("div", "qz-fig");
    const img = el("img");
    img.src = a.url;
    img.alt = a.name + " 참고 그림";
    img.loading = "lazy";
    fig.appendChild(img);
    const cap = el("div", "qz-fig-cap");
    cap.appendChild(el("code", null, `assets/${a.name}.svg`));
    if (!a.on_disk) cap.appendChild(el("span", "badge err", "파일 없음"));
    fig.appendChild(cap);
    wrap.appendChild(fig);
  });
  return field("그림", wrap);
}

/** 해설 본문에 인라인된 그림 이름이 assets 와 맞는지 — 이름을 잘못 고치면 그림이 사라진다. */
function refreshFigures() {
  const note = $("#qz-fig-note");
  if (!note) return;
  const inline = [...(S.draft.explanation || "").matchAll(/!\[[^\]]*\]\(assets\/([^)]+)\)/g)]
    .map((m) => m[1].replace(/\.svg$/, ""));
  const have = S.rec.assets.map((a) => a.name);
  const missing = inline.filter((n) => !have.includes(n));
  const unused = have.filter((n) => !inline.includes(n));
  const parts = [];
  if (inline.length) parts.push(`해설에 인라인된 그림: ${inline.join(", ")}`);
  if (missing.length) parts.push(`⚠ assets 에 없는 이름: ${missing.join(", ")} — 웹에서 그림이 안 보입니다.`);
  if (unused.length) parts.push(`⚠ 해설이 참조하지 않는 그림: ${unused.join(", ")}`);
  note.textContent = parts.join("  ·  ");
  note.classList.toggle("bad", missing.length > 0 || unused.length > 0);
}

/** 낭독문 정답번호 교차검증 — 정답을 옮기면 반드시 걸린다. */
function renderSpeechCheck() {
  const box = $("#qz-speech-check");
  if (!box) return;
  const KOR = ["일", "이", "삼", "사", "오"];
  const s = (S.draft.explanation_speech || "").trim();
  box.innerHTML = "";
  if (!s) {
    box.appendChild(el("span", "status-chip bad", "낭독문이 비어 있습니다 — 내레이션이 만들어지지 않습니다"));
    return;
  }
  const m = s.match(/^정답은\s*(일|이|삼|사|오)\s*번/);
  if (!m) {
    box.appendChild(el("span", "status-chip warn",
      "‘정답은 N 번입니다.’ 로 시작하지 않습니다"));
    return;
  }
  const said = KOR.indexOf(m[1]);
  if (said !== S.draft.answer_index) {
    box.appendChild(el("span", "status-chip bad",
      `낭독문 정답(${m[1]} 번)이 보기 정답(${GLYPHS[S.draft.answer_index]})과 다릅니다`));
    const fix = el("button", "btn sm", "접두어 맞추기");
    fix.type = "button";
    fix.addEventListener("click", () => {
      S.draft.explanation_speech = s.replace(/^정답은\s*(일|이|삼|사|오)\s*번/,
        `정답은 ${KOR[S.draft.answer_index]} 번`);
      markDirty();
      renderEditor();
    });
    box.appendChild(fix);
  } else {
    box.appendChild(el("span", "status-chip ok", `낭독문 정답 ${m[1]} 번 — 일치`));
  }
}

function setAnswer(i) {
  if (i < 0 || i >= S.draft.choices.length) return;
  S.draft.answer_index = i;
  markDirty();
  renderEditor();
}

function footer() {
  const f = el("div", "qz-foot");
  const save = el("button", "btn primary", "저장 + 검수완료 (Ctrl+Enter)");
  save.type = "button";
  save.addEventListener("click", () => doSave({ review: true, advance: true }));

  const saveOnly = el("button", "btn", "저장 (Ctrl+S)");
  saveOnly.type = "button";
  saveOnly.addEventListener("click", () => doSave({}));

  const reviewOnly = el("button", "btn", S.rec.md_flags.reviewed ? "검수 해제" : "검수완료만");
  reviewOnly.type = "button";
  reviewOnly.addEventListener("click", () => doReview(!S.rec.md_flags.reviewed));

  const revert = el("button", "btn", "되돌리기");
  revert.type = "button";
  revert.addEventListener("click", () => {
    S.draft = snapshot(S.rec);
    S.dirty = false;
    renderEditor();
    toast("편집을 되돌렸습니다.");
  });

  const next = el("button", "btn", "다음 미검수 →");
  next.type = "button";
  next.addEventListener("click", () => advance());

  f.append(save, saveOnly, reviewOnly, revert, next);
  const hint = el("span", "field-hint qz-foot-hint");
  hint.id = "qz-foot-hint";
  hint.textContent = S.dirty ? "저장하지 않은 편집이 있습니다." : "";
  f.appendChild(hint);
  return f;
}

function markDirty() {
  S.dirty = true;
  const h = $("#qz-foot-hint");
  if (h) h.textContent = "저장하지 않은 편집이 있습니다.";
}

/* ── 저장 ──────────────────────────────────────────── */
async function doSave({ review = false, advance: adv = false } = {}) {
  if (S.saving) return;
  S.saving = true;
  try {
    const body = { values: S.draft, etag: S.rec.etag };
    if (review) body.flags = { reviewed: true, needs_review: false };
    const res = await api(`/api/questions/${encodeURIComponent(S.rec.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    afterWrite(res);
    if (adv) { await advance(); return; }
  } catch (e) {
    handleWriteError(e);
  } finally {
    S.saving = false;
  }
}

async function doReview(reviewed) {
  if (S.dirty) {
    toast("먼저 저장하거나 되돌린 뒤 검수 상태를 바꾸세요.", "err");
    return;
  }
  try {
    const res = await api(`/api/questions/${encodeURIComponent(S.rec.id)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewed, etag: S.rec.etag }),
    });
    afterWrite(res);
  } catch (e) {
    handleWriteError(e);
  }
}

/** 저장 결과 반영 — 실제로 쓴 파일 목록을 보여주는 게 핵심이다. */
function afterWrite(res) {
  S.rec = res.record;
  S.draft = snapshot(S.rec);
  S.dirty = false;

  const files = (res.written || []).join(" · ") || "변경 없음";
  toast(`저장했습니다 — ${files}`);

  (res.notes || []).forEach((n) => {
    if (n.level === "error") toast(n.text, "err");
    else if (n.level === "warn") toast(n.text);
  });

  const st = res.stale || {};
  if (st.deck || st.video) {
    const parts = [];
    if (st.deck) parts.push("deck.html 재생성(#2)");
    if (st.video) parts.push("영상 재렌더(#3)");
    toast(`${st.bundle} — 본문이 바뀌어 ${parts.join(" · ")} 이 필요합니다.`);
  }

  renderEditor();
  fireReviewChanged({ id: S.rec.id });
  // 패널이 닫혀 있어 목록 DOM 은 없다 — 캐시만 갱신해 둔다.
  api("/api/questions").then((d) => { S.list = d; }).catch(() => {});
}

function handleWriteError(e) {
  if (e.status === 409) {
    const box = $("#qz-editor");
    const banner = el("div", "qz-warn err");
    banner.appendChild(icon("alert", 15));
    banner.appendChild(el("span", null, e.message));
    const btn = el("button", "btn sm", "최신 내용 다시 읽기");
    btn.type = "button";
    btn.addEventListener("click", async () => {
      S.dirty = false;
      await openQuestion(S.rec.id);
    });
    banner.appendChild(btn);
    box.insertBefore(banner, box.firstChild);
    toast("저장하지 못했습니다 — 디스크가 먼저 바뀌었습니다.", "err");
  } else if (e.status === 423) {
    toast(e.message, "err");
  } else {
    toast("저장 실패: " + e.message, "err");
  }
}

async function advance() {
  try {
    const d = await api("/api/questions/next-unreviewed?after=" + encodeURIComponent(S.rec.id));
    if (!d.id) { toast("미검수 문항이 없습니다. 검수를 모두 마쳤습니다."); return; }
    location.hash = "#/questions/" + encodeURIComponent(d.id);
  } catch (e) {
    toast("다음 문항을 찾지 못했습니다: " + e.message, "err");
  }
}

async function reindex() {
  try {
    const r = await api("/api/questions/reindex", { method: "POST", body: "{}" ,
      headers: { "Content-Type": "application/json" } });
    const ch = Object.entries(r.changed).filter(([, v]) => v).map(([k]) => k);
    toast(ch.length ? `색인을 다시 만들었습니다 — ${ch.join(" · ")}` : "색인이 이미 최신입니다.");
    if ($("#qz-list")) await refreshList(); else S.list = await api("/api/questions");
  } catch (e) {
    toast("재색인 실패: " + e.message, "err");
  }
}

/* ── 기출 원문 드로어 ──────────────────────────────── */
async function loadSource(qid) {
  const body = $("#qz-source-body");
  body.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    const d = await api(`/api/questions/${encodeURIComponent(qid)}/source`);
    body.innerHTML = "";
    if (!d.exists) {
      body.appendChild(el("div", "empty",
        d.id ? `기출 원문 ${d.id} 을 찾을 수 없습니다.` : "derived_from 이 비어 있습니다."));
      return;
    }
    body.appendChild(el("div", "muted", `${d.id} · ${d.path}`));
    const pre = el("div", "preview");
    // ★ 01/*.md 는 CRLF 다(02/*.md 는 LF 전용). \r 을 허용하지 않으면 front matter 가
    //   그대로 본문에 남아 YAML 이 목록처럼 렌더된다.
    pre.innerHTML = renderMarkdown(d.md.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, ""));
    body.appendChild(pre);
  } catch (e) {
    body.innerHTML = "";
    body.appendChild(el("div", "empty", "원문을 불러오지 못했습니다: " + e.message));
  }
}

/* ── 미저장 보호 ───────────────────────────────────── */
async function confirmDiscard() {
  return confirmModal({
    title: "저장하지 않은 편집을 버릴까요?",
    body: `<b>${escapeHtml(S.rec ? S.rec.id : "")}</b> 의 편집 내용이 사라집니다.`,
    ok: "버리고 이동", cancel: "머무르기", danger: true,
  });
}

window.addEventListener("beforeunload", (e) => {
  if (S.dirty) { e.preventDefault(); e.returnValue = ""; }
});

/* ── 키보드 — 240개를 도는 속도가 이 화면의 전부다 ── */
function bindKeys() {
  document.addEventListener("keydown", onKey);
}

function onKey(e) {
  if (!location.hash.startsWith("#/questions/")) return;
  const tag = (e.target.tagName || "").toLowerCase();
  const typing = tag === "textarea" || tag === "input";

  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
    e.preventDefault(); doSave({}); return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault(); doSave({ review: true, advance: true }); return;
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
    e.preventDefault(); $("#qz-q").focus(); $("#qz-q").select(); return;
  }
  if (e.altKey && ["1", "2", "3", "4"].includes(e.key)) {
    e.preventDefault(); setAnswer(Number(e.key) - 1); return;
  }
  if (e.altKey && ["q", "Q", "w", "W", "e", "E"].includes(e.key)) {
    e.preventDefault();
    const map = { q: "상", w: "중", e: "하" };
    S.draft.difficulty = map[e.key.toLowerCase()];
    markDirty(); renderEditor(); return;
  }
  if (e.altKey && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
    e.preventDefault(); step(e.key === "ArrowDown" ? 1 : -1); return;
  }
  if (e.key === "?" && !typing) {
    e.preventDefault(); showShortcuts();
  }
}

async function step(delta) {
  if (!S.rec) return;
  if (!S.list) { try { S.list = await api("/api/questions"); } catch (e) { return; } }
  const ids = S.list.items.map((i) => i.id);
  const i = ids.indexOf(S.rec.id);
  const next = ids[i + delta];
  if (!next) { toast(delta > 0 ? "목록의 마지막입니다." : "목록의 처음입니다."); return; }
  location.hash = "#/questions/" + encodeURIComponent(next);
}

function showShortcuts() {
  const rows = [
    ["Ctrl+S", "저장"],
    ["Ctrl+Enter", "저장 + 검수완료 + 다음 미검수로 이동"],
    ["Alt+1 ~ 4", "정답을 그 보기로"],
    ["Alt+Q / W / E", "난이도 상 / 중 / 하"],
    ["Alt+↓ / ↑", "목록에서 다음 / 이전 문항"],
    ["Ctrl+K", "검색 포커스"],
    ["Ctrl+B", "좌측 메뉴 접기"],
    ["?", "이 도움말"],
  ];
  confirmModal({
    title: "단축키",
    body: `<table class="qz-keys">${rows.map(([k, v]) =>
      `<tr><td><kbd>${escapeHtml(k)}</kbd></td><td>${escapeHtml(v)}</td></tr>`).join("")}</table>`,
    ok: "닫기", cancel: "",
  });
}
