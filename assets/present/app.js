/* ============================================================
   WOWPASS AI 셀프 채점기 — 동작 로직 (샘플 데모)
   - 이론편: 객관식 답안 입력 → localStorage 저장
   - 실무편: 문항별 자기채점 → localStorage 저장
   - 결과 리포트: 저장된 입력으로 예상점수·취약분야 자동 계산
   브라우저 localStorage만 사용 (서버 없음). 파일 단독 실행 OK.
   ============================================================ */
(function (global) {
  "use strict";

  /* ---------- 공식답안 키 (샘플) ---------- */
  // 이론 15문항, 문항당 2점. A형/B형 별도 정답.
  const THEORY_KEY = {
    A: [3, 1, 4, 2, 3, 2, 1, 4, 3, 1, 2, 4, 3, 2, 1],
    B: [2, 4, 1, 3, 2, 3, 4, 1, 2, 4, 3, 1, 2, 3, 4]
  };
  const THEORY_PER = 2;   // 문항당 점수
  const PRACTICAL_PER = 3; // 실무 문항당 점수
  const PRACTICAL_COUNT = 6;

  // 이론 문항 → 취약분야 버킷 매핑 (1~15)
  // 부가세: 1-5, 결산: 6-10, 원천세: 11-15
  const THEORY_CAT = {
    "부가세": [1, 2, 3, 4, 5],
    "결산":   [6, 7, 8, 9, 10],
    "원천세": [11, 12, 13, 14, 15]
  };

  const PASS_LINE = 70; // 합격 기준점

  /* ---------- 저장소 ---------- */
  const KEY_THEORY = "wp_theory_v1";
  const KEY_PRACTICAL = "wp_practical_v1";

  function load(key) {
    try { return JSON.parse(localStorage.getItem(key)) || null; }
    catch (e) { return null; }
  }
  function save(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); return true; }
    catch (e) { return false; }
  }

  /* ---------- 채점 계산 ---------- */
  function gradeTheory(state) {
    // state: { type:'A'|'B', answers:{1:3,...} }
    const type = (state && state.type) || "A";
    const key = THEORY_KEY[type] || THEORY_KEY.A;
    const answers = (state && state.answers) || {};
    let correct = 0, answered = 0;
    const perQuestion = {};
    for (let i = 1; i <= 15; i++) {
      const a = answers[i];
      if (a) answered++;
      const ok = a && Number(a) === key[i - 1];
      perQuestion[i] = ok;
      if (ok) correct++;
    }
    return {
      type, answered, correct,
      total: 15, earned: correct * THEORY_PER, max: 15 * THEORY_PER,
      perQuestion
    };
  }

  function gradePractical(state) {
    // state: { checks:{1:'same'|'wrong'|'unsure'} }
    const checks = (state && state.checks) || {};
    let checked = 0, correct = 0;
    const perQuestion = {};
    for (let i = 1; i <= PRACTICAL_COUNT; i++) {
      const c = checks[i];
      if (c) checked++;
      const ok = c === "same";
      perQuestion[i] = ok;
      if (ok) correct++;
    }
    return {
      checked, correct, total: PRACTICAL_COUNT,
      earned: correct * PRACTICAL_PER, max: PRACTICAL_COUNT * PRACTICAL_PER,
      perQuestion
    };
  }

  function statusOf(rate) {
    if (rate >= 70) return { key: "good",    label: "양호",     cls: "pill-teal",   color: "var(--teal)" };
    if (rate >= 50) return { key: "partial", label: "일부 보완", cls: "pill-orange", color: "var(--orange)" };
    return { key: "weak", label: "보완 필요", cls: "pill-red", color: "var(--red)" };
  }

  function overallVerdict(score) {
    if (score >= 80) return { label: "합격 유력",   tone: "good", desc: "현재 실력이라면 합격 가능성이 높습니다. 실수 방지에 집중하세요." };
    if (score >= 70) return { label: "합격권",       tone: "good", desc: "합격 기준을 충족하는 수준입니다. 안정권 진입을 위해 마무리 점검을 권장합니다." };
    if (score >= 60) return { label: "합격 경계권", tone: "warn", desc: "현재 실력으로는 합격이 가능한 수준이지만 일부 영역의 보완이 필요합니다." };
    return { label: "보완 필요", tone: "bad", desc: "합격 기준까지 점수 보완이 필요합니다. 취약분야 집중 학습을 권장합니다." };
  }

  // 합격 가능성(%) — 점수 기반 단순 추정
  function passProbability(score) {
    if (score >= 85) return 92;
    if (score >= 80) return 85;
    if (score >= 75) return 78;
    if (score >= 70) return 70;
    if (score >= 67) return 62;
    if (score >= 62) return 48;
    if (score >= 58) return 35;
    if (score >= 50) return 22;
    return 12;
  }

  /* ---------- 종합 리포트 ---------- */
  function buildReport(theoryState, practicalState) {
    const t = gradeTheory(theoryState);
    const p = gradePractical(practicalState);

    const earned = t.earned + p.earned;
    const max = t.max + p.max;                  // 30 + 18 = 48
    const pct = max ? earned / max : 0;
    const general = Math.round(pct * 100);
    const conservative = Math.max(0, general - 5);
    const optimistic = Math.min(100, general + 5);

    // 취약분야 (이론 3개 카테고리 + 실무입력)
    const categories = [];
    Object.keys(THEORY_CAT).forEach(function (cat) {
      const qs = THEORY_CAT[cat];
      let c = 0;
      qs.forEach(function (q) { if (t.perQuestion[q]) c++; });
      const rate = Math.round((c / qs.length) * 100);
      categories.push({ name: cat, correct: c, total: qs.length, rate: rate, status: statusOf(rate) });
    });
    const prate = Math.round((p.correct / p.total) * 100);
    categories.push({ name: "실무 입력", correct: p.correct, total: p.total, rate: prate, status: statusOf(prate) });

    const weak = categories.filter(function (c) { return c.status.key !== "good"; })
                           .sort(function (a, b) { return a.rate - b.rate; });

    return {
      theory: t, practical: p,
      scores: {
        conservative: conservative, general: general, optimistic: optimistic,
        prob: { conservative: passProbability(conservative), general: passProbability(general), optimistic: passProbability(optimistic) }
      },
      categories: categories,
      weak: weak,
      verdict: overallVerdict(general)
    };
  }

  /* ---------- 데모 폴백 (입력이 없을 때 화면 채우기) ---------- */
  function demoData() {
    // 예시 데이터: 일반 예상 67점(보수 62 / 낙관 72), 합격 경계권.
    // 부가세 약점(보완 필요), 실무 입력 일부 보완 → 취약분야 화면이 자연스럽게 채워짐.
    return {
      theory: { type: "A", answers: {
        1:3, 2:1, 3:1, 4:3, 5:1,      // 부가세: 2/5 정답
        6:2, 7:1, 8:4, 9:3, 10:4,     // 결산: 4/5 정답
        11:2, 12:4, 13:3, 14:2, 15:4  // 원천세: 4/5 정답
      } },
      practical: { checks: { 1:"same", 2:"wrong", 3:"same", 4:"same", 5:"unsure", 6:"same" } } // 4/6
    };
  }

  global.WP = {
    THEORY_KEY: THEORY_KEY,
    PRACTICAL_COUNT: PRACTICAL_COUNT,
    PASS_LINE: PASS_LINE,
    KEY_THEORY: KEY_THEORY, KEY_PRACTICAL: KEY_PRACTICAL,
    load: load, save: save,
    loadTheory: function () { return load(KEY_THEORY); },
    loadPractical: function () { return load(KEY_PRACTICAL); },
    saveTheory: function (s) { return save(KEY_THEORY, s); },
    savePractical: function (s) { return save(KEY_PRACTICAL, s); },
    gradeTheory: gradeTheory,
    gradePractical: gradePractical,
    buildReport: buildReport,
    demoData: demoData
  };
})(window);
