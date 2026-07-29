/* mypage.js — 마이페이지 데이터 로딩
 *
 * 화면은 mypage.php, 데이터는 우리 API. 로직을 API 한 군데에 모으기 위해서다.
 * 그누보드 테마 안에서 돌므로 jQuery 1.12.4 가 이미 로드돼 있지만,
 * 여기서는 쓰지 않는다 — fetch 로 충분하고, jQuery 버전에 묶이면 나중에 아프다.
 */
(function () {
  var root = document.querySelector('.mp');
  if (!root) return;

  var PD   = root.dataset.pd || 'sqld';
  var API  = '/exam/api/';
  var tabs = document.getElementById('mpTabs');
  var panel= document.getElementById('mpPanel');
  var CIRC = '①②③④⑤⑥⑦⑧⑨⑩';
  var cache = {};          // 탭별 응답 캐시 — 탭을 오갈 때마다 다시 부르지 않는다

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
      });
  }
  function ymd(s) { return String(s || '').slice(0, 16).replace('T', ' '); }
  function band(p) { return p >= 70 ? 'good' : (p >= 50 ? 'mid' : 'bad'); }
  function bandColor(p) {
    return p >= 70 ? 'var(--c-good)' : (p >= 50 ? 'var(--c-mid)' : 'var(--c-bad)');
  }

  function get(path) {
    return fetch(API + path, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .catch(function () { return { ok: 0 }; });
  }

  function empty(msg, link) {
    return '<div class="mp-empty">' + msg +
      (link ? '<br><br><a href="' + link[1] + '">' + link[0] + '</a>' : '') + '</div>';
  }

  /* ── 요약 4칸 ────────────────────────────────────────────────────── */
  function renderStats(me, at, wr) {
    var cells = [
      { n: at.summary ? at.summary.count : 0, u: '회', l: '응시 횟수' },
      { n: at.summary ? at.summary.avg_pct : 0, u: '점', l: '평균 점수' },
      { n: wr.summary ? wr.summary.still_wrong : 0, u: '개', l: '아직 틀리는 문제' },
      /* ⚠ 크레딧(S6) 미적용이라 항상 0 이다. 숨기지 않고 사실대로 적는다. */
      { n: me.count || 0, u: '개', l: '남은 질문', note: '무료 기간 — 차감 없음' }
    ];
    document.getElementById('mpStats').innerHTML = cells.map(function (c) {
      return '<div class="mp-stat"><div class="n">' + c.n +
        '<small>' + c.u + '</small></div><div class="l">' + c.l + '</div>' +
        (c.note ? '<div class="note">' + c.note + '</div>' : '') + '</div>';
    }).join('');
  }

  /* ── 응시 이력 ───────────────────────────────────────────────────── */
  function viewAttempt(d) {
    if (!d.items || !d.items.length) {
      return empty('아직 응시 기록이 없습니다.',
        ['1회차 풀어보기', '/exam/check.html?pd=' + encodeURIComponent(PD)]);
    }
    return d.items.map(function (a) {
      return '<div class="mp-row">' +
        '<div class="mp-row-top">' +
          '<span class="mp-tag blue">' + esc(a.round) + '</span>' +
          '<span class="mp-tag ' + band(a.pct) + '">' + a.correct + ' / ' + a.total + '</span>' +
          (a.filter ? '<span class="mp-tag">' + esc(a.filter) + '</span>' : '') +
          '<span class="mp-when">' + ymd(a.at) + '</span>' +
        '</div>' +
        '<div class="mp-score">' +
          '<span class="pct">' + a.pct + '%</span>' +
          '<span class="mp-bar"><span style="width:' + a.pct + '%;background:' + bandColor(a.pct) + '"></span></span>' +
        '</div></div>';
    }).join('');
  }

  /* ── 오답노트 ────────────────────────────────────────────────────── */
  function viewWrong(d) {
    if (!d.items || !d.items.length) {
      return empty('오답이 없습니다. 아직 채점한 적이 없거나, 전부 맞히셨습니다.',
        ['문제 풀러 가기', '/exam/check.html?pd=' + encodeURIComponent(PD)]);
    }
    return d.items.map(function (p, i) {
      var opts = (p.choices || []).map(function (t, k) {
        var cls = (k === p.answer_index) ? ' ok' : (k === p.last_chosen ? ' no' : '');
        return '<div class="mp-opt' + cls + '"><span class="n">' + (CIRC[k] || (k + 1)) +
               '</span><span>' + esc(t) + '</span></div>';
      }).join('');
      return '<div class="mp-row">' +
        '<div class="mp-row-top">' +
          '<span class="mp-tag blue">' + esc(p.round) + ' ' + p.number + '번</span>' +
          '<span class="mp-tag">' + esc(p.subject) + '</span>' +
          '<span class="mp-tag bad">' + p.wrong_cnt + '번 틀림</span>' +
          '<span class="mp-when">' + p.try_cnt + '번 풂 · ' + ymd(p.at) + '</span>' +
        '</div>' +
        '<div class="mp-q">' + esc(p.question) + '</div>' +
        '<div class="mp-opts">' + opts + '</div>' +
        (p.explanation
          ? '<span class="mp-more" data-x="' + i + '">해설 보기</span>' +
            '<div class="mp-a" id="ex' + i + '" style="display:none">' + esc(p.explanation) + '</div>'
          : '') +
        '</div>';
    }).join('');
  }

  /* ── 내 질문 ─────────────────────────────────────────────────────── */
  var ST = {
    pending:     ['', '답변 대기'],
    drafting:    ['', '답변 준비 중'],
    draft_ready: ['', '답변 준비 중'],   // 초안 상태는 이용자에게 '준비 중'으로만 보인다
    approved:    ['good', '답변 완료'],
    rejected:    ['bad', '반려']
  };
  function viewQna(d) {
    if (!d.items || !d.items.length) {
      return empty('아직 질문이 없습니다. 문제를 풀다 막히면 그 자리에서 질문할 수 있습니다.',
        ['문제 풀러 가기', '/exam/check.html?pd=' + encodeURIComponent(PD)]);
    }
    return d.items.map(function (q) {
      var s = ST[q.status] || ['', q.status];
      return '<div class="mp-row">' +
        '<div class="mp-row-top">' +
          '<span class="mp-tag ' + s[0] + '">' + s[1] + '</span>' +
          (q.pr_key ? '<span class="mp-tag blue">' + esc(q.pr_key) + '</span>' : '') +
          (q.kind === 'report' ? '<span class="mp-tag mid">오류 신고</span>' : '') +
          '<span class="mp-when">' + ymd(q.at) + '</span>' +
        '</div>' +
        '<div class="mp-q">' + esc(q.question) + '</div>' +
        (q.answer ? '<div class="mp-a">' + esc(q.answer) + '</div>' : '') +
        '</div>';
    }).join('');
  }

  /* ── 탭 ──────────────────────────────────────────────────────────── */
  var LOAD = {
    attempt: { url: function () { return 'attempts.php?pd=' + encodeURIComponent(PD); }, view: viewAttempt },
    wrong:   { url: function () { return 'wrong.php?pd=' + encodeURIComponent(PD); },    view: viewWrong },
    qna:     { url: function () { return 'qna.php?mine=1'; },                             view: viewQna }
  };

  function show(t) {
    if (cache[t]) { panel.innerHTML = LOAD[t].view(cache[t]); return; }
    panel.innerHTML = '<div class="mp-empty">불러오는 중…</div>';
    get(LOAD[t].url()).then(function (d) {
      if (!d.ok) { panel.innerHTML = empty('불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'); return; }
      cache[t] = d;
      panel.innerHTML = LOAD[t].view(d);
    });
  }

  tabs.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-t]');
    if (!b) return;
    tabs.querySelectorAll('button').forEach(function (x) { x.classList.remove('on'); });
    b.classList.add('on');
    show(b.dataset.t);
  });

  // 해설 펼치기
  panel.addEventListener('click', function (e) {
    var m = e.target.closest('.mp-more');
    if (!m) return;
    var box = document.getElementById('ex' + m.dataset.x);
    if (!box) return;
    var open = box.style.display !== 'none';
    box.style.display = open ? 'none' : '';
    m.textContent = open ? '해설 보기' : '해설 접기';
  });

  /* ── 부팅 ────────────────────────────────────────────────────────── */
  Promise.all([
    get('me.php'),
    get('attempts.php?pd=' + encodeURIComponent(PD)),
    get('wrong.php?pd=' + encodeURIComponent(PD))
  ]).then(function (r) {
    renderStats(r[0] || {}, r[1] || {}, r[2] || {});
    cache.attempt = r[1];
    cache.wrong   = r[2];
    show('attempt');
  });
})();
