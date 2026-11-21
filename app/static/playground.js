const levels = {
  C0: ['Rules only', 'Uses speech and number rules without call hints.'],
  C2: ['Known brands and places', 'Adds the built-in brand and locality lists.'],
  C3: ['This call’s context', 'Uses the contacts, caller ID, messages, and places below.'],
  C4: ['Wrong-context test', 'Uses deliberately misleading hints to test what the system will trust.'],
};

const facts = [
  ['Caller', ['PERSON', 'ORG']], ['Place', ['PLACE']], ['Amount', ['AMOUNT']],
  ['Postal PIN', ['PIN']], ['Callback', ['PHONE']],
];
const labels = {FIXED: 'Fixed', CONFIRMED: 'Verified', FLAGGED: 'Flagged', KEPT: 'Heard', RAW: 'Heard'};
const tones = {FIXED: 'fixed', CONFIRMED: 'verified', FLAGGED: 'flagged'};
const stages = {prepare: 'Transcript preparation', numbers: 'Number rules', memory: 'Confirmed memory', names: 'Name and place matching'};

const symbols = {
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-3 0h6"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  play: '<path d="m9 5 11 7-11 7z"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  type: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01m4 0h.01m4 0h.01m4 0h.01M6 13h.01m4 0h.01m4 0h.01m4 0h.01M8 16h8"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  phone: '<path d="M22 17v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3l2 5-3 2a14 14 0 0 0 9 9l2-3z"/>',
  context: '<path d="M4 7h16M4 12h16M4 17h16M9 5v4m7 1v4m-7 1v4"/>',
  compare: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16m-6-11h3m6 0h3m-12 5h3m6 0h3"/>',
  replay: '<path d="M3 12a9 9 0 1 1 3 7m-3-1v-6h6"/>',
};
const icon = name => `<svg class="pg-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${symbols[name]}</svg>`;
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const milliseconds = value => Number.isFinite(value) ? `${Number(value.toFixed(1)).toLocaleString('en-IN')} ms` : 'Unavailable';
const clock = seconds => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
const aliases = {
  B0_asr_plain: 'Plain speech-to-text',
  B1_asr_keywords_C3: 'Keyword-assisted speech-to-text (C3)',
  B1_asr_keywords_C4: 'Keyword-assisted speech-to-text (C4)',
  B2_naive_llm_C3: 'Generative rewrite (C3)',
  B2_naive_llm_C4: 'Generative rewrite (C4)',
  P_C0: 'Pehchaan · rules only (C0)',
  P_C2: 'Pehchaan · known brands and places (C2)',
  P_C3: 'Pehchaan · speech-to-text without keywords (C3)',
  P_C4: 'Pehchaan · speech-to-text without keywords (C4)',
  P_on_B1_C3: 'Pehchaan · keyword-assisted (C3)',
  P_on_B1_C4: 'Pehchaan · keyword-assisted (C4)',
};
const titleOf = id => aliases[id] || id;
const baseId = 'B0_asr_plain';

const layout = `
  <section class="pg-intro" aria-labelledby="pg-title">
    <h1 id="pg-title">Live Call Playground</h1>
    <p class="lede">Say a name, a place, and a callback number. See what the speech model heard and what Pehchaan could verify.</p>
  </section>
  <div class="pg-input-grid">
    <section class="pg-panel pg-recorder" aria-labelledby="pg-record-title">
      <h2 class="sr-only" id="pg-record-title">Call input</h2>
      <div class="pg-buttons">
        <button class="button button-primary" id="pg-record" type="button">${icon('mic')} Record Live Mic</button>
        <button class="button button-primary" id="pg-stop" type="button" hidden>${icon('stop')} Stop and Compare</button>
        <button class="button" id="pg-cancel" type="button" hidden>Cancel recording</button>
        <span class="pg-time" id="pg-time" hidden>${icon('clock')} <time id="pg-elapsed">00:00</time></span>
      </div>
      <div id="pg-playback" hidden>
        <label id="pg-audio-label" for="pg-audio"></label>
        <audio id="pg-audio" controls preload="metadata" aria-labelledby="pg-audio-label"></audio>
        <p id="pg-playback-error" class="pg-note" role="status" hidden>Playback unavailable for this audio.</p>
      </div>
      <div class="pg-fallback">
        <button class="pg-link-button" id="pg-upload" type="button">${icon('upload')} Upload audio</button>
        <input id="pg-file" type="file" accept="audio/*,.webm,.mp4,.m4a,.flac,.wav,.mp3,.ogg,.mpeg,.mpga" hidden>
        <button class="pg-link-button" id="pg-type" type="button" aria-expanded="false" aria-controls="pg-typed-form">${icon('type')} Use a transcript</button>
      </div>
      <form id="pg-typed-form" hidden>
        <label for="pg-transcript">Call transcript</label>
        <textarea id="pg-transcript" rows="3" placeholder="Paste or type what the caller said." required></textarea>
        <button class="button button-primary" id="pg-submit-text" type="submit">Compare transcript ${icon('arrow')}</button>
      </form>
    </section>
    <section class="pg-panel pg-presets" aria-labelledby="pg-preset-title">
      <h2 id="pg-preset-title">Try a sample call</h2>
      <div id="pg-presets" class="pg-preset-list"><p>Loading sample calls…</p></div>
    </section>
  </div>
  <div class="pg-progress">
    <p id="pg-status" class="pg-status" role="status" aria-live="polite"></p>
    <button id="pg-view-results" class="pg-link-button" type="button" hidden>View comparison ${icon('arrow')}</button>
  </div>
  <section class="pg-context" aria-labelledby="pg-context-title">
    <h2 id="pg-context-title">${icon('context')} What the phone knows</h2>
    <fieldset class="pg-levels">
      <legend class="sr-only">Pehchaan context level</legend>
      ${Object.entries(levels).map(([key, [label]]) =>
        `<label><input type="radio" name="pg-level" value="${key}" ${key === 'C3' ? 'checked' : ''}><span>${label} <b>${key}</b></span></label>`).join('')}
    </fieldset>
    <p id="pg-context-description" class="pg-note"></p>
    <details id="pg-context-details"><summary id="pg-context-summary">View or edit call hints</summary>
      <div id="pg-context-content">
        <div id="pg-preset-hints" hidden></div>
        ${['regular', 'wrong'].map(mode => `<div class="pg-hints" id="pg-hints-${mode}" hidden>
          <p class="pg-note">${mode === 'wrong' ? 'These hints are deliberately misleading. Use a contact, caller ID, message, or place that conflicts with the call.' : 'Live calls start with empty hints. Add details before comparing a call.'}</p>
          <div class="pg-hint-fields">
            <label>Contacts <span>(one name per line)</span><textarea rows="2" data-hint="contacts"></textarea></label>
            <label>Saved places <span>(one per line)</span><textarea rows="2" data-hint="places"></textarea></label>
            <label>Caller ID name<input type="text" data-hint="callerName"></label>
            <label>Caller ID number<input type="tel" data-hint="callerNumber"></label>
            <label>SMS sender<input type="text" data-hint="smsSender"></label>
            <label>SMS message<textarea rows="2" data-hint="smsBody"></textarea></label>
            <label>City<input type="text" data-hint="city"></label>
          </div>
          <p class="pg-note pg-hint-status" data-hint-status hidden></p>
          <button type="button" class="button pg-apply" data-apply-hints hidden>Compare again with edited hints</button>
        </div>`).join('')}
      </div>
    </details>
  </section>
  <section class="pg-results" aria-labelledby="pg-result-title">
    <div class="pg-results-top">
      <div><h2 id="pg-result-title" tabindex="-1">Call comparison</h2>
      <p id="pg-result-note" class="pg-note">Record a call or choose a sample to compare transcripts and facts.</p></div>
      <details class="pg-method">
        <summary>How decisions work</summary>
        <dl>
          <dt>Number rules</dt><dd>Check whether a number fits the expected format and flag uncertainty. Call hints never change a phone number, postal PIN, or amount.</dd>
          <dt>Sound matching</dt><dd>Compares how names and places sound across spellings and scripts.</dd>
          <dt>Second transcript</dt><dd>Checks what the speech model hears on the same audio without call keywords.</dd>
          <dt>Model verifier</dt><dd>Looks at the unclear facts. The call count shows requests made for this run.</dd>
          <dt>Confirmed memory</dt><dd>Reuses names and places explicitly confirmed in this session.</dd>
        </dl>
      </details>
    </div>
    <div class="pg-results-grid">
      <article class="pg-panel pg-result" id="pg-base"></article>
      <article class="pg-panel pg-result pg-result-main" id="pg-main"></article>
    </div>
    <details class="pg-approaches" id="pg-approaches">
      <summary>All approaches <span id="pg-approach-count" class="pg-note"></span></summary>
      <div id="pg-approach-items"><p class="pg-note">Approaches appear as they finish.</p></div>
    </details>
  </section>
  <dialog id="pg-detail-dialog" aria-labelledby="pg-dialog-title">
    <form method="dialog" class="pg-dialog-top"><h2 id="pg-dialog-title"></h2><button class="button" value="close">Close</button></form>
    <div id="pg-dialog-body"></div>
  </dialog>`;

function readHints(hints) {
  const get = key => hints.querySelector(`[data-hint="${key}"]`).value.trim();
  const lines = key => get(key).split('\n').map(line => line.trim()).filter(Boolean);
  const caller = {cnap_name: get('callerName'), number: get('callerNumber')};
  const sms = {sender: get('smsSender'), body: get('smsBody')};
  const context = {};
  if (lines('contacts').length) context.contacts = lines('contacts').map(name => ({name}));
  if (lines('places').length) context.places = lines('places');
  if (caller.cnap_name || caller.number) context.caller = caller;
  if (sms.sender || sms.body) context.sms = [sms];
  if (get('city')) context.user = {city: get('city')};
  return context;
}

function contextFacts(context) {
  const {caller, contacts, places, sms, user, domain} = context || {};
  const items = [
    ['Contacts', contacts?.map(c => [c.name, c.number].filter(Boolean).join(' · '))],
    ['Caller ID', [[caller?.cnap_name, caller?.number].filter(Boolean).join(' · ')]],
    ['Messages', sms?.map(s => [s.sender, s.body].filter(Boolean).join(' · '))],
    ['Saved places', places],
    ['City', [user?.city]],
    ['Call type', [domain]],
  ];
  return `<dl class="pg-context-facts">${items.map(([label, values]) => {
    const lines = (values || []).filter(Boolean);
    return `<div><dt>${label}</dt><dd>${lines.length ? lines.map(escape).join('<br>') : 'None supplied'}</dd></div>`;
  }).join('')}</dl>`;
}

function hasSilentError(result, entity) {
  const scored = result.scored || {};
  const scoredFacts = scored.entities?.filter(fact => fact.type === entity.etype);
  if (scoredFacts?.length > 1) return false;
  return result.entities.filter(candidate => candidate.etype === entity.etype).length === 1 &&
    scored.silent_errors?.includes(entity.etype);
}

function factState(entity, result, baseline) {
  if (baseline && hasSilentError(result, entity)) return ['error', 'Silent error'];
  return [tones[entity.status] || 'neutral', baseline ? 'Heard' : (labels[entity.status] || 'Heard')];
}

function passage(result, baseline) {
  const characters = [...(result.text || '')];
  let cursor = 0;
  let markup = '';
  const spans = (result.entities || []).slice().sort((first, second) => first.start - second.start);
  for (const entity of spans) {
    const {start, end} = entity;
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < cursor || end <= start || end > characters.length) continue;
    const [tone, state] = factState(entity, result, baseline);
    const literal = characters.slice(start, end).join('');
    markup += escape(characters.slice(cursor, start).join(''));
    markup += `<button class="pg-span pg-${tone}" type="button" data-evidence="${escape(entity.id)}" aria-label="${escape(literal)} · ${state}">${escape(literal)}</button>`;
    cursor = end;
  }
  return markup + escape(characters.slice(cursor).join('')) || 'No speech was transcribed.';
}

function summaryCard(result, baseline) {
  return `<section class="pg-summary"><h4>Call Summary &amp; Action Card</h4>
    <dl class="pg-facts">${facts.map(([label, types]) => {
      const distinct = new Map();
      for (const entity of result.entities.filter(item => types.includes(item.etype))) {
        const key = `${entity.etype}:${entity.value || entity.surface}`;
        if (!distinct.has(key) || entity.status === 'FLAGGED') distinct.set(key, entity);
      }
      const matches = [...distinct.values()];
      if (!matches.length) {
        const knownError = baseline && result.scored?.silent_errors?.some(type => types.includes(type));
        return `<div><dt>${label}</dt><dd><span class="pg-note">Not detected</span>
          ${knownError ? '<span class="pg-badge pg-error">Silent error</span>' : ''}</dd></div>`;
      }
      const multiple = matches.length > 1 && (label !== 'Caller' || new Set(matches.map(entity => entity.etype)).size < matches.length);
      const content = matches.map(entity => {
        const [tone, state] = factState(entity, result, baseline);
        return `<button class="pg-fact-value" type="button" data-evidence="${escape(entity.id)}">${escape(entity.display || entity.surface || entity.value || 'Unclear')}</button>
          <span class="pg-badge pg-${tone}">${state}</span>`;
      });
      return `<div><dt>${label}</dt><dd>${content.map(value => `<div class="pg-fact-line">${value}</div>`).join('')}
        ${multiple ? '<span class="pg-note">Multiple values heard</span>' : ''}</dd></div>`;
    }).join('')}</dl>
    <div class="pg-summary-action">${callbackAction(result, baseline)}</div>
  </section>`;
}

function callbackAction(result, baseline) {
  const numbers = result.entities.filter(entity => entity.etype === 'PHONE');
  if (!numbers.length) return '<p class="pg-note">Callback unavailable · No number heard</p>';
  if (new Set(numbers.map(number => number.value)).size > 1) {
    return '<p class="pg-note">Callback blocked · Conflicting numbers</p>';
  }
  if (numbers.some(number => number.status === 'FLAGGED') || (baseline && result.scored?.silent_errors?.includes('PHONE'))) {
    return '<p class="pg-note">Callback blocked · Number needs review</p>';
  }
  if (!/^(?:\+91)?[6-9]\d{9}$/.test(numbers[0].value)) {
    return '<p class="pg-note">Callback unavailable · Number is incomplete</p>';
  }
  return `<button class="button pg-callback" type="button" data-callback="${escape(numbers[0].display || numbers[0].value)}">${icon('phone')} Preview callback</button>`;
}

function reviewQuestions(result, confirmed) {
  if (!result.questions?.length) return '';
  return `<section class="pg-questions" aria-label="Details to review">${result.questions.map(question => {
    const entity = result.entities.find(candidate => candidate.id === question.entity_id);
    if (!entity) return '';
    const maySave = ['PERSON', 'PLACE'].includes(entity.etype);
    const saved = confirmed.get(entity.id);
    const choices = (question.choices || []).filter(Boolean);
    const list = choices.length ? `<ul>${choices.map(choice => `<li>${escape(choice)}</li>`).join('')}</ul>` : '<p>Repeat that detail</p>';
    return `<div class="pg-question">
      <p><span class="pg-badge pg-flagged">Flagged</span> ${escape(question.question)}</p>
      ${maySave ? `<form class="pg-confirm" data-confirm="${escape(entity.id)}">
        ${saved ? `<p class="pg-saved">${icon('check')} Saved for replay · ${escape(saved)}</p>` : `
          ${choices.length ? `<div class="pg-buttons">${choices.map(choice => `<button class="button" type="button" data-choice="${escape(choice)}">Confirm ${escape(choice)}</button>`).join('')}</div>` : '<p>Repeat that detail</p>'}
          <label>Enter the correct name or place <input name="canonical" type="text" required autocomplete="off"></label>
          <button type="submit" class="button">Save confirmation</button>`}
        <p class="pg-confirm-status" role="status"></p>
      </form>` : `${list}<p class="pg-note">Review only · This detail stays as heard.</p>`}
    </div>`;
  }).join('')}</section>`;
}

function timingDetails(result) {
  const times = Object.entries(result.timings_ms || {}).filter(([key, value]) => key !== 'total' && Number.isFinite(value));
  const asr = result.asr || [];
  return `<details class="pg-timings"><summary>Models and stage timings</summary>
    <dl>
      ${asr.filter(source => source.model !== 'typed').map(source => `<div><dt>${source.role === 'second_opinion' ? 'Second transcript' : 'Speech-to-text'} · ${escape(source.model)}</dt>
        <dd>${milliseconds(source.latency_ms)}${source.cached ? ' (cached model time)' : ''}</dd></div>`).join('')}
      ${times.map(([name, value]) => `<div><dt>${escape(stages[name] || name.replaceAll('_', ' '))} stage total</dt><dd>${milliseconds(value)}</dd></div>`).join('')}
      ${Number.isFinite(result.rewrite_calls) ? `<div><dt>Generative rewrite calls</dt><dd>${result.rewrite_calls}</dd></div>` : ''}
      ${Number.isFinite(result.verifier_cache_hits) ? `<div><dt>Verifier cache hits</dt><dd>${result.verifier_cache_hits}</dd></div>` : ''}
      ${asr.every(source => source.model === 'typed') && !times.length ? '<div><dt>Speech-to-text</dt><dd>No model timing for this input</dd></div>' : ''}
    </dl>
  </details>`;
}

async function checkResponse(response) {
  if (response.ok) return response;
  let message = `Request failed (HTTP ${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') message = body.detail;
  } catch { /* The response may not include a JSON detail. */ }
  throw new Error(message);
}

async function consumeEvents(response, onEvent) {
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

export function mountPlayground(root) {
  root.classList.add('playground');
  root.innerHTML = layout;
  const find = name => root.querySelector(`#pg-${name}`);
  const state = {
    level: 'C3', working: false, requested: false, recording: null, audioUrl: null,
    presets: [], input: null, contexts: null, run: null, results: new Map(), errors: new Map(), replays: new Map(),
    confirmed: new Map(), memoryAvailable: false, replaying: null, confirming: false, done: false,
  };

  const report = message => { find('status').textContent = message; };
  const getMain = () => ({C0: 'P_C0', C2: 'P_C2', C3: state.run?.main_system, C4: 'P_on_B1_C4'})[state.level];
  const getResult = id => state.replays.get(id) || state.results.get(id);
  const currentPreset = () => state.input?.preset;
  const hints = mode => find(`hints-${mode}`);
  const dialog = find('detail-dialog');

  function setLevel(level) {
    state.level = level;
    root.querySelector(`[name="pg-level"][value="${level}"]`).checked = true;
    renderContext();
    renderPanel('main', getMain(), false, true);
  }

  function renderContext() {
    const {level, working, recording, requested} = state;
    const preset = currentPreset();
    const city = preset?.context?.user?.city || state.contexts?.regular.user?.city;
    find('context-description').textContent = level === 'C2' && city ?
      `Uses built-in brands and places around ${city}.` : levels[level][1];
    find('context-summary').textContent = level === 'C4' ? 'Inspect misleading call hints' : 'View or edit call hints';
    find('context-details').hidden = ['C0', 'C2'].includes(level);
    hints('regular').hidden = !!preset || level !== 'C3';
    hints('wrong').hidden = !!preset || level !== 'C4';
    for (const mode of ['regular', 'wrong']) {
      const form = hints(mode);
      const button = form.querySelector('[data-apply-hints]');
      const status = form.querySelector('[data-hint-status]');
      const saved = state.contexts?.[mode];
      const changed = saved !== undefined && JSON.stringify(readHints(form)) !== JSON.stringify(saved);
      status.hidden = !changed;
      status.textContent = changed ? 'These edits will apply when you compare again.' : '';
      button.hidden = !changed;
      button.disabled = working || !!recording || requested;
    }
    find('preset-hints').hidden = !preset;
    if (preset) find('preset-hints').innerHTML = contextFacts(preset[level === 'C4' ? 'context_adv' : 'context']);
  }

  function renderControls() {
    const disabled = state.working || state.requested || !!state.recording;
    find('record').hidden = !!state.recording;
    find('record').disabled = disabled;
    find('record').innerHTML = state.requested ? 'Waiting for microphone…' : `${icon('mic')} Record Live Mic`;
    for (const name of ['stop', 'cancel', 'time']) find(name).hidden = !state.recording;
    for (const name of ['stop', 'cancel']) find(name).disabled = !!state.recording?.stopping;
    for (const name of ['upload', 'type', 'submit-text']) find(name).disabled = disabled;
    for (const button of root.querySelectorAll('[data-preset]')) {
      button.disabled = disabled;
      button.setAttribute('aria-pressed', String(button.dataset.preset === currentPreset()?.id));
    }
    renderContext();
  }

  async function loadPresets() {
    try {
      const response = await checkResponse(await fetch('/api/demo/presets'));
      state.presets = await response.json();
      const markup = state.presets.map(preset => `
        <button class="pg-preset" type="button" data-preset="${escape(preset.id)}" aria-pressed="false">
          <span class="pg-preset-play">${icon('play')}</span>
          <span><strong>${escape(preset.label)}</strong><small>${escape(preset.voice_source)}</small></span>
          ${icon('arrow')}
        </button>`).join('');
      find('presets').innerHTML = markup || '<p>No sample calls are available.</p>';
      renderControls();
    } catch (error) {
      find('presets').textContent = `Sample calls unavailable. ${error.message}`;
    }
  }

  function updatePlayback(input) {
    if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
    state.audioUrl = input.audio ? URL.createObjectURL(input.audio) : null;
    const src = state.audioUrl || input.preset?.audio_url;
    find('playback-error').hidden = true;
    if (src) {
      find('audio-label').textContent = input.preset?.label || input.label;
      find('audio').src = src;
    } else {
      find('audio').removeAttribute('src');
      find('audio').load();
    }
    find('playback').hidden = !src;
  }

  async function record() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      report('Microphone recording is unavailable in this browser. Upload audio or use a transcript.');
      return;
    }
    state.requested = true;
    renderControls();
    let media;
    let recorder;
    try {
      media = await navigator.mediaDevices.getUserMedia({audio: true});
      recorder = new MediaRecorder(media);
      const active = {recorder, startedAt: performance.now(), discarded: false, stopping: false, chunks: []};
      recorder.addEventListener('dataavailable', event => {
        if (event.data.size) active.chunks.push(event.data);
      });
      recorder.addEventListener('error', () => {
        active.discarded = true;
        report('The microphone recording failed. Try again or upload audio.');
        if (!active.stopping) stopRecording(false);
      });
      recorder.addEventListener('stop', () => {
        clearInterval(active.timer);
        media.getTracks().forEach(track => track.stop());
        state.recording = null;
        renderControls();
        if (active.discarded) {
          find('record').focus();
          return;
        }
        const type = recorder.mimeType || active.chunks[0]?.type || '';
        const audio = new Blob(active.chunks, {type});
        if (!audio.size) {
          report('No audio was captured. Try recording again.');
          find('record').focus();
          return;
        }
        const format = {'audio/mp4': 'm4a', 'audio/ogg': 'ogg', 'audio/wav': 'wav'}[type.split(';')[0]] || 'webm';
        void compare({audio, filename: `recording.${format}`, label: 'Microphone recording'});
        find('audio').focus();
      });
      recorder.start();
      state.recording = active;
      find('elapsed').textContent = '00:00';
      active.timer = setInterval(() => {
        find('elapsed').textContent = clock(Math.floor((performance.now() - active.startedAt) / 1000));
      }, 250);
      report('Recording. Choose Stop and Compare when you finish.');
    } catch {
      media?.getTracks().forEach(track => track.stop());
      report('Microphone access failed. Allow microphone access or upload audio or a transcript.');
    } finally {
      state.requested = false;
      renderControls();
      (state.recording ? find('stop') : find('record')).focus();
    }
  }

  function stopRecording(cancel) {
    const active = state.recording;
    if (!active || active.stopping) return;
    active.stopping = true;
    if (cancel) {
      active.discarded = true;
      report('Recording canceled.');
    }
    if (active.recorder.state !== 'inactive') active.recorder.stop();
    renderControls();
  }

  function showResultsNote(message) {
    find('result-note').textContent = message;
  }

  function renderPanel(panel, id, baseline, force = false) {
    const item = find(panel);
    const result = getResult(id);
    const error = state.errors.get(id);
    const signature = [state.input, id, result, error, !result && state.done, !baseline && state.memoryAvailable,
      !baseline && state.memoryAvailable && state.working, state.replaying === id,
      result?.questions?.map(question => state.confirmed.get(`${id}:${question.entity_id}`) || '').join()];
    if (!force && item.signature?.every((value, index) => value === signature[index])) return;
    item.signature = signature;
    const heading = baseline ? 'Base Model' : 'With Pehchaan';
    const subtitle = baseline ? (state.input?.text ? 'Typed transcript' : 'Plain speech-to-text') : levels[state.level][0];
    item.dataset.system = id || '';
    item.innerHTML = `<div class="pg-panel-heading"><span class="pg-icon-box">${icon(baseline ? 'mic' : 'check')}</span>
      <div><h3>${heading}</h3><p>${subtitle}</p></div></div>`;
    if (!result) {
      const prompt = state.input ? (state.done ? 'This approach returned no result.' : 'Waiting for this approach…') : (baseline ? 'What the speech model heard.' : 'Which facts were fixed, verified, or flagged.');
      item.insertAdjacentHTML('beforeend', `<p class="pg-placeholder${error ? ' pg-unavailable' : ''}">${escape(error ? `Approach failed. ${error}` : prompt)}</p>`);
      return;
    }
    const replaying = state.replaying === id;
    const replay = state.replays.get(id) === result;
    const confirmed = new Map((result.questions || []).map(question => [question.entity_id, state.confirmed.get(`${id}:${question.entity_id}`)]));
    item.insertAdjacentHTML('beforeend', `<div class="pg-result-content">
      <section class="pg-transcript"><h4>Transcript</h4><p>${passage(result, baseline)}</p></section>
      ${summaryCard(result, baseline)}
      ${baseline ? '' : reviewQuestions(result, confirmed)}
      ${!baseline && state.memoryAvailable ? `<div class="pg-replay">
        <button class="button" type="button" data-replay ${replaying || state.working ? 'disabled' : ''}>${icon('replay')} ${replaying ? 'Replaying…' : 'Replay Same Call'}</button>
        <p class="pg-note">${replay ? `Replay · ${milliseconds(result.replay_ms ?? result.timings_ms?.total)} · ${memoryCount(result.memory_hits)} memory ${memoryCount(result.memory_hits) === 1 ? 'hit' : 'hits'}` : 'Uses the same speech-to-text input and turns off the model verifier.'}</p>
      </div>` : ''}
      <div class="pg-run-meta">
        ${!baseline ? `<span>Pehchaan processing · ${milliseconds(result.timings_ms?.total)}</span><span>Verifier calls · ${result.llm_calls ?? 'Unavailable'}</span>` : ''}
        ${timingDetails(result)}
      </div>
    </div>`);
  }

  function memoryCount(hits) {
    return Array.isArray(hits) ? hits.length : (hits || 0);
  }

  function renderApproaches() {
    if (!state.run) {
      find('approach-count').textContent = '';
      find('approach-items').innerHTML = '<p class="pg-note">Approaches appear as they finish.</p>';
      return;
    }
    const systems = state.run.systems;
    find('approach-count').textContent = `${state.results.size + state.errors.size} / ${systems.length} finished`;
    for (const system of systems) {
      const {id} = system;
      const holder = find('approach-items');
      let details = holder.querySelector(`[data-system="${CSS.escape(id)}"]`);
      const result = state.results.get(id);
      const error = state.errors.get(id);
      if (!details) {
        details = document.createElement('details');
        details.dataset.system = id;
        holder.append(details);
      }
      const done = !result && !error && state.done;
      if (details.result === result && details.error === error && details.done === done) continue;
      Object.assign(details, {result, error, done});
      const status = result ? 'Ready' : error ? 'Failed' : state.done ? 'Unavailable' : 'Waiting';
      details.innerHTML = `<summary><span>${escape(titleOf(id))}</span><span class="pg-note">${status}</span></summary>
        ${result ? `<div class="pg-approach-content"><p class="pg-approach-text">${escape(result.text) || 'No speech was transcribed.'}</p>
          <p class="pg-note">${system.kind === 'pehchaan' ? `Pehchaan processing · ${milliseconds(result.timings_ms?.total)} · Verifier calls ${result.llm_calls}` :
          system.kind === 'naive_llm' ? `Rewrite time · ${milliseconds(result.timings_ms?.total)}` : ''}</p>${timingDetails(result)}</div>` :
          `<p class="pg-approach-content pg-note">${escape(error || (state.done ? 'No result returned.' : 'Waiting for this approach…'))}</p>`}`;
    }
  }

  function renderResults() {
    find('view-results').hidden = !state.results.size;
    renderPanel('base', baseId, true);
    renderPanel('main', getMain(), false);
    renderApproaches();
  }

  function accept(event) {
    if (event.event === 'started') {
      state.run = event;
      find('approach-items').replaceChildren();
    } else if (event.event === 'result') {
      state.results.set(event.system_id, event.result);
    } else if (event.event === 'system_error') {
      state.errors.set(event.system_id, event.message);
    } else if (event.event === 'done') {
      state.done = true;
    }
    renderResults();
  }

  async function compare(input, playSelection = false) {
    if (state.working || state.recording || state.requested) return;
    const leavingWrongContext = currentPreset()?.initial_level === 'C4' && state.level === 'C4';
    if (state.input !== input) updatePlayback(input);
    state.input = input;
    state.contexts = input.preset ? null : {
      regular: readHints(hints('regular')),
      wrong: readHints(hints('wrong')),
    };
    state.working = true;
    state.run = null;
    state.done = false;
    state.memoryAvailable = false;
    state.results.clear();
    state.errors.clear();
    state.replays.clear();
    state.confirmed.clear();
    state.replaying = null;
    renderControls();
    renderResults();
    if (input.preset && Object.hasOwn(levels, input.preset.initial_level)) setLevel(input.preset.initial_level);
    else if (leavingWrongContext) setLevel('C3');
    if (playSelection) find('audio').play().catch(() => {});
    report('Comparing this call. Results appear as each approach finishes.');
    showResultsNote(input.preset ? `${input.preset.label} · ${input.preset.voice_source}` :
      input.text ? 'Typed input · Speech recognition is skipped.' : input.label);
    const fields = new FormData();
    if (input.preset) fields.append('preset', input.preset.id);
    else {
      if (input.audio) fields.append('audio', input.audio, input.filename);
      else fields.append('text', input.text);
      fields.append('context', JSON.stringify(state.contexts.regular));
      fields.append('context_adv', JSON.stringify(state.contexts.wrong));
    }

    try {
      const response = await checkResponse(await fetch('/api/demo/compare', {method: 'POST', body: fields}));
      await consumeEvents(response, accept);
      if (!state.done) throw new Error('The comparison stream closed early.');
      report(state.errors.size ? `Comparison finished with ${state.errors.size} failed ${state.errors.size === 1 ? 'approach' : 'approaches'}.` : 'Comparison complete.');
    } catch (error) {
      state.done = true;
      report(error.message);
    } finally {
      state.working = false;
      renderControls();
      renderResults();
    }
  }

  function openDialog(title, body) {
    find('dialog-title').textContent = title;
    find('dialog-body').innerHTML = body;
    dialog.showModal();
  }

  function evidence(id, entityId, baseline) {
    const result = getResult(id);
    const entity = result?.entities.find(item => String(item.id) === entityId);
    if (!entity) return;
    const [tone, decision] = factState(entity, result, baseline);
    const stage = ['PHONE', 'PIN', 'AMOUNT'].includes(entity.etype) ? 'numbers' : entity.source === 'memory' ? 'memory' : 'names';
    const sourceNames = {rule: 'Number or language rules', context: 'Call hints', lexicon: 'Known brands and places', memory: 'Confirmed memory', llm: 'Model verifier', asr: 'Speech-to-text', transcript: 'Transcript', contacts: 'Contacts', caller_id: 'Caller ID', sms: 'Messages', saved_places: 'Saved places'};
    const expected = tone === 'error' ? result.scored?.entities?.filter(item => item.type === entity.etype && !item.correct && !item.flagged) : [];
    const model = result.asr?.[0];
    openDialog(facts.find(([, types]) => types.includes(entity.etype))?.[0] || 'Fact evidence', `
      <p><span class="pg-badge pg-${tone}">${decision}</span></p>
      <dl class="pg-evidence">
        <div><dt>Heard text</dt><dd>${escape(entity.surface)}</dd></div>
        <div><dt>Output</dt><dd>${escape(entity.display || entity.value || entity.surface)}</dd></div>
        <div><dt>Evidence</dt><dd>${escape(entity.reason || 'This fact came from the transcript.')}</dd></div>
        ${expected?.length === 1 ? `<div><dt>Known answer</dt><dd>${escape(expected[0].value)}</dd></div>` : ''}
        <div><dt>Source</dt><dd>${escape(sourceNames[entity.source?.split(':')[0]] || entity.source || 'Transcript')}</dd></div>
        ${baseline && model?.model === 'typed' ? '' : `<div><dt>${baseline ? 'Speech-to-text model time' : `${stages[stage]} stage total`}</dt><dd>${milliseconds(baseline ? model?.latency_ms : result.timings_ms?.[stage])}</dd></div>`}
      </dl>
      ${entity.admission === 'second_opinion' ? '<p class="pg-note">The second transcript provides evidence from the same audio without call keywords.</p>' : ''}
      ${timingDetails(result)}
    `);
  }

  async function sessionAction(action, fields) {
    if (!state.run?.run_id) throw new Error('Compare a call before using session memory.');
    const response = await checkResponse(await fetch(`/api/demo/${encodeURIComponent(state.run.run_id)}/${action}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(fields),
    }));
    return response.json();
  }

  async function confirm(form, canonical) {
    const id = getMain();
    const run = state.run;
    const entityId = form.dataset.confirm;
    const status = form.querySelector('.pg-confirm-status');
    if (!canonical || state.confirming) return;
    state.confirming = true;
    for (const control of form.elements) control.disabled = true;
    status.textContent = 'Saving confirmation…';
    try {
      await sessionAction('confirm', {system_id: id, entity_id: entityId, canonical});
      if (state.run !== run) return;
      state.confirmed.set(`${id}:${entityId}`, canonical);
      state.memoryAvailable = true;
      renderResults();
      if (getMain() === id) find('main').querySelector('[data-replay]')?.focus();
      report(`Saved ${canonical} for this session. Replay the same call to check memory.`);
    } catch (error) {
      status.textContent = error.message;
      for (const control of form.elements) control.disabled = false;
    } finally {
      state.confirming = false;
    }
  }

  async function replay() {
    if (state.replaying || state.working) {
      report('Wait for the current comparison to finish before replaying.');
      return;
    }
    const id = getMain();
    const run = state.run;
    state.replaying = id;
    renderResults();
    try {
      const result = await sessionAction('replay', {system_id: id});
      if (state.run !== run) return;
      state.replays.set(id, result);
      const hits = memoryCount(result.memory_hits);
      report(`Replay complete. ${hits} memory ${hits === 1 ? 'hit' : 'hits'} and ${result.llm_calls ?? 'unmeasured'} verifier calls.`);
    } catch (error) {
      report(error.message);
    } finally {
      if (state.run === run) {
        state.replaying = null;
        renderResults();
        if (getMain() === id) find('main').querySelector('[data-replay]')?.focus();
      }
    }
  }

  find('record').addEventListener('click', record);
  find('view-results').addEventListener('click', () => find('result-title').focus());
  find('stop').addEventListener('click', () => stopRecording(false));
  find('cancel').addEventListener('click', () => stopRecording(true));
  find('upload').addEventListener('click', () => find('file').click());
  find('audio').addEventListener('error', () => {
    find('playback-error').hidden = find('playback').hidden;
  });
  find('type').addEventListener('click', event => {
    const form = find('typed-form');
    form.hidden = !form.hidden;
    event.currentTarget.setAttribute('aria-expanded', String(!form.hidden));
    if (!form.hidden) find('transcript').focus();
  });
  find('file').addEventListener('change', event => {
    const audio = event.currentTarget.files[0];
    if (audio) void compare({audio, filename: audio.name, label: audio.name});
    event.currentTarget.value = '';
  });
  root.addEventListener('change', event => {
    if (event.target.name === 'pg-level') setLevel(event.target.value);
  });
  root.addEventListener('input', event => {
    if (event.target.hasAttribute('data-hint')) renderContext();
  });
  root.addEventListener('submit', event => {
    const {target} = event;
    if (target === find('typed-form')) {
      event.preventDefault();
      const text = find('transcript').value.trim();
      if (text) void compare({text});
      else report('Enter a transcript to compare.');
    } else if (target.matches('[data-confirm]')) {
      event.preventDefault();
      void confirm(target, target.elements.canonical.value.trim());
    }
  });
  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.preset) {
      const preset = state.presets.find(item => item.id === button.dataset.preset);
      if (preset) void compare({preset}, true);
    } else if (button.hasAttribute('data-apply-hints')) {
      void compare(state.input);
    } else if (button.hasAttribute('data-evidence')) {
      const panel = button.closest('[data-system]');
      evidence(panel.dataset.system, button.dataset.evidence, panel === find('base'));
    } else if (button.hasAttribute('data-callback')) {
      openDialog('Callback preview', `<p class="pg-preview-number">${escape(button.dataset.callback)}</p><p class="pg-note">No call has been placed.</p>`);
    } else if (button.hasAttribute('data-choice')) {
      void confirm(button.closest('form'), button.dataset.choice);
    } else if (button.hasAttribute('data-replay')) {
      void replay();
    }
  });

  renderControls();
  renderResults();
  void loadPresets();
}
