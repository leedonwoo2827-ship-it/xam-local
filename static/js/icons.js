/* 아이콘 — 단일 소스. 주홍 단색 라인 아이콘 한 벌.
 *
 * 규격: 24×24 viewBox · fill 없음 · stroke=currentColor · 굵기 1.6 · 끝/이음 round.
 * 색은 언제나 currentColor 라서 부모의 color 만 바꾸면 톤이 따라온다.
 * 이모지는 쓰지 않는다 — OS 마다 모양·크기·색이 달라 디자인 시스템이 성립하지 않는다.
 */
"use strict";

/** name → path/shape 마크업 (viewBox 24×24 기준) */
export const PATHS = {
  /* 내비게이션 */
  home:      '<path d="M3.5 10.3 12 3.6l8.5 6.7"/><path d="M5.6 9.2V20.4h12.8V9.2"/>',
  sparkles:  '<path d="M11 3.4l1.7 3.9 3.9 1.7-3.9 1.7L11 14.6 9.3 10.7 5.4 9l3.9-1.7z"/><path d="M17.8 15.1l.8 1.8 1.8.8-1.8.8-.8 1.8-.8-1.8-1.8-.8 1.8-.8z"/>',
  grid:      '<rect x="3.6" y="3.6" width="7" height="7" rx="1.8"/><rect x="13.4" y="3.6" width="7" height="7" rx="1.8"/><rect x="3.6" y="13.4" width="7" height="7" rx="1.8"/><rect x="13.4" y="13.4" width="7" height="7" rx="1.8"/>',
  plus:      '<path d="M12 5.5v13"/><path d="M5.5 12h13"/>',
  search:    '<circle cx="10.6" cy="10.6" r="6.4"/><path d="M20.4 20.4l-5.2-5.2"/>',
  send:      '<path d="M12 19.2V5.2"/><path d="M5.6 11.6 12 5.2l6.4 6.4"/>',

  /* 앱 · 데이터 */
  chart:     '<path d="M4 20h16"/><rect x="5.6" y="11" width="3.4" height="6" rx="1"/><rect x="10.9" y="7.4" width="3.4" height="9.6" rx="1"/><rect x="16.2" y="13.4" width="3.4" height="3.6" rx="1"/>',
  gauge:     '<path d="M4.4 17.6a8.6 8.6 0 1 1 15.2 0"/><path d="M12 12.6 15.6 9"/><circle cx="12" cy="17.6" r="1.3"/>',
  table:     '<rect x="3.8" y="4.6" width="16.4" height="14.8" rx="2.2"/><path d="M3.8 9.4h16.4"/><path d="M9.6 9.4v10"/>',
  calendar:  '<rect x="3.8" y="5.6" width="16.4" height="14" rx="2.2"/><path d="M3.8 10.2h16.4"/><path d="M8.4 3.6v3.6"/><path d="M15.6 3.6v3.6"/>',
  file:      '<path d="M13.6 3.8H7.4a2 2 0 0 0-2 2v12.4a2 2 0 0 0 2 2h9.2a2 2 0 0 0 2-2V8.8z"/><path d="M13.4 3.9v4.9h5"/>',
  folder:    '<path d="M3.8 7.4a2 2 0 0 1 2-2h3.3l1.9 2.3h7.2a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H5.8a2 2 0 0 1-2-2z"/>',

  /* 영상 · 발행 (XAM LOCAL 추가) */
  film:      '<rect x="3.4" y="5" width="17.2" height="14" rx="2.2"/><path d="M8.2 5v14"/><path d="M15.8 5v14"/><path d="M3.4 12h17.2"/>',
  play:      '<circle cx="12" cy="12" r="8.2"/><path d="M10.2 8.6 16 12l-5.8 3.4z"/>',
  package:   '<path d="M20.4 8.4 12 4.2 3.6 8.4v7.2L12 19.8l8.4-4.2z"/><path d="M3.6 8.4 12 12.6l8.4-4.2"/><path d="M12 12.6v7.2"/>',
  keyboard:  '<rect x="2.8" y="6.4" width="18.4" height="11.2" rx="2.2"/><path d="M6.6 10h.01"/><path d="M10 10h.01"/><path d="M13.4 10h.01"/><path d="M16.8 10h.01"/><path d="M7.8 14h8.4"/>',
  alert:     '<path d="M12 4.4 21 19.6H3z"/><path d="M12 10v3.8"/><circle cx="12" cy="17" r=".9"/>',
  pin:       '<path d="M14.8 3.6 20.4 9.2l-3 1 .5 5.4-6.5-6.5 1-3z"/><path d="M11.4 12.6 5.4 18.6"/><path d="M9.2 6.6l8.2 8.2"/>',
  bulb:      '<path d="M9.4 17.4a5.6 5.6 0 1 1 5.2 0"/><path d="M9.6 17.4h4.8"/><path d="M10.2 20.2h3.6"/>',
  check:     '<path d="M5 12.8 9.6 17.4 19 8"/>',
  clock:     '<circle cx="12" cy="12" r="8.2"/><path d="M12 7.6V12l3.2 2"/>',
  broadcast: '<path d="M4.9 19.1a10 10 0 0 1 0-14.2"/><path d="M7.8 16.2a6 6 0 0 1 0-8.4"/><circle cx="12" cy="12" r="1.9"/><path d="M16.2 7.8a6 6 0 0 1 0 8.4"/><path d="M19.1 4.9a10 10 0 0 1 0 14.2"/>',
  key:       '<circle cx="8.4" cy="15.6" r="3.8"/><path d="M11.1 12.9 19.6 4.4"/><path d="M16.6 4.4h3v3"/><path d="M14.6 9.4l2.2 2.2"/>',

  /* 조작 */
  download:  '<path d="M12 4.4v10.4"/><path d="M7.8 10.8 12 15l4.2-4.2"/><path d="M4.6 18.6h14.8"/>',
  upload:    '<path d="M12 15.4V5"/><path d="M7.8 9.2 12 5l4.2 4.2"/><path d="M4.6 18.6h14.8"/>',
  refresh:   '<path d="M19.4 12a7.4 7.4 0 1 1-2.3-5.3"/><path d="M19.6 4.4v4.2h-4.2"/>',
  close:     '<path d="M6.2 6.2l11.6 11.6"/><path d="M17.8 6.2 6.2 17.8"/>',
  external:  '<path d="M13.6 4.6h5.8v5.8"/><path d="M19.4 4.6 11 13"/><path d="M17 14.4v3.4a1.8 1.8 0 0 1-1.8 1.8H6.4a1.8 1.8 0 0 1-1.8-1.8V9a1.8 1.8 0 0 1 1.8-1.8h3.4"/>',

  /* 캐럿 · 패널 */
  chevronLeft:  '<path d="M14.6 6.4 9 12l5.6 5.6"/>',
  chevronRight: '<path d="M9.4 6.4 15 12l-5.6 5.6"/>',
  chevronDown:  '<path d="M6.4 9.4 12 15l5.6-5.6"/>',
  chevronUp:    '<path d="M6.4 14.6 12 9l5.6 5.6"/>',
  panelLeft:  '<rect x="3.8" y="4.6" width="16.4" height="14.8" rx="2.2"/><path d="M9.6 4.6v14.8"/>',
  panelRight: '<rect x="3.8" y="4.6" width="16.4" height="14.8" rx="2.2"/><path d="M14.4 4.6v14.8"/>',

  /* 사람 */
  user: '<circle cx="12" cy="8.6" r="3.8"/><path d="M4.8 20.2a7.2 7.2 0 0 1 14.4 0"/>',
};

/* ── 조립 ─────────────────────────────────────────── */

/** 인라인 SVG 문자열. html`` 템플릿 안에서 쓴다. */
export function iconHtml(name, size = 16) {
  const d = PATHS[name];
  if (!d) return "";
  return `<svg class="i" viewBox="0 0 24 24" width="${size}" height="${size}"`
       + ` fill="none" stroke="currentColor" stroke-width="1.6"`
       + ` stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
}

/** SVGElement. appendChild 로 붙일 때 쓴다. */
export function icon(name, size = 16) {
  const t = document.createElement("template");
  t.innerHTML = iconHtml(name, size);
  return t.content.firstElementChild;
}

/**
 * 크리미한 그린 그라데이션 박스에 담긴 라인 아이콘.
 * tone: "" | "ok" | "warn" | "err" | "info" | "idle"  (의미 기반 상태색)
 * box:  32 | 40 | 56
 */
export function iconBoxHtml(name, tone = "", box = 32) {
  const cls = box >= 56 ? " lg" : box >= 40 ? " md" : "";
  const glyph = box >= 56 ? 24 : box >= 40 ? 19 : 16;
  return `<div class="icon-box${cls}${tone ? " " + tone : ""}">${iconHtml(name, glyph)}</div>`;
}

export function iconBox(name, tone = "", box = 32) {
  const t = document.createElement("template");
  t.innerHTML = iconBoxHtml(name, tone, box);
  return t.content.firstElementChild;
}

/**
 * `data-icon="name"` 자리표시자를 실제 SVG 로 바꾼다.
 * 마크업(index.html)에 SVG 를 박아 두지 않기 위한 장치.
 * `data-icon-size` 로 크기를 줄 수 있다(기본 17).
 *
 * 주의: 자리표시자는 **교체**된다. 버튼처럼 id·이벤트가 붙는 요소에 직접 달면 그 요소가
 * 사라진다 — 반드시 안쪽에 빈 <span data-icon="…"> 을 두고 그것을 표시자로 쓴다.
 */
export function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((slot) => {
    const name = slot.dataset.icon;
    const size = Number(slot.dataset.iconSize || 17);
    const svg = icon(name, size);
    if (!svg) return;
    slot.replaceWith(svg);
  });
}
