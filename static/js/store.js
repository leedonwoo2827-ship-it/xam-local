/* 앱 공용 상태 — BOOK 개요 캐시 · 잡 폴링
 *
 * 상태 관리 라이브러리는 쓰지 않는다. 대신 세 가지로 버틴다.
 *   1) 프로미스 메모이즈 — 세션 내내 안 바뀌는 것(BOOK 개요, 번들 목록)
 *   2) localStorage      — 이 PC 취향 (필터, 접힘 상태). 전부 xam.* 네임스페이스
 *   3) CustomEvent       — 화면 간 신호 (xam:job-changed, xam:review-changed)
 */
"use strict";

import { api, sleep } from "./util.js";

let bookPromise = null;
let versionPromise = null;

/** BOOK 개요 — 단계별 파일 수 · 회차 · 검수 진행률. */
export function getBook(force = false) {
  if (force || !bookPromise) {
    bookPromise = api("/api/book/info").catch((e) => ({
      exists: false, error: e.message, rounds: [], total: 0, reviewed: 0,
    }));
  }
  return bookPromise;
}

export function getVersion(force = false) {
  if (force || !versionPromise) {
    versionPromise = api("/api/version").catch(() => ({ name: "XAM LOCAL", pd: "?" }));
  }
  return versionPromise;
}

/** 문항 목록. 필터가 바뀌면 매번 새로 받는다 — 캐시하지 않는다. */
export async function getQuestions(params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== "" && v != null)
  );
  return api("/api/questions?" + qs.toString());
}

/** 번들 24개 상태. 렌더가 끝나면 바뀌므로 force 로 다시 받는다. */
export async function getBundles() {
  try {
    return (await api("/api/render/bundles")).items || [];
  } catch (e) {
    return [];
  }
}

/** 최근 작업(렌더 + 발행 합본). 서버에 잡 계층이 없으면 빈 배열. */
export async function getJobs(limit = 12) {
  try {
    const d = await api(`/api/jobs?limit=${limit}`);
    return d.jobs || [];
  } catch (e) {
    return [];
  }
}

/* ── 잡 폴링 ────────────────────────────────────────────────────────────────
 * 서버는 SSE 를 쓰지 않는다. 스레드 + JSON 파일 + 2초 폴링이다(계획 §10).
 * 로그는 서버가 링버퍼 400줄만 들고 있으므로 log_from 커서로 증분만 받는다.
 * onTick 은 진행 중에도 호출된다 — .prog 를 그때그때 갱신해야 한다.
 *
 * ★ maxTicks 는 넉넉해야 한다. 예전 3600(2시간)에서 24번들 렌더가 7시간 걸리자
 *   2시간 지점에 폴링이 스스로 포기하고 **화면이 그 시점 스냅샷에 얼어붙었다**.
 *   서버는 정상이었는데 사람은 렌더가 멈춘 줄 알았다. 기본을 24시간으로 두고,
 *   그래도 넘으면 onTick 에 timeout 표식을 남겨 화면이 "다시 붙일지" 판단하게 한다.
 *
 * ★ onTick 이 던지는 예외를 삼킨다. 안 삼키면 그리기 한 번 실패가 폴링 전체를
 *   끊어서 같은 '얼어붙음' 이 된다.
 */
export async function pollJob(id, onTick, { interval = 2000, maxTicks = 43200 } = {}) {
  let cursor = 0;
  for (let i = 0; i < maxTicks; i++) {
    let job;
    try {
      job = await api(`/api/jobs/${encodeURIComponent(id)}?log_from=${cursor}`);
    } catch (e) {
      // 일시적 실패로 폴링을 끊지 않는다. 잡은 서버 파일에 남아 있다.
      await sleep(interval);
      continue;
    }
    if (job.log && typeof job.log.next === "number") cursor = job.log.next;
    // 그리기 실패가 폴링을 끊지 않게 한다 — 끊기면 화면이 그 시점에 얼어붙는다.
    if (onTick) {
      try { onTick(job); } catch (e) { console.error("pollJob onTick", e); }
    }
    if (job.status !== "running" && job.status !== "queued") return job;
    await sleep(interval);
  }
  return null;
}

/* ── 이 PC 취향 ─────────────────────────────────────────────────────────── */
const PREF_KEY = "xam.pref";

export function getPref(name, fallback = null) {
  try {
    const all = JSON.parse(localStorage.getItem(PREF_KEY) || "{}");
    return name in all ? all[name] : fallback;
  } catch (e) {
    return fallback;
  }
}

export function setPref(name, value) {
  let all = {};
  try { all = JSON.parse(localStorage.getItem(PREF_KEY) || "{}"); } catch (e) { /* 무시 */ }
  all[name] = value;
  localStorage.setItem(PREF_KEY, JSON.stringify(all));
}

/** 작업이 끝났다는 신호 — 셸의 최근 목록과 다른 화면이 듣는다. */
export function fireJobChanged(detail) {
  window.dispatchEvent(new CustomEvent("xam:job-changed", { detail }));
}

/** 검수 상태가 바뀌었다는 신호 — 레일의 진행률과 발행 사전점검이 듣는다. */
export function fireReviewChanged(detail) {
  window.dispatchEvent(new CustomEvent("xam:review-changed", { detail }));
}
