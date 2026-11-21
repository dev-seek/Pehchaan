// Your voice: connect, choose a speech model and language, then speak, upload or paste a transcript.
import {badge, elapsed, esc, icon, factWord, ms, plural} from './util.js';
import {info} from './info.js';
import {canStream, openMic, startPcm} from './pcm.js';
import {connectLive, forgetLive, savedSecret, siteConfig, liveAuth, verifyAudio, verifyTranscript} from './api.js';
import {micProblem} from './recorder.js';
import {modelBlurb} from './lead.js';

const STATUS = {FIXED: 'fixed', VERIFIED: 'verified', HEARD: 'heard', FLAGGED: 'ask'};
const EVIDENCE = {exam: 'This setup sat the locked exam.', dev: 'Measured on development calls, not the exam.', unmeasured: 'No benchmark covers this setup.'};
const TIERS = [
  ['partial', 'Partial: names, places, digits', 'Names, places and digit numbers work. Spoken money and numbers are kept as said and flagged for a person.'],
  ['unsupported', 'Not supported yet', 'Not built for this language. Digit numbers may work. Names and spoken money will not.'],
];
const AUTO_NOTE = 'Hindi, Hinglish and Indian English are tested on real voice. Telugu is tested on synthetic voice only.';

const layout = `
  <ol class="steps">
    <li class="step is-now" id="live-step-connect"><span class="step-n" id="live-n1" aria-hidden="true">1</span><div class="step-body">
      <h3>Connect</h3>
      <form class="connect" id="live-auth" autocomplete="off">
        <label>Demo passcode or OpenAI key<input id="live-secret" type="password" autocomplete="off" placeholder="Passcode or sk-..."></label>
        <button class="button button-primary" id="live-connect" type="submit">Connect</button>
      </form>
      <div class="connected" id="live-connected" role="status" hidden></div>
      <p class="note" id="live-auth-note">Your key stays in this tab and is sent only with your requests.</p>
      <p class="form-error" id="live-auth-error" role="alert" hidden></p>
    </div></li>
    <li class="step is-todo" id="live-step-choose"><span class="step-n" id="live-n2" aria-hidden="true">2</span><div class="step-body">
      <h3>Choose a speech model${info('asr')}</h3>
      <fieldset id="live-choose" disabled>
        <legend class="sr-only">Speech model</legend>
        <div class="voice-models" id="live-models"></div>
        <label class="lang">Language<select id="live-language"></select></label>
        <p class="note" id="live-language-note">${AUTO_NOTE}</p>
        <details class="live-context"><summary>Add what the phone knows${info('context')}</summary>
          <div class="hint-fields">
            <label>City<input id="live-city" type="text"></label>
            <label>Contacts <span>(one per line)</span><textarea id="live-contacts" rows="2"></textarea></label>
            <label>Saved places <span>(one per line)</span><textarea id="live-places" rows="2"></textarea></label>
          </div>
        </details>
      </fieldset>
    </div></li>
    <li class="step is-todo" id="live-step-speak"><span class="step-n" aria-hidden="true">3</span><div class="step-body">
      <h3>Speak</h3>
      <fieldset id="live-speak" disabled>
        <legend class="sr-only">Send your call</legend>
        <div class="live-tabs" role="tablist" aria-label="How to send your call">
          <button role="tab" type="button" data-live-tab="mic" aria-selected="true">${icon('mic')} Mic</button>
          <button role="tab" type="button" data-live-tab="file" aria-selected="false">${icon('upload')} Audio file</button>
          <button role="tab" type="button" data-live-tab="paste" aria-selected="false">${icon('type')} Paste text</button>
        </div>
        <div data-pane="mic">
          <div class="rec-row">
            <button class="button button-primary" id="live-start" type="button">${icon('mic')} Start speaking</button>
            <button class="button button-primary" id="live-stop" type="button" hidden>${icon('stop')} Stop</button>
            <span class="rec-time" id="live-time" hidden><span class="rec-dot" aria-hidden="true"></span><time id="live-elapsed">00:00</time></span>
          </div>
          <p class="note">Up to 30 seconds. Pause between phrases. Each phrase uses one live request.</p>
        </div>
        <div data-pane="file" hidden>
          <input id="live-file" type="file" accept="audio/*,.webm,.mp4,.m4a,.flac,.wav,.mp3,.ogg,.mpeg,.mpga" aria-label="Choose an audio file">
          <p class="note">Up to 30 seconds and 5 MB.</p>
        </div>
        <form data-pane="paste" id="live-paste" hidden>
          <label>Transcript from any speech model<textarea id="live-text" rows="3" required></textarea></label>
          <button class="button button-primary" type="submit">Check transcript</button>
        </form>
      </fieldset>
    </div></li>
  </ol>
  <p id="live-status" class="status-line" role="status" aria-live="polite"></p>
  <div id="live-out"></div>`;

const factRow = fact => `<li>${badge(STATUS[fact.status])}<span><b>${esc(factWord(fact.type))}:</b> ${esc(fact.value)}${fact.heard !== fact.value ? ` <span class="muted">(heard “${esc(fact.heard)}”)</span>` : ''}<small>${esc(fact.reason)}</small></span></li>`;

function resultCard(result) {
  const t = result.telemetry;
  return `<article class="live-result">
    <div class="call-pair">
      <section class="call-side"><h3>${esc(t.model)} alone</h3><p class="transcript">${esc(result.raw_text)}</p></section>
      <section class="call-side is-main"><h3>With Pehchaan</h3><p class="transcript">${esc(result.verified_text)}</p></section>
    </div>
    ${result.clarifier_prompt ? `<p class="live-ask">${badge('ask')} <span>${esc(result.clarifier_prompt)}</span></p>` : ''}
    <ul class="live-facts">${result.entities.map(factRow).join('') || '<li class="muted">No facts found.</li>'}</ul>
    <p class="note">${t.stt_ms ? `Speech ${ms(t.stt_ms)}. ` : ''}Pehchaan ${ms(t.harness_ms)}. ${esc(EVIDENCE[t.evidence])}</p>
  </article>`;
}

function languageOptions(lab) {
  const rows = lab?.languages?.languages || [];
  const groups = TIERS.map(([tier, title]) => {
    const list = rows.filter(r => r.tier === tier);
    return list.length ? `<optgroup label="${esc(title)}">${list.map(r => `<option value="${esc(r.code)}" data-tier="${tier}">${esc(r.name)}</option>`).join('')}</optgroup>` : '';
  });
  return `<option value="">Auto: Hindi, Hinglish, English, Telugu</option>${groups.join('')}`;
}

export function mountLive(root, {lab}) {
  root.innerHTML = layout;
  const find = name => root.querySelector(`#live-${name}`);
  const say = text => { find('status').textContent = text; };
  const state = {connected: null, model: null, activated: false};
  let session = null;
  find('language').innerHTML = languageOptions(lab);

  const lines = name => find(name).value.split('\n').map(x => x.trim()).filter(Boolean);
  const language = () => find('language').value || undefined;
  function context() {
    const out = {};
    if (find('city').value.trim()) out.user = {city: find('city').value.trim()};
    if (lines('contacts').length) out.contacts = lines('contacts').map(name => ({name}));
    if (lines('places').length) out.places = lines('places');
    return out;
  }

  // ---- step 1: connect ----
  function setSteps() {
    const on = Boolean(state.connected);
    find('choose').disabled = !on;
    find('speak').disabled = !on;
    find('step-connect').className = `step ${on ? 'is-done' : 'is-now'}`;
    find('step-choose').className = `step ${on ? 'is-now' : 'is-todo'}`;
    find('step-speak').className = `step ${on ? 'is-now' : 'is-todo'}`;
    find('n1').innerHTML = on ? icon('check', 14) : '1';
    find('auth').hidden = on;
    find('auth-note').hidden = on;
    find('connected').hidden = !on;
  }

  function showConnected(answer) {
    state.connected = answer;
    const who = {byok: 'your OpenAI key', passcode: 'the demo passcode', local: 'this laptop'}[answer.kind];
    const left = answer.limits.left_this_hour;
    find('connected').innerHTML = `<span class="connected-mark">${icon('check', 16)}</span>
      <span><b>Connected with ${who}.</b> ${plural(answer.models.length, 'speech model')} ready${answer.kind === 'local' ? '' : `, ${left} of ${answer.limits.per_hour} live requests left this hour`}.</span>
      ${answer.kind === 'local' ? '' : '<button class="link-button" type="button" id="live-forget">Disconnect</button>'}`;
    const preferred = answer.models.find(m => m.id === state.model) || answer.models.find(m => m.evidence === 'exam') || answer.models[0];
    state.model = preferred.id;
    find('models').innerHTML = answer.models.map(m => `<label class="voice-model${m.id === state.model ? ' is-on' : ''}">
      <input type="radio" name="live-model" value="${esc(m.id)}" ${m.id === state.model ? 'checked' : ''}><span><b>${esc(m.id)}</b><small>${esc(modelBlurb(m))}</small></span></label>`).join('');
    find('auth-error').hidden = true;
    setSteps();
  }

  async function connect(secret, quiet = false) {
    find('connect').disabled = true;
    find('connect').textContent = 'Checking…';
    find('auth-error').hidden = true;
    try {
      showConnected(await connectLive(secret));
      find('secret').value = '';
      if (!quiet) { say(''); find('models').querySelector('input:checked')?.focus(); }
    } catch (error) {
      forgetLive();
      state.connected = null;
      setSteps();
      if (!quiet) {
        find('auth-error').textContent = error.message || 'Could not connect. Try again.';
        find('auth-error').hidden = false;
        find('secret').focus();
      }
    } finally {
      find('connect').disabled = false;
      find('connect').textContent = 'Connect';
    }
  }

  function disconnect(message) {
    forgetLive();
    state.connected = null;
    setSteps();
    if (message) {
      find('auth-error').textContent = message;
      find('auth-error').hidden = false;
    }
  }

  function failed(error) {
    say(error.message || 'Something went wrong. Try again.');
    if (error.status === 401) disconnect(error.message);
  }

  async function run(work, label) {
    if (!state.connected) return;
    say(label);
    find('out').innerHTML = '';
    try {
      find('out').innerHTML = resultCard(await work());
      say('');
      void refreshCount();
    } catch (error) {
      failed(error);
    }
  }

  async function refreshCount() {
    const secret = savedSecret();
    if (!state.connected || state.connected.kind === 'local' || !secret) return;
    try { showConnected(await connectLive(secret)); } catch { /* the next request will report it */ }
  }

  // ---- live stream ----
  function streamView() {
    find('out').innerHTML = `<article class="live-result"><h3>As you speak</h3><ol class="live-phrases" id="live-phrases"></ol>
      <p class="live-ask" id="live-question" hidden></p><ul class="live-facts" id="live-facts"></ul></article>`;
  }

  function onEvent(message) {
    if (message.type === 'phrase') {
      find('phrases').insertAdjacentHTML('beforeend', `<li>${esc(message.text)} <small class="muted">${ms(message.stt_ms)} speech, ${ms(message.harness_ms)} check</small></li>`);
    } else if (message.type === 'fact') {
      find('facts').insertAdjacentHTML('beforeend', factRow(message.fact));
    } else if (message.type === 'clarifier') {
      const box = find('question');
      box.hidden = false;
      box.innerHTML = `${badge('ask')} <span>${esc(message.prompt)}</span>`;
    } else if (message.type === 'final') {
      find('out').innerHTML = message.result ? resultCard(message.result) : '<p class="note">No speech was heard.</p>';
      say(message.result ? '' : 'No speech was heard. Try again a little closer to the mic.');
      finish();
      void refreshCount();
    } else if (message.type === 'error') {
      failed({message: message.message, status: message.status});
      finish();
    }
  }

  function buttons(on) {
    find('start').hidden = on;
    find('stop').hidden = !on;
    find('time').hidden = !on;
  }

  async function finish() {
    const active = session;
    session = null;
    buttons(false);
    if (!active) return;
    clearInterval(active.timer);
    await active.mic?.stop().catch(() => {});
    if (active.socket?.readyState === WebSocket.OPEN) active.socket.close();
  }

  async function start() {
    if (session || !state.connected) return;
    if (!canStream()) { say('Live streaming is not available in this browser. Upload a file instead.'); return; }
    const capture = openMic();          // must stay before the first await
    const active = {socket: null, mic: null, timer: null, held: [], live: false};
    session = active;
    say('Waiting for the microphone…');
    try {
      active.mic = await startPcm(capture, chunk => {
        if (!active.live) active.held.push(chunk);
        else if (active.socket.readyState === WebSocket.OPEN) active.socket.send(chunk);
      });
    } catch (error) {
      session = null;
      say(micProblem(error));
      return;
    }
    if (session !== active) { await active.mic.stop(); return; }
    const began = Date.now();           // audio held while connecting counts toward the limit
    say('Connecting…');
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/v1/stream`);
    active.socket = socket;
    socket.onerror = () => { if (session === active) { say('The live connection failed. Try again.'); finish(); } };
    socket.onclose = () => { if (session === active) { say('The live connection closed.'); finish(); } };
    socket.onopen = () => socket.send(JSON.stringify({type: 'start', mode: 'audio', model: state.model, language: language(), auth: liveAuth(), context: context()}));
    socket.onmessage = ({data}) => {
      const message = JSON.parse(data);
      if (message.type !== 'ready') { onEvent(message); return; }
      streamView();
      for (const chunk of active.held) socket.send(chunk);
      active.held = [];
      active.live = true;
      buttons(true);
      say('Listening. Pause between phrases.');
      active.timer = setInterval(() => {
        const seconds = Math.floor((Date.now() - began) / 1000);
        find('elapsed').textContent = elapsed(seconds);
        if (seconds >= message.limits.max_audio_seconds - 1) stop();
      }, 250);
    };
  }

  async function stop() {
    const active = session;
    if (!active?.mic) return;
    clearInterval(active.timer);
    const mic = active.mic;
    active.mic = null;
    find('stop').hidden = true;
    say('Checking the whole call…');
    await mic.stop();
    if (active.socket.readyState === WebSocket.OPEN) active.socket.send(JSON.stringify({type: 'stop'}));
  }

  // ---- events ----
  find('auth').addEventListener('submit', event => {
    event.preventDefault();
    const secret = find('secret').value.trim();
    if (!secret) {
      find('auth-error').textContent = 'Enter the demo passcode or your OpenAI key.';
      find('auth-error').hidden = false;
      find('secret').focus();
      return;
    }
    void connect(secret);
  });
  find('language').addEventListener('change', event => {
    const tier = event.target.selectedOptions[0]?.dataset.tier;
    find('language-note').textContent = TIERS.find(([id]) => id === tier)?.[2] || AUTO_NOTE;
  });
  root.addEventListener('change', event => {
    if (event.target.name !== 'live-model') return;
    state.model = event.target.value;
    for (const label of root.querySelectorAll('.voice-model')) label.classList.toggle('is-on', label.contains(event.target));
  });
  root.addEventListener('click', event => {
    if (event.target.closest('#live-forget')) { disconnect(); say(''); find('out').innerHTML = ''; return; }
    const tab = event.target.closest('[data-live-tab]');
    if (!tab) return;
    for (const button of root.querySelectorAll('[data-live-tab]')) button.setAttribute('aria-selected', String(button === tab));
    for (const pane of root.querySelectorAll('[data-pane]')) pane.hidden = pane.dataset.pane !== tab.dataset.liveTab;
  });
  find('start').addEventListener('click', () => void start());
  find('stop').addEventListener('click', () => void stop());
  find('file').addEventListener('change', event => {
    const file = event.currentTarget.files[0];
    event.currentTarget.value = '';
    if (file) void run(() => verifyAudio(file, context(), state.model, language()), `Checking ${file.name}…`);
  });
  find('paste').addEventListener('submit', event => {
    event.preventDefault();
    const text = find('text').value.trim();
    if (text) void run(() => verifyTranscript({text, model: 'external', context: context(), language: language() || null}), 'Checking the transcript…');
  });
  setSteps();

  return {
    async activate() {
      if (state.activated) return;
      state.activated = true;
      const config = await siteConfig();
      if (savedSecret()) await connect(savedSecret(), true);
      else if (config.live_needs_passcode === false) await connect('', true);
    },
  };
}
