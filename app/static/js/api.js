// Every network call the site makes. Same-origin only: nothing is loaded from the internet.
export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

// The demo passcode lives in memory, and in sessionStorage when the browser allows it.
let passcode = '';
try { passcode = sessionStorage.getItem('pehchaan.passcode') || ''; } catch { /* storage blocked */ }
export const getPasscode = () => passcode;
export function setPasscode(value) {
  passcode = value || '';
  try {
    if (passcode) sessionStorage.setItem('pehchaan.passcode', passcode);
    else sessionStorage.removeItem('pehchaan.passcode');
  } catch { /* storage blocked */ }
}

export async function checkResponse(response) {
  if (response.ok) return response;
  let message = `The request failed (HTTP ${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') message = body.detail;
  } catch { /* no JSON body */ }
  throw new ApiError(message, response.status);
}

export async function getJSON(url) {
  return (await checkResponse(await fetch(url, {cache: 'no-store'}))).json();
}

export async function postJSON(url, body) {
  const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body ?? {})});
  return (await checkResponse(response)).json();
}

let configPromise = null;
export function siteConfig() {
  configPromise ||= getJSON('/api/config').catch(() => ({mode: 'unknown', live_needs_passcode: false, live_available: false, studio: false, unavailable: true}));
  return configPromise;
}

let presetPromise = null;
export function presets() {
  presetPromise ||= getJSON('/api/demo/presets').then(list => Array.isArray(list) ? list : []).catch(error => { presetPromise = null; throw error; });
  return presetPromise;
}

/** Read newline-delimited JSON events until the stream ends. */
export async function readEvents(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = '';
  try {
    while (true) {
      const {done, value} = await reader.read();
      buffered += decoder.decode(value, {stream: !done});
      const lines = buffered.split('\n');
      buffered = lines.pop();
      for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
      if (done) break;
    }
    if (buffered.trim()) onEvent(JSON.parse(buffered));
  } finally {
    reader.releaseLock();
  }
}

/** POST /api/demo/compare. `live` adds the passcode header. Events go to onEvent. */
export async function compare(fields, onEvent, {live = false} = {}) {
  const headers = {};
  if (live && passcode) headers['X-Demo-Passcode'] = passcode;
  const response = await checkResponse(await fetch('/api/demo/compare', {method: 'POST', body: fields, headers}));
  await readEvents(response, onEvent);
}

/** Run a packaged sample and collect everything the stream returns. */
export async function runPreset(id) {
  const fields = new FormData();
  fields.append('preset', id);
  const run = {started: null, results: new Map(), errors: new Map(), done: false};
  await compare(fields, event => {
    if (event.event === 'started') run.started = event;
    else if (event.event === 'result') run.results.set(event.system_id, event.result);
    else if (event.event === 'system_error') run.errors.set(event.system_id, event.message);
    else if (event.event === 'done') run.done = true;
  });
  return run;
}

export const confirmCorrection = (runId, fields) => postJSON(`/api/demo/${encodeURIComponent(runId)}/confirm`, fields);
export const replayCall = (runId, systemId) => postJSON(`/api/demo/${encodeURIComponent(runId)}/replay`, {system_id: systemId});
export const learningLedger = () => getJSON('/api/demo/learning');
export const rollbackCorrection = id => postJSON(`/api/demo/learning/${encodeURIComponent(id)}/rollback`, {});

/** Describe a failed live request in words a person can act on. */
export function liveProblem(error) {
  if (error?.status === 401) return {kind: 'passcode', text: 'That passcode was not accepted. Enter the demo passcode to use live audio.'};
  if (error?.status === 403) return {kind: 'off', text: 'Live audio is turned off on this deployment. The sample calls still work.'};
  if (error?.status === 429) return {kind: 'limit', text: error.message || 'Too many requests. Try again in a minute. The sample calls still work.'};
  return {kind: 'other', text: error?.message || 'Something went wrong. Try again.'};
}
