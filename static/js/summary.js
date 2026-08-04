/* 화면 ④ 요약노트 검수 — 좌 .md 편집 / 우 즉시 미리보기, 패널에 발행될 .html
 *
 * 미리보기가 둘인 것은 의도다.
 *   왼쪽 renderMarkdown : **지금 타이핑하는 것**
 *   패널 iframe        : **실제로 발행될 산출물(.html)**
 * 우리는 .md 만 고치므로 그 둘은 갈라진다. 그 사실을 배너로 못박는다.
 */
"use strict";

import { $, $$, api, el, escapeHtml, toast, confirmModal, renderMarkdown, fmtBytes } from "./util.js";
import { icon, hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const S = { list: null, key: null, rec: null, dirty: false };

export const meta = {
  title: (ctx) => (ctx.panel ? `발행될 HTML · ${ctx.args[0]}` : "요약노트 검수"),
  subtitle: (ctx) => (ctx.panel
    ? "이 파일이 실제로 사이트에 올라갑니다. 왼쪽 .md 편집과는 별개입니다."
    : "03/summary_*.md 를 고칩니다. 발행되는 것은 .html 이라는 점을 잊지 마세요."),
  actions: (ctx) => (ctx.panel ? [] : [
    actionBtn("발행될 HTML 보기", () => {
      if (S.key) location.hash = "#/preview/" + encodeURIComponent(S.key);
    }, { iconName: "external" }),
    actionBtn("저장", () => save(), { primary: true, iconName: "check" }),
  ]),
};

export async function mount(root, ctx) {
  if (ctx.panel) return mountPanel(root, ctx);

  const page = el("div", "page");
  page.innerHTML = `
    <div class="quick-row" id="sm-tabs"></div>
    <div id="sm-drift"></div>
    <div class="sm-split">
      <div>
        <div class="qz-label" id="sm-label">03/summary_* — 편집</div>
        <textarea class="md-edit" id="sm-md"></textarea>
        <div class="qz-foot">
          <button class="btn primary" id="sm-save" type="button">저장 (Ctrl+S)</button>
          <button class="btn" id="sm-revert" type="button">되돌리기</button>
          <span class="field-hint qz-foot-hint" id="sm-hint"></span>
        </div>
      </div>
      <div>
        <div class="qz-label">지금 타이핑하는 내용의 미리보기</div>
        <div class="card preview" id="sm-prev"></div>
      </div>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  try {
    S.list = await api("/api/summary");
  } catch (e) {
    root.innerHTML = "";
    root.appendChild(el("div", "empty", "요약노트를 불러오지 못했습니다: " + e.message));
    return;
  }
  renderTabs();
  $("#sm-save").addEventListener("click", () => save());
  $("#sm-revert").addEventListener("click", () => {
    if (!S.rec) return;
    $("#sm-md").value = S.rec.md;
    S.dirty = false;
    updateHint();
    renderPreview();
  });
  const ta = $("#sm-md");
  ta.addEventListener("input", () => { S.dirty = true; updateHint(); renderPreview(); });
  document.addEventListener("keydown", onKey);

  const first = ctx.args[0] || (S.list.items.find((i) => i.md_exists) || S.list.items[0]).key;
  await open(first);
}

function renderTabs() {
  const box = $("#sm-tabs");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = "";
  S.list.items.forEach((it) => {
    const b = el("button", "chip" + (S.key === it.key ? " on" : ""), it.key);
    b.type = "button";
    b.title = `${it.md_path} · ${fmtBytes(it.md_bytes)}`;
    // ★ .md 가 없어도 막지 않는다 — .html 을 직접 고친다(그게 발행되는 파일이다).
    //   예전에는 여기서 disabled 라서, #2 가 .html 만 만든 회차는 요약노트를 아예
    //   고칠 수 없었다.
    if (!it.md_exists && !it.html_exists) {
      b.disabled = true; b.title = "03/ 에 이 과목 파일이 없습니다.";
    } else if (!it.md_exists) {
      b.title = ".md 가 없어 .html 을 직접 고칩니다 (발행되는 파일입니다).";
    }
    b.addEventListener("click", () => open(it.key));
    box.appendChild(b);
  });
  if (S.list.index_url) {
    const a = el("a", "chip", "색인 HTML");
    a.href = S.list.index_url;
    a.target = "_blank";
    a.rel = "noopener";
    box.appendChild(a);
  }
}

async function open(key) {
  if (S.dirty && !(await confirmModal({
    title: "저장하지 않은 편집을 버릴까요?",
    body: `<b>${escapeHtml(S.key || "")}</b> 의 편집 내용이 사라집니다.`,
    ok: "버리고 이동", cancel: "머무르기", danger: true,
  }))) return;

  try {
    S.rec = await api("/api/summary/" + encodeURIComponent(key));
  } catch (e) {
    toast("불러오지 못했습니다: " + e.message, "err");
    return;
  }
  S.key = key;
  S.dirty = false;
  history.replaceState(null, "", "#/summary/" + encodeURIComponent(key));
  $("#sm-md").value = S.rec.md;
  renderTabs();
  renderDrift();
  renderPreview();
  updateHint();
}

function renderDrift() {
  const box = $("#sm-drift");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = "";
  const it = S.list.items.find((i) => i.key === S.key);
  if (!it) return;
  // .md 를 고치면 반드시 뜬다. 그게 정상이고, 그래서 문구로 설명한다.
  const warn = el("div", "qz-warn " + (S.rec.drift ? "warn" : "info"));
  warn.appendChild(icon(S.rec.drift ? "alert" : "bulb", 15));
  warn.appendChild(el("span", null, S.rec.drift
    ? S.list.drift_text
    : "발행되는 것은 .html 입니다. .md 를 고치면 도구 #1/#2 에서 HTML 을 다시 만들어야 "
      + "사이트에 반영됩니다."));
  box.appendChild(warn);
}

function renderPreview() {
  const box = $("#sm-prev");
  if (!box) return;
  box.innerHTML = renderMarkdown($("#sm-md").value);
}

function updateHint() {
  const h = $("#sm-hint");
  if (!h) return;
  const it = S.list.items.find((i) => i.key === S.key);
  h.textContent = (S.dirty ? "저장하지 않은 편집이 있습니다.  ·  " : "")
    + (it ? `${it.md_path} · ${fmtBytes(it.md_bytes)}` : "");
}

async function save() {
  if (!S.rec || !S.dirty) { toast("바뀐 내용이 없습니다."); return; }
  try {
    const r = await api("/api/summary/" + encodeURIComponent(S.key), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ md: $("#sm-md").value, etag: S.rec.etag }),
    });
    S.rec.md = $("#sm-md").value;
    S.rec.etag = r.etag;
    S.rec.drift = true;
    S.dirty = false;
    updateHint();
    renderDrift();
    toast(`저장했습니다 — ${r.written.join(" · ")}`);
    toast(r.warning);
    S.list = await api("/api/summary");
    renderTabs();
  } catch (e) {
    if (e.status === 409) {
      const again = await confirmModal({
        title: "저장하지 못했습니다",
        body: escapeHtml(e.message),
        ok: "최신 내용 다시 읽기", cancel: "머무르기",
      });
      if (again) { S.dirty = false; await open(S.key); }
    } else {
      toast("저장 실패: " + e.message, "err");
    }
  }
}

function onKey(e) {
  if (!location.hash.startsWith("#/summary")) return;
  if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
}

window.addEventListener("beforeunload", (e) => {
  if (S.dirty && location.hash.startsWith("#/summary")) { e.preventDefault(); e.returnValue = ""; }
});

/* ══ 패널: 발행될 HTML ════════════════════════════════ */
async function mountPanel(root, ctx) {
  const key = ctx.args[0];
  root.innerHTML = "";
  let url = null;
  try {
    const d = await api("/api/summary/" + encodeURIComponent(key));
    url = d.html_url;
  } catch (e) {
    root.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message));
    return;
  }
  const note = el("div", "field-hint");
  note.textContent = "03/summary_*.html — 이 파일이 06/theory/ 로 복사되어 사이트에 올라갑니다. "
    + "SVG 를 인라인으로 품고 있어 단독으로도 열립니다.";
  root.appendChild(note);
  const frame = el("iframe", "html-frame");
  frame.src = url;
  frame.loading = "lazy";
  root.appendChild(frame);
  const a = el("a", "btn sm", "새 창에서 열기");
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener";
  root.appendChild(a);
}
