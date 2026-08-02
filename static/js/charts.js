/* 차트 — 의존성 0 인라인 SVG.
 *
 * 색은 CSS 변수만 참조한다(토큰을 바꾸면 차트가 따라온다). 팔레트는 dataviz 검증기로
 * 확인했다 — 상태 3색 #2a7a4c / #c9911f / #9d2f26 은 6개 검사 전부 통과하고,
 * 산출물 제출 상태처럼 '순서가 있는' 값은 카테고리 색 4개가 아니라 명도가 단조 감소하는
 * 단일 색조 램프(--c-seq-1..4)로 그린다.
 *
 * 규칙:
 *  - 마크는 얇게, 값 끝은 4px 라운드
 *  - 쌓인 조각 사이는 2px 서피스 간격(색만으로 구분하지 않는다)
 *  - 숫자·라벨은 텍스트 토큰 색을 쓴다(시리즈 색을 글자에 쓰지 않는다)
 *  - 모든 차트에 role="img" + <title> + 화면에 안 보이는 텍스트 요약(.a11y)
 */
"use strict";

import { el, escapeHtml } from "./util.js";

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const num = (v) => (Number.isFinite(+v) ? +v : 0);

/** 문자열 SVG → 요소. template 안에서는 HTML 파서가 svg 네임스페이스를 알아서 잡는다. */
function svgEl(markup) {
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstElementChild;
}

/** 차트 + 스크린리더용 텍스트 요약을 한 덩어리로 감싼다. */
function wrap(markup, summary) {
  const box = el("div", "chart-wrap");
  box.appendChild(svgEl(markup));
  if (summary) box.appendChild(el("p", "a11y", summary));
  return box;
}

/* ══ 도넛 — 단일 진척값 ═══════════════════════════════════════════════════
   퍼센트 하나를 보여주는 자리. 큰 숫자를 가운데 두고 링은 얇게.
   pct 가 null 이면 '—' 를 띄운다(데이터 미입력과 0% 는 다르다). */
export function donut(pct, { label = "", size = 78, tone = "" } = {}) {
  const has = pct != null && Number.isFinite(+pct);
  const p = has ? clamp(Math.round(+pct), 0, 100) : 0;
  const stroke = 7;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const mid = size / 2;
  const color = tone === "warn" ? "var(--c-warn)"
              : tone === "err"  ? "var(--c-crit)"
              : "var(--c-seq-4)";
  const title = `${label || "진척"} ${has ? p + "%" : "데이터 없음"}`;

  return wrap(`
    <svg class="chart" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}"
         role="img" aria-label="${escapeHtml(title)}">
      <title>${escapeHtml(title)}</title>
      <circle cx="${mid}" cy="${mid}" r="${r}" fill="none"
              stroke="var(--c-track)" stroke-width="${stroke}"/>
      ${has && p > 0 ? `<circle cx="${mid}" cy="${mid}" r="${r}" fill="none"
              stroke="${color}" stroke-width="${stroke}" stroke-linecap="round"
              stroke-dasharray="${(c * p / 100).toFixed(2)} ${c.toFixed(2)}"
              transform="rotate(-90 ${mid} ${mid})"/>` : ""}
      <text x="${mid}" y="${mid}" text-anchor="middle" dominant-baseline="central"
            fill="var(--text)" font-family="var(--font)" font-size="${Math.round(size * 0.26)}"
            font-weight="700" style="font-variant-numeric:tabular-nums">${has ? p + "%" : "—"}</text>
    </svg>`, title);
}

/* ══ 쌓인 가로 바 — 순서가 있는 상태 분포 ════════════════════════════════
   segments: [{ label, value, seq }]  seq 1(옅음)~4(진함)
   조각 사이에 2px 서피스 간격을 둬서 색만으로 경계를 읽지 않게 한다. */
export function stackedBar(segments, { height = 12, gap = 2 } = {}) {
  const rows = segments.filter((s) => num(s.value) > 0);
  const total = rows.reduce((a, s) => a + num(s.value), 0);
  if (!total) return el("div", "empty", "표시할 값이 없습니다.");

  const W = 1000;                                   // viewBox 기준폭(반응형은 CSS 가 처리)
  const gaps = Math.max(0, rows.length - 1) * gap;
  const usable = W - gaps;
  let x = 0;
  const bars = rows.map((s) => {
    const w = Math.max(2, (num(s.value) / total) * usable);
    const seg = `<rect x="${x.toFixed(1)}" y="0" width="${w.toFixed(1)}" height="${height}"
        rx="2" fill="var(--c-seq-${clamp(num(s.seq) || 4, 1, 4)})"><title>${
        escapeHtml(`${s.label} ${s.value}건 · ${Math.round(num(s.value) / total * 100)}%`)}</title></rect>`;
    x += w + gap;
    return seg;
  }).join("");

  const summary = rows.map((s) => `${s.label} ${s.value}건`).join(", ");
  return wrap(`
    <svg class="chart" viewBox="0 0 ${W} ${height}" preserveAspectRatio="none"
         width="100%" height="${height}" role="img" aria-label="${escapeHtml(summary)}">
      <title>${escapeHtml(summary)}</title>${bars}
    </svg>`, `상태 분포: ${summary}. 전체 ${total}건.`);
}

/* ══ 가로 막대 — 등급·범주별 건수 ════════════════════════════════════════
   rows: [{ label, value, tone }]  tone: "" | "warn" | "err"
   각 막대에 라벨과 숫자를 직접 붙인다(색만으로 구분하지 않는다).

   라벨·숫자는 HTML 로 두고 막대만 SVG 로 그린다. 폭에 맞춰 늘리는 SVG 안에 글자를 넣으면
   가로로 눌려 찌그러지기 때문이다(간트 축도 같은 이유로 HTML 이다). */
export function hbar(rows, { max = null } = {}) {
  if (!rows.length) return el("div", "empty", "표시할 값이 없습니다.");
  const top = max != null ? num(max) : Math.max(1, ...rows.map((r) => num(r.value)));
  const grid = el("div", "hbar");
  const H = 10;

  rows.forEach((r) => {
    grid.appendChild(el("div", "hbar-label", r.label));

    const w = (num(r.value) / top) * 1000;      // viewBox 단위(0~1000)로 바로 계산한다
    const fill = r.tone === "err" ? "var(--c-crit)"
               : r.tone === "warn" ? "var(--c-warn)"
               : "var(--c-seq-3)";
    grid.appendChild(svgEl(`
      <svg class="chart" viewBox="0 0 1000 ${H}" preserveAspectRatio="none"
           width="100%" height="${H}" role="img"
           aria-label="${escapeHtml(`${r.label} ${r.value}건`)}">
        <title>${escapeHtml(`${r.label} ${r.value}건`)}</title>
        <rect x="0" y="0" width="1000" height="${H}" rx="5" fill="var(--c-track)"/>
        ${num(r.value) > 0
          ? `<rect x="0" y="0" width="${Math.max(12, w).toFixed(1)}" height="${H}" rx="4" fill="${fill}"/>`
          : ""}
      </svg>`));

    grid.appendChild(el("div", "hbar-value", String(num(r.value))));
  });

  const summary = rows.map((r) => `${r.label} ${r.value}건`).join(", ");
  grid.appendChild(el("p", "a11y", summary));
  return grid;
}

/* ══ 스파크라인 — 최근 추이 ══════════════════════════════════════════════
   points: [{ label, value }]  단일 시리즈라 범례를 두지 않는다(제목이 이름을 말한다). */
export function sparkline(points, { height = 44 } = {}) {
  const pts = points.filter(Boolean);
  if (pts.length < 2) return el("div", "empty", "추이를 그릴 만큼 자료가 모이지 않았습니다.");

  const W = 1000, pad = 4;
  const top = Math.max(1, ...pts.map((p) => num(p.value)));
  const stepX = (W - pad * 2) / (pts.length - 1);
  const y = (v) => pad + (1 - num(v) / top) * (height - pad * 2);
  const xy = pts.map((p, i) => [pad + i * stepX, y(p.value)]);
  const line = xy.map(([x, yy], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${yy.toFixed(1)}`).join(" ");
  const area = `${line} L${xy[xy.length - 1][0].toFixed(1)} ${height} L${xy[0][0].toFixed(1)} ${height} Z`;
  const last = xy[xy.length - 1];

  const dots = pts.map((p, i) => `<circle cx="${xy[i][0].toFixed(1)}" cy="${xy[i][1].toFixed(1)}"
      r="8" fill="transparent"><title>${escapeHtml(`${p.label} ${p.value}건`)}</title></circle>`).join("");

  const summary = pts.map((p) => `${p.label} ${p.value}건`).join(", ");
  return wrap(`
    <svg class="chart" viewBox="0 0 ${W} ${height}" preserveAspectRatio="none"
         width="100%" height="${height}" role="img" aria-label="${escapeHtml(summary)}">
      <title>${escapeHtml(summary)}</title>
      <path d="${area}" fill="var(--c-seq-1)" opacity=".55"/>
      <path d="${line}" fill="none" stroke="var(--c-seq-4)" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
      <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3.2" fill="var(--c-seq-4)"
              stroke="var(--bone)" stroke-width="2" vector-effect="non-scaling-stroke"/>
      ${dots}
    </svg>`, `최근 추이 — ${summary}`);
}

/* ══ 간트 스트립 — 파견 차수 일정 ════════════════════════════════════════
   rows: [{ name, sub, startPct, endPct, done, badge }]  (퍼센트는 호출부가 계산해 넘긴다)
   행마다 같은 x 스케일의 SVG 를 쓰므로 월 격자선이 세로로 자연히 맞는다.
   '예정'은 옅은 단계, '완료'는 진한 단계 — 명도 차로 읽히게 두고 배지로 한 번 더 말해 준다. */
export function ganttStrip(rows, { ticks = [], todayPct = null } = {}) {
  const grid = el("div", "gantt");
  const W = 1000, H = 16, barH = 9;

  const gridlines = ticks.map((t) =>
    `<line x1="${(t.pct * 10).toFixed(1)}" y1="0" x2="${(t.pct * 10).toFixed(1)}" y2="${H}"
           stroke="var(--hairline-2)" stroke-width="1" vector-effect="non-scaling-stroke"/>`).join("");
  const today = todayPct != null && todayPct >= 0 && todayPct <= 100
    ? `<line x1="${(todayPct * 10).toFixed(1)}" y1="0" x2="${(todayPct * 10).toFixed(1)}" y2="${H}"
             stroke="var(--c-crit)" stroke-width="1.5" stroke-dasharray="2 2"
             vector-effect="non-scaling-stroke"/>` : "";

  rows.forEach((r) => {
    const name = el("div", "gantt-name");
    name.innerHTML = `<b>${escapeHtml(String(r.name))}</b>`
      + (r.sub ? ` <span class="muted">${escapeHtml(r.sub)}</span>` : "");
    name.title = r.sub || String(r.name);
    grid.appendChild(name);

    const left = clamp(num(r.startPct), 0, 100);
    // 아주 짧은 파견(며칠)이 사업 전체 기간에 눌려 사라지지 않게 최소 폭을 준다
    const width = Math.max(1.2, clamp(num(r.endPct), 0, 100) - left);
    const fill = r.done ? "var(--c-seq-4)" : "var(--c-seq-2)";
    grid.appendChild(svgEl(`
      <svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"
           width="100%" height="${H}" role="img"
           aria-label="${escapeHtml(`${r.name} ${r.badge || ""}`)}">
        <title>${escapeHtml(`${r.name}${r.sub ? " · " + r.sub : ""}${r.badge ? " · " + r.badge : ""}`)}</title>
        <rect x="0" y="${(H - barH) / 2}" width="${W}" height="${barH}" rx="4.5" fill="var(--c-track)"/>
        ${gridlines}
        <rect x="${(left * 10).toFixed(1)}" y="${(H - barH) / 2}" width="${(width * 10).toFixed(1)}"
              height="${barH}" rx="4" fill="${fill}"/>
        ${today}
      </svg>`));

    const end = el("div", "gantt-end");
    end.innerHTML = r.badgeHtml || "";
    grid.appendChild(end);
  });

  // 축 — 라벨 열 아래는 비우고 트랙 열에만 월 눈금을 적는다.
  // 눈금 글자는 HTML 로 둔다(폭에 맞춰 늘어나는 SVG 안의 글자는 가로로 찌그러진다).
  if (ticks.length) {
    grid.appendChild(el("div"));
    const axis = el("div", "gantt-axis");
    axis.setAttribute("aria-hidden", "true");
    ticks.forEach((t) => {
      const s = el("span", null, t.label);
      s.style.left = clamp(t.pct, 0, 100) + "%";
      axis.appendChild(s);
    });
    grid.appendChild(axis);
    grid.appendChild(el("div"));
  }
  return grid;
}

/* ══ 월 눈금 만들기 ══════════════════════════════════════════════════════
   전체 기간(min~max)에 대해 월초 위치를 퍼센트로 돌려준다. 기간이 길면 눈금을 솎는다. */
export function monthTicks(min, max) {
  if (!(min instanceof Date) || !(max instanceof Date)) return [];
  const span = (max - min) / 86400000;
  if (span <= 0) return [];
  const out = [];
  const cur = new Date(min.getFullYear(), min.getMonth(), 1);
  if (cur < min) cur.setMonth(cur.getMonth() + 1);
  while (cur <= max) {
    out.push({ date: new Date(cur), pct: ((cur - min) / 86400000 / span) * 100 });
    cur.setMonth(cur.getMonth() + 1);
  }
  const every = out.length > 14 ? 3 : out.length > 8 ? 2 : 1;
  return out.filter((_, i) => i % every === 0).map((t) => ({
    pct: t.pct,
    label: t.date.getMonth() === 0
      ? `${String(t.date.getFullYear()).slice(2)}년`
      : `${t.date.getMonth() + 1}월`,
  }));
}
