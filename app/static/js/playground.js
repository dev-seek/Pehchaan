// Try it: sample gallery, your own call, the base-versus-Pehchaan comparison, and the confirm, test, replay, undo flow.
import {esc, icon, plural} from './util.js';
import {info} from './info.js';
import {siteConfig, presets as loadPresets, compare as postCompare, ApiError, getPasscode, setPasscode, liveProblem,
  confirmCorrection, replayCall, learningLedger, rollbackCorrection} from './api.js';
import {canRecord, startRecording, micProblem} from './recorder.js';
import {showEvidence, openNote} from './evidence.js';
import {systemTitle, systemInfo} from './charts.js';
import {levels, sampleCard, emptySamples, contextFacts, storyBanner, resultPanel, scorecardBlock, ledger} from './pg-views.js';

const BASE_ID = 'B0_asr_plain';

const layout = `
  <header class="page-head">
    <h1>Try a call</h1>
    <p class="lede">Play a sample call. See what the base speech model heard, and which facts Pehchaan fixed, verified or asked about.</p>
    <p class="note invented">All names, numbers and calls on this page are invented. Sample answers are packaged with the site, so they run instantly and cost nothing.</p>
  </header>

  <section class="samples-section" aria-labelledby="pg-samples-title">
    <h2 id="pg-samples-title">Start with a sample call</h2>
    <ul id="pg-samples" class="samples"><li class="state-box">Loading sample calls…</li></ul>
  </section>

  <section class="own card-soft" aria-labelledby="pg-own-title">
    <h2 id="pg-own-title">Or try your own call</h2>
    <div id="pg-live-note"></div>
    <div class="own-actions" id="pg-own-actions">
      <div class="rec-row">
        <button class="button button-primary" id="pg-record" type="button">${icon('mic')} Record from the microphone</button>
        <button class="button button-primary" id="pg-stop" type="button" hidden>${icon('stop')} Stop and compare</button>
        <button class="button" id="pg-cancel" type="button" hidden>Cancel</button>
        <span class="rec-time" id="pg-time" hidden><span class="rec-dot" aria-hidden="true"></span><time id="pg-elapsed">00:00</time></span>
      </div>
      <div class="fallbacks">
        <button class="link-button" id="pg-upload" type="button">${icon('upload')} Upload audio</button>
        <input id="pg-file" type="file" accept="audio/*,.webm,.mp4,.m4a,.flac,.wav,.mp3,.ogg,.mpeg,.mpga" hidden>
        <button class="link-button" id="pg-type" type="button" aria-expanded="false" aria-controls="pg-typed-form">${icon('type')} Paste a transcript</button>
      </div>
    </div>
    <form id="pg-typed-form" hidden>
      <label for="pg-transcript">Call transcript</label>
      <textarea id="pg-transcript" rows="3" placeholder="Paste or type what the caller said." required></textarea>
      <button class="button button-primary" id="pg-submit-text" type="submit">Compare transcript ${icon('arrow')}</button>
    </form>
    <p id="pg-mic-note" class="note" role="status"></p>
  </section>

  <section class="level card-soft" aria-labelledby="pg-context-title">
    <h2 id="pg-context-title">What the phone knows${info('context')}</h2>
    <fieldset class="levels">
      <legend class="sr-only">Pehchaan context level</legend>
      ${Object.entries(levels).map(([key, l]) => `<div class="level-opt"><label><input type="radio" name="pg-level" value="${key}" ${key === 'C3' ? 'checked' : ''}><span>${esc(l.label)} <b>${key}</b></span></label>${info(key)}</div>`).join('')}
    </fieldset>
    <p id="pg-context-description" class="note"></p>
    <details id="pg-context-details"><summary id="pg-context-summary">View or edit call hints</summary>
      <div>
        <div id="pg-preset-hints" hidden></div>
        ${['regular', 'wrong'].map(mode => `<div class="hints" id="pg-hints-${mode}" hidden>
          <p class="note">${mode === 'wrong' ? 'These hints are deliberately misleading. Use a contact, caller ID, message or place that conflicts with the call.' : 'Live calls start with empty hints. Add details before comparing a call.'}</p>
          <div class="hint-fields">
            <label>Contacts <span>(one name per line)</span><textarea rows="2" data-hint="contacts"></textarea></label>
            <label>Saved places <span>(one per line)</span><textarea rows="2" data-hint="places"></textarea></label>
            <label>Caller ID name<input type="text" data-hint="callerName"></label>
            <label>Caller ID number<input type="tel" data-hint="callerNumber"></label>
            <label>SMS sender<input type="text" data-hint="smsSender"></label>
            <label>SMS message<textarea rows="2" data-hint="smsBody"></textarea></label>
            <label>City<input type="text" data-hint="city"></label>
          </div>
          <p class="note" data-hint-status hidden></p>
          <button type="button" class="button" data-apply-hints hidden>Compare again with edited hints</button>
        </div>`).join('')}
      </div>
    </details>
  </section>

  <section class="results" aria-label="Comparison">
    <p id="pg-status" class="status-line" role="status" aria-live="polite"></p>
    <div id="pg-playback" class="playback" hidden>
      <p id="pg-audio-label" class="note"></p>
      <audio id="pg-audio" controls preload="metadata" aria-labelledby="pg-audio-label"></audio>
      <p id="pg-playback-error" class="note" role="status" hidden>Playback is unavailable for this audio.</p>
    </div>
    <div id="pg-story"><div class="state-box"><strong>Nothing compared yet</strong>Choose a sample call above. The result shows which facts the base model got wrong and what Pehchaan did about them.</div></div>
    <div id="pg-scorecard"></div>
    <div class="pair">
      <article class="panel" id="pg-base" aria-label="Base model"></article>
      <article class="panel panel-main" id="pg-main" aria-label="With Pehchaan"></article>
    </div>
    <details class="approaches" id="pg-approaches">
      <summary>All approaches that ran <span id="pg-approach-count" class="note"></span></summary>
      <div id="pg-approach-items"><p class="note">Approaches appear as they finish.</p></div>
    </details>
  </section>

  <section class="ledger-section" aria-labelledby="pg-ledger-title">
    <h2 id="pg-ledger-title">What Pehchaan has learned${info('ledger')}</h2>
    <p class="note">Every confirmation is tested before it can change anything. Each decision is kept here, and you can undo any adopted correction${info('verified_learning')}.</p>
    <div id="pg-ledger"></div>
  </section>`;

function readHints(hints) {
  const get = key => hints.querySelector(`[data-hint="${key}"]`).value.trim();
  const lines = key => get(key).split('\n').map(l => l.trim()).filter(Boolean);
  const context = {};
  if (lines('contacts').length) context.contacts = lines('contacts').map(name => ({name}));
  if (lines('places').length) context.places = lines('places');
  if (get('callerName') || get('callerNumber')) context.caller = {cnap_name: get('callerName'), number: get('callerNumber')};
  if (get('smsSender') || get('smsBody')) context.sms = [{sender: get('smsSender'), body: get('smsBody')}];
  if (get('city')) context.user = {city: get('city')};
  return context;
}

export async function mountPlayground(root) {
  root.classList.add('page', 'playground');
  root.innerHTML = layout;
  const find = name => root.querySelector(`#pg-${name}`);
  const dialog = document.getElementById('evidence-dialog');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ui = {
    level: 'C3', working: false, requested: false, recording: null, audioUrl: null, presets: [], input: null, contexts: null,
    run: null, results: new Map(), errors: new Map(), replays: new Map(), verdicts: new Map(), confirming: null, ledger: null,
    canReplay: false, replaying: null, done: false, config: {mode: 'unknown', live_available: false, live_needs_passcode: false},
    pending: null,
  };
  const report = message => { find('status').textContent = message; };
  const getMain = () => ({C0: 'P_C0', C2: 'P_C2', C3: ui.run?.main_system || 'P_on_B1_C3', C4: 'P_on_B1_C4'})[ui.level];
  const getResult = id => ui.replays.get(id) || ui.results.get(id);
  const currentPreset = () => ui.input?.preset;
  const hints = mode => find(`hints-${mode}`);
  const setHtml = (el, html) => { if (el.cache !== html) { el.cache = html; el.innerHTML = html; } };

  // ---- live access: what this deployment allows ----
  function renderLiveNote() {
    const {mode, live_available: available, live_needs_passcode: needsCode} = ui.config;
    const own = find('own-actions');
    const holder = find('live-note');
    const blocked = mode === 'public' && !available;
    for (const el of [find('record'), find('upload'), find('type'), find('submit-text')]) el.dataset.locked = blocked ? 'true' : '';
    own.classList.toggle('is-off', blocked);
    if (blocked) {
      holder.innerHTML = `<div class="state-box"><strong>${icon('lock')} Live audio is off on this deployment</strong>
        Recording, uploads and pasted transcripts spend paid model credits, so they are switched off here. The sample calls above still work in full.</div>`;
    } else if (needsCode) {
      const has = !!getPasscode();
      holder.innerHTML = `<form id="pg-pass" class="pass">
        <p><strong>${icon('lock')} Live audio needs a passcode.</strong> It limits how many paid model calls this public demo can make. The sample calls need no passcode.</p>
        <div class="pass-row"><label for="pg-passcode">Demo passcode</label>
          <input id="pg-passcode" type="password" autocomplete="off" ${has ? 'placeholder="Saved for this tab"' : ''}>
          <button class="button" type="submit">${has ? 'Replace passcode' : 'Use passcode'}</button>
          ${has ? '<button class="link-button" type="button" id="pg-forget">Forget it</button>' : ''}</div>
        <p id="pg-pass-status" class="note" role="status"></p></form>`;
    } else {
      holder.innerHTML = '';
    }
  }

  function setLevel(level) {
    ui.level = level;
    root.querySelector(`[name="pg-level"][value="${level}"]`).checked = true;
    renderContext();
    renderPanels();
  }

  function renderContext() {
    const {level, working, recording, requested} = ui;
    const preset = currentPreset();
    const city = preset?.context?.user?.city || ui.contexts?.regular.user?.city;
    find('context-description').textContent = level === 'C2' && city ? `Uses the built-in brands and places around ${city}.` : levels[level].blurb;
    find('context-summary').textContent = level === 'C4' ? 'Inspect the misleading call hints' : 'View or edit call hints';
    find('context-details').hidden = ['C0', 'C2'].includes(level);
    hints('regular').hidden = !!preset || level !== 'C3';
    hints('wrong').hidden = !!preset || level !== 'C4';
    for (const mode of ['regular', 'wrong']) {
      const form = hints(mode);
      const button = form.querySelector('[data-apply-hints]');
      const status = form.querySelector('[data-hint-status]');
      const saved = ui.contexts?.[mode];
      const changed = saved !== undefined && JSON.stringify(readHints(form)) !== JSON.stringify(saved);
      status.hidden = !changed;
      status.textContent = changed ? 'These edits apply when you compare again.' : '';
      button.hidden = !changed;
      button.disabled = working || !!recording || requested;
    }
    find('preset-hints').hidden = !preset;
    if (preset) find('preset-hints').innerHTML = contextFacts(preset[level === 'C4' ? 'context_adv' : 'context']);
  }

  function renderControls() {
    const busy = ui.working || ui.requested || !!ui.recording;
    find('record').hidden = !!ui.recording;
    find('record').disabled = busy;
    find('record').innerHTML = ui.requested ? 'Waiting for the microphone…' : `${icon('mic')} Record from the microphone`;
    for (const name of ['stop', 'cancel', 'time']) find(name).hidden = !ui.recording;
    for (const name of ['stop', 'cancel']) find(name).disabled = !!ui.recording?.stopping;
    for (const name of ['upload', 'type', 'submit-text']) find(name).disabled = busy;
    for (const button of root.querySelectorAll('[data-preset]')) {
      button.disabled = busy;
      button.setAttribute('aria-pressed', String(button.dataset.preset === currentPreset()?.id));
    }
    renderContext();
  }

  // ---- samples ----
  function renderSamples() {
    const busy = ui.working || ui.requested || !!ui.recording;
    find('samples').innerHTML = ui.presets.length
      ? ui.presets.map(p => sampleCard(p, {selected: p.id === currentPreset()?.id, disabled: busy})).join('')
      : emptySamples();
  }

  const samplesReady = (async () => {
    ui.config = await siteConfig();
    renderLiveNote();
    try {
      ui.presets = await loadPresets();
    } catch (error) {
      find('samples').innerHTML = `<li class="state-box is-error"><strong>Sample calls unavailable</strong>${esc(error.message)}</li>`;
      return;
    }
    renderSamples();
  })();

  // ---- recording ----
  async function record() {
    if (!await ensureLive(null)) return;
    if (!canRecord()) { find('mic-note').textContent = 'Microphone recording is not available in this browser. Upload audio or paste a transcript instead.'; return; }
    find('mic-note').textContent = '';
    ui.requested = true;
    renderControls();
    try {
      const handle = await startRecording(text => { find('elapsed').textContent = text; });
      ui.recording = {handle, stopping: false};
      report('Recording. Choose Stop and compare when you finish.');
    } catch (error) {
      find('mic-note').textContent = micProblem(error);
      report(micProblem(error));
    } finally {
      ui.requested = false;
      renderControls();
      (ui.recording ? find('stop') : find('record')).focus();
    }
  }

  async function stopRecording(cancel) {
    const active = ui.recording;
    if (!active || active.stopping) return;
    active.stopping = true;
    renderControls();
    const take = await (cancel ? active.handle.cancel() : active.handle.finish());
    ui.recording = null;
    renderControls();
    if (cancel) { report('Recording canceled.'); find('record').focus(); return; }
    if (!take) { report('No audio was captured. Try recording again.'); find('record').focus(); return; }
    void startCompare({audio: take.blob, filename: take.filename, label: 'Microphone recording'});
  }

  // ---- gate to live features ----
  async function ensureLive(input) {
    const {mode, live_available: available, live_needs_passcode: needsCode} = ui.config;
    if (mode === 'public' && !available) {
      report('Live audio is off on this deployment. The sample calls still work.');
      find('live-note').scrollIntoView({block: 'nearest'});
      return false;
    }
    if (needsCode && !getPasscode()) {
      ui.pending = input;
      report('Enter the demo passcode to use live audio.');
      const field = root.querySelector('#pg-passcode');
      if (field) { field.focus(); root.querySelector('#pg-pass-status').textContent = 'Enter the demo passcode, then try again.'; }
      return false;
    }
    return true;
  }

  // ---- playback ----
  function updatePlayback(input) {
    if (ui.audioUrl) URL.revokeObjectURL(ui.audioUrl);
    ui.audioUrl = input.audio ? URL.createObjectURL(input.audio) : null;
    const src = ui.audioUrl || input.preset?.audio_url || '';
    find('playback-error').hidden = true;
    if (src) {
      find('audio-label').textContent = `Listen: ${input.preset?.label || input.label}`;
      find('audio').src = src;
    } else {
      find('audio').removeAttribute('src');
      find('audio').load();
    }
    find('playback').hidden = !src;
  }

  // ---- rendering results ----
  function renderPanels() {
    const baseResult = getResult(BASE_ID);
    const mainId = getMain();
    const mainResult = getResult(mainId);
    const common = {level: ui.level, done: ui.done, ui};
    setHtml(find('base'), resultPanel({id: BASE_ID, result: baseResult, error: ui.errors.get(BASE_ID), baseline: true, ...common}));
    setHtml(find('main'), resultPanel({id: mainId, result: mainResult, error: ui.errors.get(mainId), baseline: false, ...common}));
    const story = mainResult && ui.input ? storyBanner({base: baseResult, main: mainResult, input: ui.input, level: ui.level}) : '';
    if (story) setHtml(find('story'), story);
    setHtml(find('scorecard'), mainResult && baseResult ? scorecardBlock(baseResult, mainResult, ui.level) : '');
    renderApproaches();
  }

  function renderApproaches() {
    if (!ui.run) {
      find('approach-count').textContent = '';
      return;
    }
    const systems = ui.run.systems;
    find('approach-count').textContent = `${ui.results.size + ui.errors.size} of ${systems.length} finished`;
    const html = systems.map(system => {
      const {id} = system;
      const result = ui.results.get(id);
      const error = ui.errors.get(id);
      const status = result ? 'Ready' : error ? 'Failed' : ui.done ? 'No result' : 'Waiting';
      const extra = system.kind === 'pehchaan' ? `Pehchaan processing ${result?.timings_ms?.total ?? '—'} ms, LLM calls ${result?.llm_calls ?? '—'}`
        : system.kind === 'naive_llm' ? `Rewrite time ${result?.timings_ms?.total ?? '—'} ms` : '';
      return `<details data-system="${esc(id)}"><summary><span>${esc(systemTitle(id))}${systemInfo(id) ? info(systemInfo(id)) : ''}</span><span class="note">${status}</span></summary>
        ${result ? `<div class="approach-content"><p class="approach-text">${esc(result.text) || 'No speech was transcribed.'}</p><p class="note">${esc(extra)}</p></div>`
        : `<p class="approach-content note">${esc(error || (ui.done ? 'No result returned.' : 'Waiting for this approach…'))}</p>`}</details>`;
    }).join('');
    const holder = find('approach-items');
    const open = new Set([...holder.querySelectorAll('details[open]')].map(d => d.dataset.system));
    if (holder.cache !== html) {
      holder.cache = html;
      holder.innerHTML = html;
      for (const d of holder.querySelectorAll('details')) d.open = open.has(d.dataset.system);
    }
  }

  function accept(event) {
    if (event.event === 'started') { ui.run = event; find('approach-items').cache = null; }
    else if (event.event === 'result') ui.results.set(event.system_id, event.result);
    else if (event.event === 'system_error') ui.errors.set(event.system_id, event.message);
    else if (event.event === 'done') ui.done = true;
    renderPanels();
  }

  async function startCompare(input, {playSelection = false} = {}) {
    if (ui.working || ui.recording || ui.requested) return;
    const live = !input.preset;
    if (live && !await ensureLive(input)) return;
    const leavingTrap = currentPreset()?.initial_level === 'C4' && ui.level === 'C4';
    if (ui.input !== input) updatePlayback(input);
    ui.input = input;
    ui.contexts = input.preset ? null : {regular: readHints(hints('regular')), wrong: readHints(hints('wrong'))};
    Object.assign(ui, {working: true, run: null, done: false, canReplay: false, replaying: null, confirming: null});
    for (const map of [ui.results, ui.errors, ui.replays, ui.verdicts]) map.clear();
    find('story').innerHTML = `<div class="state-box"><strong>Comparing this call…</strong>Results appear as each approach finishes.</div>`;
    find('story').cache = null;
    renderControls();
    renderSamples();
    renderPanels();
    if (input.preset && Object.hasOwn(levels, input.preset.initial_level)) setLevel(input.preset.initial_level);
    else if (leavingTrap) setLevel('C3');
    report('Comparing this call. Results appear as each approach finishes.');
    if (playSelection) find('audio').play().catch(() => {});
    root.querySelector('.results').scrollIntoView({behavior: reduced ? 'auto' : 'smooth', block: 'start'});

    const fields = new FormData();
    if (input.preset) fields.append('preset', input.preset.id);
    else {
      if (input.audio) fields.append('audio', input.audio, input.filename); else fields.append('text', input.text);
      fields.append('context', JSON.stringify(ui.contexts.regular));
      fields.append('context_adv', JSON.stringify(ui.contexts.wrong));
    }
    try {
      await postCompare(fields, accept, {live});
      if (!ui.done) throw new Error('The comparison stream closed early.');
      report(ui.errors.size ? `Comparison finished. ${plural(ui.errors.size, 'approach', 'approaches')} failed.` : 'Comparison complete.');
    } catch (error) {
      ui.done = true;
      const problem = liveProblem(error);
      report(problem.text);
      if (!ui.results.size) find('story').innerHTML = `<div class="state-box is-error"><strong>The comparison could not run</strong>${esc(problem.text)}</div>`;
      if (problem.kind === 'passcode') {
        setPasscode('');
        ui.pending = input;
        renderLiveNote();
        root.querySelector('#pg-pass-status').textContent = problem.text;
        root.querySelector('#pg-passcode')?.focus();
      }
    } finally {
      ui.working = false;
      renderControls();
      renderSamples();
      renderPanels();
    }
  }

  // ---- learning: confirm, test, replay, undo ----
  async function refreshLedger() {
    try {
      ui.ledger = await learningLedger();
    } catch {
      ui.ledger = [];
    }
    ui.canReplay = ui.ledger.some(e => e.active) || [...ui.verdicts.values()].some(v => v.adopted);
    setHtml(find('ledger'), ledger(ui.ledger));
  }

  async function confirm(form, canonical) {
    const id = getMain();
    const run = ui.run;
    const entityId = form.dataset.confirm;
    const key = `${id}:${entityId}`;
    if (!canonical || ui.confirming || !run) return;
    ui.confirming = key;
    renderPanels();
    report('Testing this correction on labelled calls…');
    try {
      const verdict = await confirmCorrection(run.run_id, {system_id: id, entity_id: entityId, canonical});
      if (ui.run !== run) return;
      ui.verdicts.set(key, verdict);
      ui.confirming = null;
      await refreshLedger();
      renderPanels();
      report(verdict.adopted
        ? `Adopted. Tested on ${verdict.clips_replayed} labelled calls with ${verdict.facts_harmed} facts harmed.`
        : 'Not adopted. Nothing was saved. The checks below say why.');
      (find('main').querySelector(verdict.adopted ? '[data-replay]' : '.verdict') || find('main')).focus?.();
    } catch (error) {
      ui.confirming = null;
      renderPanels();
      const status = find('main').querySelector(`[data-confirm="${CSS.escape(entityId)}"] .confirm-status`);
      if (status) status.textContent = error.message;
      report(error.message);
    }
  }

  async function replay() {
    if (ui.replaying || ui.working) { report('Wait for the current comparison to finish before replaying.'); return; }
    const id = getMain();
    const run = ui.run;
    ui.replaying = id;
    renderPanels();
    try {
      const result = await replayCall(run.run_id, id);
      if (ui.run !== run) return;
      ui.replays.set(id, result);
      const hits = Array.isArray(result.memory_hits) ? result.memory_hits.length : (result.memory_hits || 0);
      report(`Replay complete. ${hits} memory ${hits === 1 ? 'hit' : 'hits'} and ${result.llm_calls ?? 'unmeasured'} LLM calls.`);
    } catch (error) {
      report(error.message);
    } finally {
      if (ui.run === run) {
        ui.replaying = null;
        renderPanels();
        find('main').querySelector('[data-replay]')?.focus();
      }
    }
  }

  async function undo(eventId) {
    try {
      await rollbackCorrection(eventId);
      for (const [key, verdict] of [...ui.verdicts]) if (String(verdict.event_id) === String(eventId)) ui.verdicts.delete(key);
      ui.replays.clear();
      await refreshLedger();
      renderPanels();
      report('Undone. Pehchaan no longer applies that correction. Replay shows the original result again.');
    } catch (error) {
      report(error.message);
    }
  }

  // ---- events ----
  find('record').addEventListener('click', record);
  find('stop').addEventListener('click', () => void stopRecording(false));
  find('cancel').addEventListener('click', () => void stopRecording(true));
  find('audio').addEventListener('error', () => { find('playback-error').hidden = find('playback').hidden; });
  find('upload').addEventListener('click', async () => { if (await ensureLive(null)) find('file').click(); });
  find('type').addEventListener('click', async event => {
    const button = event.currentTarget;
    const form = find('typed-form');
    if (form.hidden && !await ensureLive(null)) return;
    form.hidden = !form.hidden;
    button.setAttribute('aria-expanded', String(!form.hidden));
    if (!form.hidden) find('transcript').focus();
  });
  find('file').addEventListener('change', event => {
    const audio = event.currentTarget.files[0];
    if (audio) void startCompare({audio, filename: audio.name, label: audio.name});
    event.currentTarget.value = '';
  });
  root.addEventListener('change', event => { if (event.target.name === 'pg-level') setLevel(event.target.value); });
  root.addEventListener('input', event => { if (event.target.hasAttribute('data-hint')) renderContext(); });
  root.addEventListener('submit', event => {
    const form = event.target;
    if (form === find('typed-form')) {
      event.preventDefault();
      const text = find('transcript').value.trim();
      if (text) void startCompare({text}); else report('Enter a transcript to compare.');
    } else if (form.matches('[data-confirm]')) {
      event.preventDefault();
      void confirm(form, form.elements.canonical?.value.trim());
    } else if (form.id === 'pg-pass') {
      event.preventDefault();
      const field = form.querySelector('#pg-passcode');
      if (!field.value.trim()) { form.querySelector('#pg-pass-status').textContent = 'Type the passcode first.'; return; }
      setPasscode(field.value.trim());
      renderLiveNote();
      report('Passcode saved for this tab.');
      if (ui.pending) { const input = ui.pending; ui.pending = null; void startCompare(input); }
    }
  });
  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.id === 'pg-forget') { setPasscode(''); renderLiveNote(); report('Passcode forgotten.'); return; }
    if (button.dataset.preset) {
      const preset = ui.presets.find(p => p.id === button.dataset.preset);
      if (preset) void startCompare({preset}, {playSelection: true});
    } else if (button.hasAttribute('data-apply-hints')) void startCompare(ui.input);
    else if (button.hasAttribute('data-evidence')) {
      const panel = button.closest('[id="pg-base"], [id="pg-main"]');
      const baseline = panel === find('base');
      showEvidence(dialog, {result: getResult(baseline ? BASE_ID : getMain()), entityId: button.dataset.evidence, baseline});
    } else if (button.hasAttribute('data-callback')) {
      openNote(dialog, 'Callback preview', `<p class="preview-number">${esc(button.dataset.callback)}</p><p class="note">No call has been placed.</p>`);
    } else if (button.hasAttribute('data-choice')) void confirm(button.closest('form'), button.dataset.choice);
    else if (button.hasAttribute('data-replay')) void replay();
    else if (button.hasAttribute('data-undo')) void undo(button.dataset.undo);
  });

  renderControls();
  renderPanels();
  void refreshLedger();

  return {
    async openSample(id) {
      await samplesReady;
      const preset = ui.presets.find(p => p.id === id);
      if (preset) void startCompare({preset}, {playSelection: false});
    },
  };
}
