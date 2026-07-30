/* mypage.js — 마이페이지 데이터 로딩
 *
 * 화면은 mypage.php, 데이터는 우리 API. 로직을 API 한 군데에 모으기 위해서다.
 * 그누보드 테마 안에서 돌므로 jQuery 1.12.4 가 이미 로드돼 있지만,
 * 여기서는 쓰지 않는다 — fetch 로 충분하고, jQuery 버전에 묶이면 나중에 아프다.
 */
(function () {
  var root = document.querySelector('.mp');
  if (!root) return;

  /* ⚠ 'sqld' 폴백을 두지 않는다. 문제집이 여러 개인 지금은 폴백이
   *   "다른 문제집을 보고 있는데 SQLD 데이터가 뜨는" 경로가 된다.
   *   빈 값으로 두고 me.php 의 books[0] 으로 정한다. */
  var PD   = root.dataset.pd || '';
  var API  = '/exam/api/';
  var tabs = document.getElementById('mpTabs');
  var panel= document.getElementById('mpPanel');
  var CIRC = '①②③④⑤⑥⑦⑧⑨⑩';

  /* 탭별 응답 캐시 — 탭을 오갈 때마다 다시 부르지 않는다.
   * ★ 키에 PD 를 넣는다. 탭 이름만으로 캐시하면 문제집을 바꿨을 때
   *   이전 문제집의 응시 이력·오답노트가 그대로 남는다. */
  var cache = {};
  function ck(t) { return PD + '|' + t; }

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

  /* ── 문제집 선택 ──────────────────────────────────────────────────
   * me.php 의 books[] 로 그린다. 수강·포인트가 문제집별이라 이용자가 어느 문제집을
   * 보고 있는지 항상 알아야 한다.
   *
   * 선택은 ?pd= 로 이동한다(SPA 로 갈아끼우지 않는다) — 주소를 공유·북마크할 수 있어야
   * 하고, 서버가 data-pd 로 초기값을 내려주는 지금 구조와 어긋나지 않는다.
   */
  function renderBooks(me) {
    var box = document.getElementById('mpBooks');
    if (!box) return;
    var books = me.books || [];

    if (!books.length) {
      box.innerHTML = '<div class="ap-pdbar">' +
        '<span class="ap-pdbar-l">수강 중인 문제집이 없습니다</span>' +
        '<a class="ap-pdchip" href="/exam/">문제집 보러 가기</a></div>';
      return;
    }

    var ST = { pending: '신청 접수', paid: '수강 중', canceled: '취소', refunded: '환불' };
    box.innerHTML = '<div class="ap-pdbar">' +
      '<span class="ap-pdbar-l">내 문제집</span>' +
      books.map(function (b) {
        var on  = (b.pd_id === PD);
        var sub = b.entitled ? (b.count + '개') : (ST[b.status] || '');
        return '<a class="ap-pdchip' + (on ? ' on' : '') + '"' +
               ' href="?pd=' + encodeURIComponent(b.pd_id) + '">' +
               esc(b.pd_name) + (sub ? ' <small>· ' + esc(sub) + '</small>' : '') + '</a>';
      }).join('') +
      '<a class="ap-pdchip" href="/exam/">+ 더 보기</a></div>';
  }

  /* ── 요약 4칸 ────────────────────────────────────────────────────── */
  function renderStats(me, at, wr) {
    /* 남은 질문 — 이제 실제 값이다. 문제집별로 다르다.
     * 아래 note 는 세 경우를 구분한다. 뭉개면 "왜 0인가"를 이용자가 알 수 없다:
     *   · 수강 중 + 차감 OFF → 무료 기간이라 안 줄어든다
     *   · 수강 중 + 차감 ON  → 실제 잔여
     *   · 미수강            → 신청부터 해야 한다 */
    var sel = null, i;
    for (i = 0; i < (me.books || []).length; i++) {
      if (me.books[i].pd_id === PD) { sel = me.books[i]; break; }
    }
    var note;
    if (!sel || !sel.entitled) note = (sel && sel.status === 'pending') ? '승인 대기 중' : '수강 신청이 필요합니다';
    else                       note = '무료 기간 — 차감 없음';

    var cells = [
      { n: at.summary ? at.summary.count : 0, u: '회', l: '응시 횟수' },
      { n: at.summary ? at.summary.avg_pct : 0, u: '점', l: '평균 점수' },
      { n: wr.summary ? wr.summary.still_wrong : 0, u: '개', l: '아직 틀리는 문제' },
      { n: me.count || 0, u: '개', l: '남은 질문', note: note }
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
    /* 행 전체를 성적표 링크로 만든다.
       응시 이력은 점수만 보여주고 끝나는 화면이 아니어야 한다 — 누른 뒤에 분석이 나와야
       "왜 틀렸는지" 로 이어진다. 그게 이 제품이 파는 것이다. */
    return d.items.map(function (a) {
      var href = '/exam/report.php?pd=' + encodeURIComponent(PD) + '&at=' + (a.at_id | 0);
      return '<a class="mp-row mp-row-link" href="' + href + '">' +
        '<div class="mp-row-top">' +
          '<span class="mp-tag blue">' + esc(a.round) + '</span>' +
          '<span class="mp-tag ' + band(a.pct) + '">' + a.correct + ' / ' + a.total + '</span>' +
          (a.filter ? '<span class="mp-tag">' + esc(a.filter) + '</span>' : '') +
          '<span class="mp-when">' + ymd(a.at) + '</span>' +
          '<span class="mp-go">성적표 →</span>' +
        '</div>' +
        '<div class="mp-score">' +
          '<span class="pct">' + a.pct + '%</span>' +
          '<span class="mp-bar"><span style="width:' + a.pct + '%;background:' + bandColor(a.pct) + '"></span></span>' +
        '</div></a>';
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
    /* ★ qna 에도 pd 를 붙인다. 없으면 두 문제집 질문이 한 목록에 섞여
     *   "이 문제집에서 몇 개 물었나"를 알 수 없다. 서버도 pd 로 필터한다. */
    qna:     { url: function () { return 'qna.php?mine=1&pd=' + encodeURIComponent(PD); }, view: viewQna }
  };

  function show(t) {
    var key = ck(t);
    if (cache[key]) { panel.innerHTML = LOAD[t].view(cache[key]); return; }
    panel.innerHTML = '<div class="mp-empty">불러오는 중…</div>';
    get(LOAD[t].url()).then(function (d) {
      if (!d.ok) { panel.innerHTML = empty('불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'); return; }
      cache[key] = d;
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

  /* ── 부팅 ──────────────────────────────────────────────────────────
   * me.php 를 **먼저 단독으로** 부른다. PD 가 비어 있을 수 있고(주소에 ?pd= 가 없을 때)
   * 그 값을 books[0] 에서 받아야 나머지 두 요청의 URL 이 정해진다.
   * 세 개를 한꺼번에 던지면 PD='' 로 나가서 서버가 엉뚱한 기본값을 쓴다.
   *
   * 왕복이 한 번 늘지만 me.php 는 가볍고(잔액 쿼리 몇 개), 틀린 문제집 데이터를
   * 그렸다가 다시 그리는 것보다 낫다.
   */
  get('me.php' + (PD ? '?pd=' + encodeURIComponent(PD) : '')).then(function (me) {
    me = me || {};
    if (!PD && me.pd) PD = me.pd;          // 서버가 고른 문제집을 따른다
    renderBooks(me);

    if (!PD) {                              // 수강 중인 문제집이 하나도 없다
      document.getElementById('mpStats').innerHTML = '';
      panel.innerHTML = empty('아직 신청한 문제집이 없습니다.', ['문제집 보러 가기', '/exam/']);
      return;
    }

    return Promise.all([
      get('attempts.php?pd=' + encodeURIComponent(PD)),
      get('wrong.php?pd=' + encodeURIComponent(PD))
    ]).then(function (r) {
      renderStats(me, r[0] || {}, r[1] || {});
      cache[ck('attempt')] = r[0];
      cache[ck('wrong')]   = r[1];
      show('attempt');
    });
  });
})();
