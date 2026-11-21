// Studio (laptop only): record the six real-voice sample calls, one script at a time.
import {esc, icon, glyph, badge} from './util.js';
import {initInfo} from './info.js';
import {getJSON, checkResponse} from './api.js';
import {canRecord, startRecording, micProblem} from './recorder.js';

initInfo();
const root = document.getElementById('studio');
const state = {samples: [], index: 0, handle: null, take: null, takeUrl: null, busy: false, message: '', problem: ''};
const langTag = {Hindi: 'hi', Hinglish: 'hi-Latn', 'Indian English': 'en-IN', Telugu: 'te'};

const recorded = () => state.samples.filter(s => s.recorded).length;
const current = () => state.samples[state.index];

function render() {
  const total = state.samples.length;
  const done = recorded();
  const s = current();
  const allDone = total > 0 && done === total;
  const status = state.handle ? 'recording' : state.take ? 'review' : 'idle';
  root.innerHTML = `
    <div class="studio-progress">
      <p><b class="num">${done}</b> of <b class="num">${total}</b> recorded</p>
      <div class="meter" role="progressbar" aria-label="Clips recorded" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${done}"><span style="width:${total ? (100 * done / total) : 0}%"></span></div>
    </div>
    ${s ? `<article class="take card" aria-labelledby="take-title">
      <div class="meta"><h2 id="take-title">${esc(s.label)}</h2><span class="chip">${esc(s.language)}</span>
        ${s.recorded ? badge('verified').replace('Verified', 'Saved') : '<span class="chip">Not recorded yet</span>'}</div>
      <p class="script" lang="${langTag[s.language] || 'en'}">${esc(s.spoken)}</p>
      ${s.tip ? `<p class="tip"><strong>Tip.</strong> ${esc(s.tip)}</p>` : ''}
      <div class="controls">
        ${status === 'idle' ? `<button class="button button-primary" id="rec" type="button" ${state.busy ? 'disabled' : ''}>${icon('mic')} ${s.recorded ? 'Re-record' : 'Record'}</button>` : ''}
        ${status === 'recording' ? `<button class="button button-primary" id="stop" type="button">${icon('stop')} Stop</button><span class="timer" id="timer">00:00</span>` : ''}
        ${status === 'review' ? `<audio controls src="${esc(state.takeUrl)}" aria-label="Listen to the new take"></audio>
          <button class="button button-primary" id="save" type="button" ${state.busy ? 'disabled' : ''}>${icon('check')} ${state.busy ? 'Saving…' : 'Save this take'}</button>
          <button class="button" id="again" type="button" ${state.busy ? 'disabled' : ''}>${icon('replay')} Record again</button>` : ''}
        ${status === 'idle' && s.recorded ? `<audio controls preload="none" src="/api/demo/presets/${encodeURIComponent(s.id)}/audio?t=${Date.now()}" aria-label="Listen to the saved take"></audio>
          <button class="link-button" id="delete" type="button">Delete saved clip</button>` : ''}
      </div>
      <p class="note" id="studio-status" role="status">${esc(state.message)}</p>
      ${state.problem ? `<div class="state-box is-error problem" role="alert"><strong>${esc(state.problem)}</strong></div>` : ''}
    </article>` : '<div class="state-box"><strong>No scripts to record</strong>The server did not return any sample scripts.</div>'}
    ${allDone ? `<div class="finish" role="status"><h2>All ${total} clips are recorded</h2>
      <p>Run <code>make publish</code> in the terminal to package the answers, so the samples work on the public site.</p></div>` : ''}
    <ul class="clip-list" aria-label="All scripts">${state.samples.map((x, i) => `<li><button type="button" data-go="${i}" ${i === state.index ? 'aria-current="true"' : ''} ${state.handle ? 'disabled' : ''}>
      <span>${esc(x.label)} <span class="muted">${esc(x.language)}</span></span><span>${x.recorded ? `${glyph('check')} Saved` : 'To record'}</span></button></li>`).join('')}</ul>`;
}

function clearTake() {
  if (state.takeUrl) URL.revokeObjectURL(state.takeUrl);
  state.take = null;
  state.takeUrl = null;
}

async function load() {
  try {
    state.samples = await getJSON('/api/studio/samples');
  } catch (error) {
    root.innerHTML = `<div class="state-box is-error"><strong>The Studio is not available</strong>${esc(error.message)} It only runs on the laptop (<code>make serve</code>).</div>`;
    return;
  }
  const first = state.samples.findIndex(s => !s.recorded);
  state.index = Math.max(0, first);
  render();
}

async function start() {
  state.problem = '';
  state.message = '';
  if (!canRecord()) { state.problem = 'This browser cannot record audio. Open the Studio in a current Chrome, Edge, Safari or Firefox.'; render(); return; }
  try {
    state.handle = await startRecording(text => { const t = document.getElementById('timer'); if (t) t.textContent = text; });
    state.message = 'Recording. Read the script aloud, then press Stop.';
  } catch (error) {
    state.problem = micProblem(error);
  }
  render();
  document.getElementById('stop')?.focus();
}

async function stop() {
  const take = await state.handle.finish();
  state.handle = null;
  if (!take) { state.problem = 'No audio was captured. Try again.'; render(); return; }
  state.take = take;
  state.takeUrl = URL.createObjectURL(take.blob);
  state.message = 'Listen to the take. Save it, or record again.';
  render();
  document.getElementById('save')?.focus();
}

async function save() {
  const s = current();
  state.busy = true;
  state.problem = '';
  render();
  try {
    const body = new FormData();
    body.append('audio', state.take.blob, state.take.filename);
    await checkResponse(await fetch(`/api/studio/samples/${encodeURIComponent(s.id)}`, {method: 'POST', body}));
    s.recorded = true;
    clearTake();
    const next = state.samples.findIndex((x, i) => !x.recorded && i !== state.index);
    state.message = `Saved ${s.label}.`;
    if (next >= 0) { state.index = next; state.message += ' On to the next script.'; }
  } catch (error) {
    state.problem = `Could not save this take. ${error.message}`;
  }
  state.busy = false;
  render();
  document.getElementById('take-title')?.scrollIntoView({block: 'start'});
}

async function remove() {
  const s = current();
  if (!confirm(`Delete the saved clip for "${s.label}"?`)) return;
  try {
    await checkResponse(await fetch(`/api/studio/samples/${encodeURIComponent(s.id)}`, {method: 'DELETE'}));
    s.recorded = false;
    state.message = 'Deleted.';
  } catch (error) {
    state.problem = error.message;
  }
  render();
}

root.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.id === 'rec') void start();
  else if (button.id === 'stop') void stop();
  else if (button.id === 'save') void save();
  else if (button.id === 'again') { clearTake(); state.message = ''; render(); void start(); }
  else if (button.id === 'delete') void remove();
  else if (button.dataset.go !== undefined) { clearTake(); state.index = +button.dataset.go; state.message = ''; state.problem = ''; render(); }
});

void load();
