// Measured results, read from the API once and shared by the Home and Proof pages. Nothing here is a typed-in number.
import {getJSON} from './api.js';

const validReport = (report, dataset) => {
  const {clips, simulated, n_clips: n, ran_at: ranAt, main_system: main, systems} = report || {};
  return clips === dataset && simulated === false && Number.isInteger(n) && n > 0 && typeof ranAt === 'string' && ranAt &&
    typeof main === 'string' && systems && typeof systems === 'object' && !Array.isArray(systems) && Object.keys(systems).length &&
    Object.values(systems).every(s => s && typeof s === 'object' && !Array.isArray(s));
};

async function tryReport(dataset) {
  try { const report = await getJSON(`/api/bench/latest?clips=${dataset}`); return validReport(report, dataset) ? report : null; }
  catch { return null; }
}

let reportPromise = null;
/** {report, final} where final is true only for the real-voice exam. Null report means nothing measured yet. */
export function benchReport() {
  reportPromise ||= (async () => {
    const available = await getJSON('/api/bench/available').catch(() => ['dev']);   // asking first avoids a 404 in the console
    const real = available.includes('test_real_phone') ? await tryReport('test_real_phone') : null;
    if (real) return {report: real, final: true};
    const dev = await tryReport('dev');
    return {report: dev, final: false};
  })();
  return reportPromise;
}
export const reloadReport = () => { reportPromise = null; return benchReport(); };

let proofPromise = null;
export function learningProof() {
  proofPromise ||= getJSON('/api/learning/proof').then(p => (p && p.systems && Object.keys(p.systems).length ? p : null)).catch(() => null);
  return proofPromise;
}

let realPromise = null;
export function realVoice() {
  realPromise ||= getJSON('/api/real-voice').then(r => (r?.clean?.totals ? r : null)).catch(() => null);
  return realPromise;
}

// ---- derived numbers: always computed from the report, never typed in ----
export const sys = (report, id) => report?.systems?.[id];

/** Counts of facts for one system row: right, asked (wrong but flagged), silently wrong. */
export function factCounts(row) {
  const n = row?.entities;
  if (!Number.isFinite(n) || !Number.isFinite(row.entity_accuracy) || !Number.isFinite(row.silent_error_rate)) return null;
  const right = Math.round(row.entity_accuracy * n);
  const silent = Math.round(row.silent_error_rate * n);
  return {n, right, silent, asked: Math.max(0, n - right - silent)};
}

/** Do two 95% intervals overlap? null when an interval is missing. */
export function intervalsOverlap(a, b, key) {
  const x = a?.ci95?.[key];
  const y = b?.ci95?.[key];
  if (!Array.isArray(x) || !Array.isArray(y)) return null;
  return x[0] <= y[1] && y[0] <= x[1];
}

export const interval = (row, key) => row?.ci95?.[key] || null;
