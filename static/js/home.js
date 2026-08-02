/* 바탕(아래층)의 기본 화면 — 패널을 닫으면 여기로 돌아온다.
 *
 * ★ 이 앱의 UX 핵심: 목록은 패널(위층), 작업은 바탕(아래층).
 *   그래서 바탕에는 항상 무언가가 깔려 있어야 한다. 아무것도 고르지 않은 상태가
 *   이 화면이다 — 파이프라인 4단계를 띄우고, 누르면 그 단계의 목록 패널이 열린다.
 */
"use strict";

import { $, api, el, toast } from "./util.js";
import { getBook, getVersion } from "./store.js";
import { icon, hydrateIcons } from "./icons.js";
import { donut } from "./charts.js";

export const meta = {
  title: "무엇을 할까요",
  subtitle: "목록은 위에 떠 있는 창에서 고르고, 작업은 이 바탕에서 합니다.",
};

const STEPS = [
  { nav: "sc", path: "/scan", icon: "folder", label: "구조화 MD로 정리",
    desc: "스캔한 OCR 본문을 01/*.md 로 확정합니다." },
  { nav: "q", path: "/questions", icon: "file", label: "문항 교정",
    desc: "_rounds · 02/ · 05/lesson 을 함께 갱신합니다." },
  { nav: "v", path: "/video", icon: "film", label: "영상 제작·검수",
    desc: "슬라이드 · 음성 · 자막을 확인하고 렌더합니다." },
  { nav: "p", path: "/publish", icon: "package", label: "발행",
    desc: "빌드 → FTP → 관리자 화면 임포트." },
];

export async function mount(root, ctx) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card hm-head" id="hm-head"></div>
    <div class="grid grid-2" id="hm-steps"></div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  renderSteps(ctx);
  await renderHead();
}

function renderSteps(ctx) {
  const box = $("#hm-steps");
  box.innerHTML = "";
  STEPS.forEach((s) => {
    const card = el("div", "card hm-step");
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    const head = el("div", "hm-step-head");
    head.appendChild(icon(s.icon, 18));
    head.appendChild(el("b", null, s.label));
    card.appendChild(head);
    card.appendChild(el("p", "muted", s.desc));
    const hint = el("div", "field-hint",
      s.path === "/publish" ? "바탕에서 바로 열립니다" : "위에 목록 창이 뜹니다");
    card.appendChild(hint);
    const go = () => ctx.navigate(s.path);
    card.addEventListener("click", go);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
    });
    box.appendChild(card);
  });
}

async function renderHead() {
  const box = $("#hm-head");
  box.innerHTML = "";
  let v, book, scan;
  try {
    [v, book] = await Promise.all([getVersion(), getBook(true)]);
  } catch (e) {
    box.appendChild(el("div", "empty", "상태를 불러오지 못했습니다: " + e.message));
    return;
  }
  try { scan = await api("/api/scan"); } catch (e) { scan = null; }

  if (!book.exists) {
    const w = el("div", "qz-warn err");
    w.appendChild(icon("alert", 15));
    w.appendChild(el("span", null, book.error
      || "BOOK 을 찾을 수 없습니다. .env 의 XAM_BOOK 을 확인하세요."));
    box.appendChild(w);
    return;
  }

  const left = el("div", "qz-head-stat");
  left.appendChild(donut(book.total ? Math.round((book.reviewed / book.total) * 100) : null,
    { label: "검수", size: 78 }));
  const t = el("div");
  t.appendChild(el("div", "stat-value", `${book.reviewed} / ${book.total}`));
  t.appendChild(el("div", "muted", "문항 검수"));
  left.appendChild(t);
  box.appendChild(left);

  const info = el("div", "hm-facts");
  const fact = (label, value, title) => {
    const f = el("div", "hm-fact");
    f.appendChild(el("span", "muted", label));
    f.appendChild(el("b", null, value));
    if (title) f.title = title;
    return f;
  };
  info.appendChild(fact("품목", `${v.pd_label || v.pd}`, v.pd));
  info.appendChild(fact("회차", `${(book.rounds || []).length}회`,
    (book.rounds || []).map((r) => r.round_label).join(" / ")));
  if (scan) info.appendChild(fact("OCR 확정", `${scan.confirmed} / ${scan.count}`));
  const st = book.stages || {};
  info.appendChild(fact("영상 번들", `${(st["05"] || {}).bundles ?? "?"}개`));
  info.appendChild(fact("BOOK", book.book, book.book));
  box.appendChild(info);
}
