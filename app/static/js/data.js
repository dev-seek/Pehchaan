// Measured results, read from the API once and shared across the site. Nothing here is a typed-in number.
import {getJSON} from './api.js';

// Hard rule: a simulated run is never shown as a result.
const measured = (report, dataset) => {
  const {clips, simulated, n_clips: n, main_system: main, systems} = report || {};
  const complete = clips === dataset && simulated === false && Number.isInteger(n) && n > 0 && typeof main === 'string'
    && systems && typeof systems === 'object' && Object.keys(systems).length > 0;
  return complete ? report : null;
};

let proofPromise = null;
export function learningProof() {
  proofPromise ||= getJSON('/api/learning/proof').then(p => (p && p.systems && Object.keys(p.systems).length ? p : null)).catch(() => null);
  return proofPromise;
}

let labPromise = null;
/** Everything the Benchmark Lab shows: both exam lines, the paired counts, line quality and the model comparison. */
export function labData() {
  labPromise ||= getJSON('/v1/bench').then(lab => ({
    ...lab,
    exam: {standard: measured(lab.exam?.standard, 'test_real_phone'), noisy: measured(lab.exam?.noisy, 'test_real_noisy')},
    dev: measured(lab.dev, 'dev'),
  })).catch(() => null);
  return labPromise;
}

export const sys = (report, id) => report?.systems?.[id];
export const interval = (row, key) => row?.ci95?.[key] || null;
