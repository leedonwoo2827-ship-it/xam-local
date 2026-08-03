/* ============================================================
   WOWPASS UI 키트 — 의존성 0
   · SVG 라인 아이콘 스프라이트 (이모지 대체)
   · 인라인 SVG 차트: donut 게이지 / 가로 막대 / 레이더
   사용:
     <svg class="ic"><use href="#i-download"></use></svg>
     WPUI.donut({pct, label, sub, color})  → SVG 문자열
   ============================================================ */
(function (global) {
  "use strict";

  /* ---------------- 아이콘 스프라이트 ---------------- */
  const ICONS = {
    "download": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4.5 20h15"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="16" rx="2.5"/><path d="M3.5 9.5h17"/><path d="M8 3v4M16 3v4"/>',
    "clipboard": '<rect x="5" y="4.5" width="14" height="17" rx="2.5"/><path d="M9 4.5a3 3 0 0 1 6 0"/><path d="M8.5 11.5h7M8.5 15.5h4.5"/>',
    "clipboard-check": '<rect x="5" y="4.5" width="14" height="17" rx="2.5"/><path d="M9 4.5a3 3 0 0 1 6 0"/><path d="M8.7 13.6l1.9 1.9 3.7-3.9"/>',
    "chart": '<path d="M4 20h16"/><path d="M6.5 20v-7"/><path d="M12 20V5"/><path d="M17.5 20v-10"/>',
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="2.5"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9.5 3v3M14.5 3v3M9.5 18v3M14.5 18v3M3 9.5h3M3 14.5h3M18 9.5h3M18 14.5h3"/>',
    "bell": '<path d="M6 9.5a6 6 0 0 1 12 0c0 4.5 1.8 5.5 1.8 5.5H4.2S6 14 6 9.5z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
    "trophy": '<path d="M8 4.5h8v4.5a4 4 0 0 1-8 0z"/><path d="M8 5.5H5v1.5a3 3 0 0 0 3 3M16 5.5h3v1.5a3 3 0 0 1-3 3"/><path d="M12 13.5v3.5M9.5 20.5h5M10.5 17h3"/>',
    "map": '<path d="M9 4 4 6.2v13.6L9 17.6l6 2.2 5-2.2V4.2L15 6.4 9 4z"/><path d="M9 4v13.6M15 6.4v13.4"/>',
    "target": '<circle cx="12" cy="12" r="8.2"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.9" fill="currentColor" stroke="none"/>',
    "search": '<circle cx="11" cy="11" r="6.4"/><path d="M20 20l-4.2-4.2"/>',
    "flag": '<path d="M6 21V4"/><path d="M6 4.5h11l-2 4 2 4H6"/>',
    "doc": '<path d="M7 3.5h7l5 5V20.5H7z"/><path d="M14 3.5V8.5h5"/><path d="M9.5 13h6M9.5 16.5h4"/>',
    "edit": '<path d="M5 19.5h14"/><path d="M15.5 5l3 3L9 17.5l-4 1 1-4z"/>',
    "check": '<path d="M5 12.5l4.4 4.4L19 7"/>',
    "check-circle": '<circle cx="12" cy="12" r="8.4"/><path d="M8.4 12.4l2.5 2.5 4.6-5"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-13.7-5L4 8"/><path d="M4 3.5V8h4.5"/><path d="M4 13a8 8 0 0 0 13.7 5L20 16"/><path d="M20 20.5V16h-4.5"/>',
    "box": '<path d="M3.6 7.5 12 4l8.4 3.5v9L12 20l-8.4-3.5z"/><path d="M3.6 7.5 12 11l8.4-3.5M12 11v9"/>',
    "gift": '<rect x="4" y="9.5" width="16" height="10.5" rx="1.5"/><path d="M3 9.5h18M12 9.5v10.5"/><path d="M12 9.5C11 6 9 6 8.2 7c-.8 1 .3 2.5 3.8 2.5zM12 9.5c1-3.5 3-3.5 3.8-2.5.8 1-.3 2.5-3.8 2.5z"/>',
    "medal": '<circle cx="12" cy="14" r="5"/><path d="M9.2 9.7 7 3.5h10l-2.2 6.2"/><path d="M12 11.7l.9 1.8 2 .3-1.4 1.4.3 2-1.8-1-1.8 1 .3-2-1.4-1.4 2-.3z"/>',
    "book": '<path d="M5 4.5h11a2 2 0 0 1 2 2v13H7a2 2 0 0 1-2-2z"/><path d="M5 17.5a2 2 0 0 1 2-2h11"/>',
    "receipt": '<path d="M6 3.5h12v17l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3z"/><path d="M9 8h6M9 11.5h6"/>',
    "cap": '<path d="M2.5 9 12 5.2 21.5 9 12 12.8z"/><path d="M6 10.8V15c0 1.5 2.7 2.6 6 2.6s6-1.1 6-2.6v-4.2"/><path d="M21.5 9v4.5"/>',
    "user": '<circle cx="12" cy="8.4" r="3.7"/><path d="M5.2 20c0-3.5 3-6 6.8-6s6.8 2.5 6.8 6"/>',
    "help": '<circle cx="12" cy="12" r="8.4"/><path d="M9.6 9.4a2.5 2.5 0 0 1 4.6 1.4c0 1.7-2 2-2 3.3"/><circle cx="12" cy="16.6" r="0.7" fill="currentColor" stroke="none"/>',
    "logout": '<path d="M14 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2H14"/><path d="M17.5 8l4 4-4 4"/><path d="M21.5 12H10"/>',
    "play": '<circle cx="12" cy="12" r="8.4"/><path d="M10.3 8.6l5 3.4-5 3.4z" fill="currentColor" stroke="none"/>',
    "shield": '<path d="M12 3.5 19 6v5c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "bulb": '<path d="M9.2 17.5h5.6M10.2 20.5h3.6"/><path d="M7.5 10.8a4.5 4.5 0 1 1 9 0c0 2-1.6 3-2.1 4.7H9.6C9.1 13.8 7.5 12.8 7.5 10.8z"/>',
    "rocket": '<path d="M12 3.2c3 1.6 4.8 4.6 4.8 8 0 2-.9 3.8-1.8 4.8H9c-.9-1-1.8-2.8-1.8-4.8 0-3.4 1.8-6.4 4.8-8z"/><circle cx="12" cy="9.4" r="1.6"/><path d="M9 16.2l-2 4 3-1.2M15 16.2l2 4-3-1.2"/>',
    "calculator": '<rect x="5" y="3.5" width="14" height="17" rx="2"/><rect x="8" y="6.5" width="8" height="3" rx="1"/><path d="M9 13h.02M12 13h.02M15 13h.02M9 16.5h.02M12 16.5h.02M15 16.5h.02"/>',
    "list": '<path d="M8.5 7h11M8.5 12h11M8.5 17h11"/><path d="M4.5 7h.02M4.5 12h.02M4.5 17h.02"/>',
    "chevron": '<path d="M9.5 6l6 6-6 6"/>',
    "arrow-right": '<path d="M4.5 12h15M13.5 6l6 6-6 6"/>',
    "info": '<circle cx="12" cy="12" r="8.4"/><path d="M12 11v5.2"/><circle cx="12" cy="7.8" r="0.7" fill="currentColor" stroke="none"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
    "send": '<path d="M21 4 3 11l6 2.5L12 20l3-6 6-10z"/><path d="M9 13.5 21 4"/>',
    "sparkle": '<path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 14l.7 1.8 1.8.7-1.8.7L19 19l-.7-1.8-1.8-.7 1.8-.7z" stroke-width="1.2"/>',
  };

  function buildSprite() {
    let symbols = "";
    for (const id in ICONS) {
      symbols += '<symbol id="i-' + id + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
                 'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + ICONS[id] + '</symbol>';
    }
    return '<svg class="svg-sprite" aria-hidden="true">' + symbols + '</svg>';
  }

  function injectSprite() {
    if (document.getElementById("wp-sprite")) return;
    const div = document.createElement("div");
    div.id = "wp-sprite";
    div.innerHTML = buildSprite();
    document.body.insertBefore(div.firstChild, document.body.firstChild);
  }

  /* ---------------- 차트: 도넛 게이지 ---------------- */
  function donut(o) {
    o = o || {};
    const size = o.size || 132, stroke = o.stroke || 13;
    const pct = Math.max(0, Math.min(100, o.pct || 0));
    const color = o.color || "var(--blue-600)";
    const track = o.track || "var(--surface-strong)";
    const r = (size - stroke) / 2, c = 2 * Math.PI * r, off = c * (1 - pct / 100), cx = size / 2;
    return '<svg class="chart-donut" viewBox="0 0 ' + size + ' ' + size + '" width="' + size + '" height="' + size + '" role="img">' +
      '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="' + track + '" stroke-width="' + stroke + '"/>' +
      '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="' + stroke + '" ' +
        'stroke-linecap="round" stroke-dasharray="' + c.toFixed(1) + '" stroke-dashoffset="' + off.toFixed(1) + '" ' +
        'transform="rotate(-90 ' + cx + ' ' + cx + ')" style="transition:stroke-dashoffset .8s cubic-bezier(.2,.7,.3,1)"/>' +
      (o.label != null ? '<text x="' + cx + '" y="' + (cx + (o.sub ? -2 : 6)) + '" text-anchor="middle" class="cd-val" fill="' + (o.labelColor || "var(--ink)") + '">' + o.label + '</text>' : '') +
      (o.sub ? '<text x="' + cx + '" y="' + (cx + 18) + '" text-anchor="middle" class="cd-sub" fill="var(--muted)">' + o.sub + '</text>' : '') +
    '</svg>';
  }

  /* ---------------- 차트: 가로 막대 ---------------- */
  function hbars(o) {
    o = o || {}; const items = o.items || []; const max = o.max || 100;
    const w = o.width || 460, rowH = 46, padL = 0, barH = 10, top = 6;
    const h = items.length * rowH + 8;
    let svg = '<svg class="chart-hbars" viewBox="0 0 ' + w + ' ' + h + '" width="100%" height="' + h + '" preserveAspectRatio="xMinYMin meet">';
    items.forEach(function (it, i) {
      const y = i * rowH + top;
      const val = Math.max(0, Math.min(max, it.value));
      const bw = (w - padL) * (val / max);
      const color = it.color || "var(--blue-600)";
      svg += '<text x="0" y="' + (y + 4) + '" class="hb-label">' + it.label + '</text>';
      svg += '<text x="' + w + '" y="' + (y + 4) + '" text-anchor="end" class="hb-val" fill="' + color + '">' + (it.valueLabel != null ? it.valueLabel : val + '%') + '</text>';
      svg += '<rect x="' + padL + '" y="' + (y + 14) + '" width="' + (w - padL) + '" height="' + barH + '" rx="5" fill="var(--surface-strong)"/>';
      svg += '<rect x="' + padL + '" y="' + (y + 14) + '" width="' + bw.toFixed(1) + '" height="' + barH + '" rx="5" fill="' + color + '"><animate attributeName="width" from="0" to="' + bw.toFixed(1) + '" dur="0.7s" fill="freeze"/></rect>';
    });
    return svg + '</svg>';
  }

  /* ---------------- 차트: 레이더 ---------------- */
  function radar(o) {
    o = o || {}; const axes = o.axes || []; const max = o.max || 100; const size = o.size || 260;
    const cx = size / 2, cy = size / 2 + 4, R = size / 2 - 50, n = axes.length;
    const ang = i => (-90 + i * 360 / n) * Math.PI / 180;
    const pt = (i, v) => [cx + Math.cos(ang(i)) * R * v, cy + Math.sin(ang(i)) * R * v];
    const lpt = (i) => [cx + Math.cos(ang(i)) * (R + 22), cy + Math.sin(ang(i)) * (R + 22)];
    let svg = '<svg class="chart-radar" viewBox="0 0 ' + size + ' ' + size + '" width="' + size + '" height="' + size + '">';
    // grid rings
    [0.34, 0.67, 1].forEach(function (ring) {
      let p = "";
      for (let i = 0; i < n; i++) { const [x, y] = pt(i, ring); p += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1) + " "; }
      svg += '<path d="' + p + 'Z" fill="none" stroke="var(--hairline-strong)" stroke-width="1"/>';
    });
    // spokes + labels
    for (let i = 0; i < n; i++) {
      const [x, y] = pt(i, 1);
      svg += '<line x1="' + cx + '" y1="' + cy + '" x2="' + x.toFixed(1) + '" y2="' + y.toFixed(1) + '" stroke="var(--hairline-strong)" stroke-width="1"/>';
      const [lx, ly] = lpt(i);
      const anchor = Math.abs(lx - cx) < 6 ? "middle" : (lx > cx ? "start" : "end");
      svg += '<text x="' + lx.toFixed(1) + '" y="' + (ly + 4).toFixed(1) + '" text-anchor="' + anchor + '" class="rd-label">' + axes[i].label + '</text>';
    }
    // data polygon
    let dp = "";
    for (let i = 0; i < n; i++) { const [x, y] = pt(i, Math.max(0.04, axes[i].value / max)); dp += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1) + " "; }
    svg += '<path d="' + dp + 'Z" fill="rgba(44,92,230,.16)" stroke="var(--blue-600)" stroke-width="2" stroke-linejoin="round"/>';
    for (let i = 0; i < n; i++) { const [x, y] = pt(i, Math.max(0.04, axes[i].value / max)); svg += '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="3.4" fill="var(--blue-600)"/>'; }
    return svg + '</svg>';
  }

  /* ── 헤더 로그인 상태 (정적 페이지 전용) ────────────────────────────────
     index.html·detail.html 은 정적 파일이라 서버가 로그인 상태를 그릴 수 없다.
     그래서 로그인한 회원이 /exam/ 에 오면 [로그인] 버튼이 그대로 보였다.

     ★ `data-authswap="1"` 이 붙은 nav 만 건드린다.
       그누보드 화면(theme/axexam/head.php)은 서버에서 이미 정확히 그리므로
       거기까지 갈아끼우면 깜빡이고 두 번 그리는 셈이 된다.

     실패(네트워크·비로그인)하면 아무것도 하지 않는다 — 기본 마크업이
     비로그인 상태이므로 그게 안전한 폴백이다. */
  function authSwap() {
    var nav = document.querySelector('.axnav-util[data-authswap="1"]');
    var box = nav && nav.querySelector('.axnav-auth');
    if (!box) return;

    fetch('/exam/api/me.php', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok || !d.login) return;             // 비로그인 = 기본 마크업 그대로
        var nick = String(d.nick || d.mb_id || '')
          .replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
          });
        box.innerHTML =
            '<span class="axnav-me"><b>' + nick + '</b>님</span>'
          + '<a class="axnav-item" href="/exam/mypage.php">'
          +   '<svg class="ic"><use href="#i-user"></use></svg>마이페이지</a>'
          + (d.admin ? '<a class="axnav-item" href="/adm/">'
          +   '<svg class="ic"><use href="#i-shield"></use></svg>관리자</a>' : '')
          /* 로그아웃 후 갈 곳을 명시한다 — head.php 와 같은 규칙.
             url 에 도메인을 넣으면 logout.php 가 거부하므로 경로만 준다. */
          + '<a class="axnav-cta" href="/bbs/logout.php?url=' + encodeURIComponent('/exam/') + '">로그아웃</a>';
      })
      .catch(function () { /* 조용히 비로그인 상태로 둔다 */ });
  }

  global.WPUI = { injectSprite: injectSprite, donut: donut, hbars: hbars, radar: radar,
                  authSwap: authSwap };

  if (typeof document !== "undefined") {
    function boot() { injectSprite(); authSwap(); }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
  }
})(window);
