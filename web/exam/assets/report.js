/* report.js — 성적표(분석 리포트) 렌더링
 *
 * 데이터는 api/report.php 한 번 호출로 다 온다. LLM 을 쓰지 않는다 — 집계 쿼리다.
 *
 * 설계 원칙
 *  · 판정은 **색만으로 표현하지 않는다.** 색약 이용자에게 색은 정보가 아니므로
 *    막대 색과 함께 '양호/보완/미달' 글자를 붙인다.
 *  · 미응답이 많으면 점수보다 그 사실을 먼저 말한다. 40문항 비운 45점은 45점이 아니다.
 *  · 과락(과목별 하한)이 있으면 총점이 높아도 불합격이다. 그 이유를 화면에 적는다.
 */
(function () {
  var root = document.querySelector('.rp');
  if (!root) return;

  var PD    = root.dataset.pd || '';
  var AT    = parseInt(root.dataset.at || '0', 10) || 0;
  var BRAND = root.dataset.brand || 'XAMpass';
  /* 샘플(데모) 모드 — API 에 sample=1 을 붙인다. 서버가 합성 답안지를 만든다. */
  var SAMPLE = root.dataset.sample === '1';
  var API   = '/exam/api/';
  var body  = document.getElementById('rpBody');

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function mmss(sec) {
    sec = sec | 0;
    if (!sec) return '';
    var m = Math.floor(sec / 60), s = sec % 60;
    return m >= 60 ? (Math.floor(m / 60) + '시간 ' + pad(m % 60) + '분') : (m + '분 ' + pad(s) + '초');
  }
  /* 막대 색 — 판정 4단계. 글자(rp-tag)와 항상 같이 쓴다. */
  var BAND = {
    good: { c: 'var(--c-good)', t: '양호' },
    mid:  { c: 'var(--c-blue)', t: '보통' },
    weak: { c: 'var(--c-mid)',  t: '보완 필요' },
    fail: { c: 'var(--c-bad)',  t: '과락' }
  };

  /* ── 점수 헤드 ──────────────────────────────────────────────── */
  function hero(d) {
    var a = d.attempt, p = d.pass;
    var judge = p.judge === 'pass'
      ? '<span class="rp-judge pass">✓ 합격선 통과</span>'
      : '<span class="rp-judge fail">합격선 미달</span>';

    /* 미응답 경고를 점수보다 먼저 읽히게 둔다.
       절반 이상 비웠으면 점수 자체가 실력을 나타내지 않는다. */
    var notes = [];
    if (a.skipped > 0) {
      var half = a.skipped >= a.total / 2;
      notes.push('<div class="rp-note ' + (half ? 'bad' : 'warn') + '">'
        + '<b>미응답 ' + a.skipped + '문항</b>' + (half
          ? ' — 절반 이상을 비우셨습니다. 이 점수는 실력을 나타내지 않습니다. 끝까지 풀고 다시 채점해 보세요.'
          : ' 이 오답으로 계산되었습니다.')
        + '</div>');
    }
    if (p.fail_subjects && p.fail_subjects.length) {
      notes.push('<div class="rp-note bad"><b>과락 과목이 있습니다</b> — '
        + esc(p.fail_subjects.join(' · '))
        + '. 총점이 ' + p.total_line + '점을 넘어도 과목별 ' + p.subject_line
        + '% 미만이면 불합격입니다.</div>');
    }
    if (!notes.length) {
      notes.push('<div class="rp-note">합격 기준 — 총점 <b>' + p.total_line + '점</b> 이상'
        + (p.subject_line > 0 ? ' · 과목별 <b>' + p.subject_line + '%</b> 이상' : '') + '</div>');
    }

    return '<div class="rp-hero">'
      + '<div class="rp-score">'
      +   '<div class="n">' + a.pct + '<small>점</small></div>'
      +   '<div class="frac">' + a.correct + ' / ' + a.total + '문항</div>'
      +   judge
      + '</div>'
      + '<div class="rp-meta">'
      +   '<div class="line">'
      +     '<b>' + esc(d.pd_name) + '</b>'
      +     '<span>' + esc(a.rd_label || (a.rd_no + "회")) + '</span>'
      +     (d.access && d.access.free_round
              ? '<span class="rp-tag good">무료 회차</span>' : '')
      +     (a.filter ? '<span>· ' + esc(a.filter) + '</span>' : '')
      +     (a.sec ? '<span>· ' + mmss(a.sec) + '</span>' : '')
      +     '<span>· ' + esc(String(a.at).slice(0, 16)) + '</span>'
      +   '</div>'
      +   notes.join('')
      + '</div></div>';
  }

  /* ── 과목별 ─────────────────────────────────────────────────── */
  function subjects(d) {
    if (!d.subjects || !d.subjects.length) return '';
    var line = d.pass.subject_line;
    var rows = d.subjects.map(function (s) {
      var b = BAND[s.band] || BAND.mid;
      return '<div class="rp-bar-row">'
        + '<div class="rp-bar-name">' + esc(s.sj_name)
        +   ' <span class="rp-tag ' + s.band + '">' + b.t + '</span></div>'
        + '<div class="rp-bar-val"><b>' + s.pct + '%</b> · ' + s.correct + '/' + s.total
        +   (s.skipped ? ' <span style="color:var(--c-faint)">(미응답 ' + s.skipped + ')</span>' : '')
        + '</div>'
        + '<div class="rp-track">'
        +   '<i style="width:' + s.pct + '%;background:' + b.c + '"></i>'
        +   (line > 0 ? '<span class="line" style="left:' + line + '%" title="과락선 ' + line + '%"></span>' : '')
        + '</div></div>';
    }).join('');

    return '<div class="rp-card"><h3>과목별 결과</h3>'
      + '<p class="cap">' + (line > 0
          ? '세로선이 과락선(' + line + '%)입니다. 선 왼쪽에 있으면 총점과 무관하게 불합격입니다.'
          : '과목별 정답률입니다.') + '</p>'
      + '<div class="rp-bars">' + rows + '</div></div>';
  }

  /* ── 취약 개념 ──────────────────────────────────────────────── */
  function weak(d) {
    if (!d.weak || !d.weak.length) {
      return '<div class="rp-card"><h3>취약 개념</h3>'
        + '<p class="cap">이번 회차에서 반복적으로 틀린 개념이 없습니다.</p></div>';
    }
    var chips = d.weak.map(function (w, i) {
      return '<span class="rp-chip' + (i < 3 ? ' hot' : '') + '">' + esc(w.tag)
        + ' <em>' + w.wrong + '/' + w.total + ' 틀림</em></span>';
    }).join('');
    return '<div class="rp-card"><h3>취약 개념</h3>'
      + '<p class="cap">과목보다 좁은 단위로 봅니다. 앞쪽 세 개가 가장 시급합니다 — '
      + '이론에서 이 개념부터 다시 보세요.</p>'
      + '<div class="rp-tags">' + chips + '</div></div>';
  }

  /* ── 난이도별 ───────────────────────────────────────────────── */
  function difficulty(d) {
    if (!d.difficulty || d.difficulty.length < 2) return '';
    var rows = d.difficulty.map(function (x) {
      var band = x.pct >= 80 ? 'good' : (x.pct >= 60 ? 'mid' : (x.pct >= 40 ? 'weak' : 'fail'));
      var b = BAND[band];
      return '<div class="rp-bar-row">'
        + '<div class="rp-bar-name">난이도 ' + esc(x.df) + '</div>'
        + '<div class="rp-bar-val"><b>' + x.pct + '%</b> · ' + x.correct + '/' + x.total + '</div>'
        + '<div class="rp-track"><i style="width:' + x.pct + '%;background:' + b.c + '"></i></div>'
        + '</div>';
    }).join('');
    return '<div class="rp-card"><h3>난이도별 결과</h3>'
      + '<p class="cap">쉬운 문항에서 실점이 있으면 개념보다 <b>실수</b>를 먼저 잡아야 합니다.</p>'
      + '<div class="rp-bars">' + rows + '</div></div>';
  }

  /* ── 추이 ───────────────────────────────────────────────────── */
  function trend(d) {
    if (!d.trend || d.trend.length < 2) return '';
    var cur = d.attempt.at_id;
    var bars = d.trend.map(function (t) {
      var h = Math.max(4, Math.round(t.pct * 0.78));   // 최대 78px
      return '<a class="t' + (t.at_id === cur ? ' on' : '') + '"'
        + ' href="?pd=' + encodeURIComponent(PD) + '&at=' + t.at_id + '"'
        + ' title="' + t.rd_no + '회 · ' + t.pct + '점">'
        + '<b>' + t.pct + '</b>'
        + '<i style="height:' + h + 'px"></i>'
        + '<span>' + esc(t.at) + '</span></a>';
    }).join('');
    return '<div class="rp-card"><h3>점수 추이</h3>'
      + '<p class="cap">최근 ' + d.trend.length + '회. 막대를 누르면 그 회차 성적표로 갑니다.</p>'
      + '<div class="rp-trend">' + bars + '</div></div>';
  }

  /* ── 문항별 ─────────────────────────────────────────────────── */
  var CIRC = '①②③④⑤⑥⑦⑧⑨⑩';
  var itemFilter = 'wrong';    // 기본은 '틀린 것만' — 50문항 전부는 처음에 안 본다

  function itemRows(d) {
    var list = d.items.filter(function (it) {
      if (itemFilter === 'all') return true;
      if (itemFilter === 'wrong') return !it.ok;
      if (itemFilter === 'skip')  return it.chosen < 0;
      return true;
    });
    if (!list.length) {
      return '<tr><td colspan="6" style="text-align:center;color:var(--c-faint);padding:26px">'
        + (itemFilter === 'wrong' ? '틀린 문항이 없습니다.' : '해당하는 문항이 없습니다.') + '</td></tr>';
    }
    return list.map(function (it) {
      var cls = it.chosen < 0 ? 'skip' : (it.ok ? '' : 'no');
      var mark = it.chosen < 0
        ? '<span class="mark sk">미응답</span>'
        : (it.ok ? '<span class="mark ok">O</span>' : '<span class="mark no">X</span>');
      var mine = it.chosen < 0 ? '—' : (CIRC[it.chosen] || (it.chosen + 1));
      var ans  = it.answer < 0 ? '—' : (CIRC[it.answer] || (it.answer + 1));
      return '<tr class="' + cls + '">'
        + '<td class="n">' + it.no + '</td>'
        + '<td class="n">' + mark + '</td>'
        + '<td class="q">' + esc(it.q) + '</td>'
        + '<td class="hide-s">' + esc(it.sj_name) + '</td>'
        + '<td class="n hide-s">' + esc(it.df) + '</td>'
        + '<td class="n">' + mine + ' / <b>' + ans + '</b></td>'
        + '</tr>';
    }).join('');
  }

  function items(d) {
    var n = { all: d.items.length, wrong: 0, skip: 0 };
    d.items.forEach(function (it) { if (!it.ok) n.wrong++; if (it.chosen < 0) n.skip++; });

    return '<div class="rp-card"><h3>문항별 결과</h3>'
      + '<p class="cap">내가 고른 답 / <b>정답</b> 순서입니다. 문제 전문은 문제집에서 보세요.</p>'
      + '<div class="rp-filter" id="rpFilter">'
      +   '<button data-f="wrong" class="on">틀린 것만 <b>' + n.wrong + '</b></button>'
      +   (n.skip ? '<button data-f="skip">미응답 <b>' + n.skip + '</b></button>' : '')
      +   '<button data-f="all">전체 ' + n.all + '</button>'
      + '</div>'
      + '<table class="rp-tbl"><thead><tr>'
      +   '<th>번호</th><th>정오</th><th>문항</th>'
      +   '<th class="hide-s">과목</th><th class="n hide-s">난이도</th><th class="n">내 답/정답</th>'
      + '</tr></thead><tbody id="rpItems">' + itemRows(d) + '</tbody></table></div>';
  }

  /* ── 반복 오답 ──────────────────────────────────────────────── */
  function repeat(d) {
    if (!d.repeat || !d.repeat.length) return '';
    var rows = d.repeat.map(function (r) {
      return '<a href="/exam/check.php?pd=' + encodeURIComponent(PD)
        + '&m=quiz&rd=' + r.rd_no + '">'
        + '<span class="cnt">' + r.wrong + '번 틀림</span>'
        + '<span class="t">' + esc(r.q) + '</span>'
        + '<span class="m">' + r.rd_no + '회 ' + r.no + '번 · ' + esc(r.sj_name) + '</span>'
        + '</a>';
    }).join('');
    return '<div class="rp-card"><h3>계속 틀리는 문제</h3>'
      + '<p class="cap">이번 회차가 아니라 <b>누적</b>입니다. 두 번 이상 틀렸고 아직 못 맞힌 문항입니다 — '
      + '점수보다 이쪽이 먼저입니다.</p>'
      + '<div class="rp-rep">' + rows + '</div></div>';
  }

  /* ── 다음에 볼 것 ───────────────────────────────────────────── */
  function next(d) {
    var worst = null;
    (d.subjects || []).forEach(function (s) { if (!worst || s.pct < worst.pct) worst = s; });

    var cards = [];
    if (worst) {
      cards.push('<a href="/exam/check.php?pd=' + encodeURIComponent(PD) + '&m=theory">'
        + '<b>이론 다시 보기 — ' + esc(worst.sj_name) + '</b>'
        + '<span>가장 낮은 과목입니다(' + worst.pct + '%). 요약노트에서 이 과목부터 보세요.</span></a>');
    }
    cards.push('<a href="/exam/check.php?pd=' + encodeURIComponent(PD)
      + '&m=quiz&rd=' + d.attempt.rd_no + '">'
      + '<b>' + d.attempt.rd_no + '회 다시 풀기</b>'
      + '<span>같은 회차를 다시 풀면 점수 추이에 쌓입니다.</span></a>');
    cards.push('<a href="/exam/check.php?pd=' + encodeURIComponent(PD) + '&m=board">'
      + '<b>막히는 부분 질문하기</b>'
      + '<span>과목게시판에 물어보세요. 같은 질문의 공개 답변이 이미 있을 수도 있습니다.</span></a>');
    cards.push('<a href="/exam/mypage.php?pd=' + encodeURIComponent(PD) + '">'
      + '<b>오답노트 보기</b>'
      + '<span>틀린 문항이 보기와 해설까지 함께 쌓여 있습니다.</span></a>');

    return '<div class="rp-card"><h3>다음에 볼 것</h3>'
      + '<div class="rp-next">' + cards.join('') + '</div></div>';
  }

  /* ── 잠긴 회차 ──────────────────────────────────────────────────
   * 분석은 서버가 아예 보내지 않는다(화면에서 가리는 것만으로는 개발자도구로 다 보인다).
   * 여기서는 **몇 개가 있는지만** 보여준다 — 그게 무엇을 사는지 알려준다.
   */
  function lockCard(d) {
    var t = d.teaser || {};
    var free = (t.free_rounds || []);

    var counts = [];
    if (t.weak_subjects) counts.push('<li><b>' + t.weak_subjects + '개 과목</b>이 보완 필요 이하입니다</li>');
    if (t.weak_tags)     counts.push('<li>반복해서 틀린 <b>취약 개념 ' + t.weak_tags + '개</b>가 잡혔습니다</li>');
    if (t.wrong)         counts.push('<li>틀린 <b>' + t.wrong + '문항</b>의 내 답과 정답</li>');
    if (t.repeat)        counts.push('<li>누적해서 <b>계속 틀리는 문제 ' + t.repeat + '개</b></li>');
    if (!counts.length)  counts.push('<li>과목별 취약도 · 취약 개념 · 문항별 결과</li>');

    var freeMsg = free.length
      ? '<div class="rp-note">'
        + free.map(function (f) { return '<b>' + esc(f.label) + '</b>'; }).join(' · ')
        + ' 성적표는 <b>무료</b>로 보실 수 있습니다.</div>'
      : '';

    return '<div class="rp-card rp-lock">'
      + '<div class="rp-lock-ic">🔒</div>'
      + '<h3>이 회차의 분석은 수강 신청 후 보실 수 있습니다</h3>'
      + '<p class="cap">점수는 위에 그대로 있습니다. 잠긴 것은 <b>왜 틀렸는지</b>입니다.</p>'
      + '<ul class="rp-lock-list">' + counts.join('') + '</ul>'
      + freeMsg
      + '<div class="rp-lock-cta">'
      +   '<a class="mp-btn" href="/exam/buy.php?pd=' + encodeURIComponent(PD) + '">수강 신청</a>'
      +   (free.length
            ? '<a class="mp-btn ghost" href="/exam/check.php?pd=' + encodeURIComponent(PD)
              + '&m=quiz&rd=' + free[0].rd_no + '">' + esc(free[0].label) + ' 무료로 풀어보기</a>'
            : '')
      + '</div>'
      + '<p class="cap" style="margin:14px 0 0">'
      + '수강 신청하면 <b>전 회차 성적표</b>와 <b>1:1 질문</b>이 열립니다. '
      + '문제·정답·해설은 지금도 전부 무료입니다.</p>'
      + '</div>';
  }

  /* ── 조립 ───────────────────────────────────────────────────── */
  function render(d) {
    document.getElementById('rpSub').textContent =
      d.pd_name + ' · ' + d.attempt.rd_no + '회 · ' + String(d.attempt.at).slice(0, 10);

    /* PDF 는 브라우저 인쇄를 쓴다 — 서버에 PDF 라이브러리(wkhtmltopdf·mPDF)를 올리면
       메모리·폰트(한글) 문제가 붙고, 화면과 결과물이 갈린다.
       인쇄 CSS 로 화면 그대로 뽑는 쪽이 유지 비용이 0에 가깝다. */
    document.getElementById('rpActions').innerHTML =
        '<a class="mp-btn" href="/exam/check.php?pd=' + encodeURIComponent(PD)
      + '&m=quiz&rd=' + d.attempt.rd_no + '">다시 풀기</a>'
      + '<button type="button" class="mp-btn ghost" id="rpPrint">PDF 저장 · 인쇄</button>'
      + '<a class="mp-btn ghost" href="/exam/mypage.php?pd=' + encodeURIComponent(PD)
      + (SAMPLE ? '&sample=1' : '') + '">마이페이지</a>';
    document.getElementById('rpPrint').addEventListener('click', function () {
      /* 인쇄 전에 문항별 필터를 '전체' 로 올린다 — 종이에 남는 성적표에서
         '틀린 것만' 33문항만 찍히면 나중에 그게 전부인 줄로 읽힌다. */
      var all = document.querySelector('#rpFilter button[data-f="all"]');
      if (all && !all.classList.contains('on')) all.click();
      window.print();
    });

    var c = document.getElementById('rpCrumb');
    if (c) {
      c.innerHTML = '<a href="/exam/">' + esc(BRAND) + '</a><span class="sep">›</span>'
        + '<a href="/exam/check.php?pd=' + encodeURIComponent(PD) + '">' + esc(d.pd_name) + ' 문제집</a>'
        + '<span class="sep">›</span><b>성적표</b>';
    }

    /* 잠긴 회차는 점수(hero)만 그리고 나머지를 잠금 카드로 대체한다.
       서버가 분석을 안 보냈으므로 subjects(d) 등을 불러도 빈 문자열이 나오지만,
       의도를 코드에 드러내려고 분기한다. */
    if (d.access && d.access.locked) {
      body.innerHTML = hero(d) + lockCard(d);
      return;
    }

    body.innerHTML = hero(d) + subjects(d) + weak(d) + difficulty(d)
                   + trend(d) + items(d) + repeat(d) + next(d);

    var f = document.getElementById('rpFilter');
    if (f) {
      f.addEventListener('click', function (e) {
        var b = e.target.closest('button[data-f]');
        if (!b) return;
        itemFilter = b.dataset.f;
        f.querySelectorAll('button').forEach(function (x) { x.classList.remove('on'); });
        b.classList.add('on');
        document.getElementById('rpItems').innerHTML = itemRows(d);
      });
    }
  }

  /* ── 부팅 ───────────────────────────────────────────────────── */
  var q = 'report.php?pd=' + encodeURIComponent(PD)
        + (AT ? '&at_id=' + AT : '')
        + (SAMPLE ? '&sample=1' : '');

  fetch(API + q, { credentials: 'same-origin' })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d || !d.ok) {
        var msg = (d && d.err === 'no_attempt')
          ? '아직 채점한 기록이 없습니다. 문제를 풀고 채점하면 성적표가 만들어집니다.'
          : ((d && d.err === 'pd_required')
              ? '문제집이 지정되지 않았습니다.'
              : '성적표를 불러오지 못했습니다.');
        document.getElementById('rpSub').textContent = '';
        body.innerHTML = '<div class="mp-empty">' + msg
          + '<br><br><a href="/exam/' + (PD ? 'check.php?pd=' + encodeURIComponent(PD) + '&m=quiz' : '') + '">'
          + '문제 풀러 가기</a></div>';
        return;
      }
      render(d);
    })
    .catch(function () {
      document.getElementById('rpSub').textContent = '';
      body.innerHTML = '<div class="mp-empty">성적표를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>';
    });
})();
