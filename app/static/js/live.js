// Your own call: live microphone over WS /v1/stream, an audio file, or a transcript pasted from any speech model.
import {badge, elapsed, esc, icon, factWord, ms} from './util.js';
import {info} from './info.js';
import {canStream, openMic, startPcm} from './pcm.js';
import {getPasscode, setPasscode, getOpenAIKey, setOpenAIKey, hasLiveAccess, liveAuth, verifyAudio, verifyTranscript} from './api.js';
import {micProblem} from './recorder.js';

const STATUS = {FIXED: 'fixed', VERIFIED: 'verified', HEARD: 'heard', FLAGGED: 'ask'};
const EVIDENCE = {exam: 'This exact setup sat the locked exam.', dev: 'This model was measured on development and sample calls, not the exam.',
  unmeasured: 'No benchmark covers this setup, so treat it as a demo.'};

const layout = `
  <form class="live-auth" id="live-auth" autocomplete="off">
    <p><strong>${icon('lock')} Live calls use a paid model.</strong> Enter the demo passcode, or use your own OpenAI key. Your key stays in this tab's memory and is sent only with your request.</p>
    <div class="live-auth-row">
      <label>Demo passcode<input id="live-pass" type="password" autocomplete="off"></label>
      <label>Or your OpenAI key<input id="live-key" type="password" autocomplete="off" placeholder="sk-..."></label>
      <button class="button" type="submit">Use it</button>
      <button class="link-button" type="button" id="live-forget">Forget</button>
    </div>
    <p class="note" id="live-auth-status" role="status"></p>
  </form>
  <div class="live-tabs" role="tablist" aria-label="How to send your call">
    <button role="tab" type="button" data-tab="mic" aria-selected="true">${icon('mic')} Live mic</button>
    <button role="tab" type="button" data-tab="file" aria-selected="false">${icon('upload')} Audio file</button>
    <button role="tab" type="button" data-tab="paste" aria-selected="false">${icon('type')} Paste any transcript</button>
  </div>
  <div data-pane="mic">
    <p class="note">Speak up to 30 seconds. Each phrase is checked when you pause, then the whole call is checked again at the end. Each phrase counts as one live request.</p>
    <div class="rec-row">
      <button class="button button-primary" id="live-start" type="button">${icon('mic')} Start</button>
      <button class="button button-primary" id="live-stop" type="button" hidden>${icon('stop')} Stop</button>
      <span class="rec-time" id="live-time" hidden><span class="rec-dot" aria-hidden="true"></span><time id="live-elapsed">00:00</time></span>
    </div>
  </div>
  <div data-pane="file" hidden>
    <p class="note">Up to 30 seconds and 5 MB. It goes to the speech model selected above.</p>
    <input id="live-file" type="file" accept="audio/*,.webm,.mp4,.m4a,.flac,.wav,.mp3,.ogg,.mpeg,.mpga" aria-label="Choose an audio file">
  </div>
  <form data-pane="paste" id="live-paste" hidden>
    <label>Transcript from your speech model (Deepgram, Sarvam, Google, Azure, anything)<textarea id="live-text" rows="3" required></textarea></label>
    <label>Second transcript of the same audio <span class="muted">(optional, a stronger check)</span><textarea id="live-alt" rows="2"></textarea></label>
    <label>Speech model name <span class="muted">(optional)</span><input id="live-model" type="text" maxlength="60"></label>
    <button class="button button-primary" type="submit">Verify transcript</button>
  </form>
  <details class="live-context"><summary>What the phone knows about this call${info('context')}</summary>
    <div class="hint-fields">
      <label>City<input id="live-city" type="text"></label>
      <label>Contacts <span>(one name per line)</span><textarea id="live-contacts" rows="2"></textarea></label>
      <label>Saved places <span>(one per line)</span><textarea id="live-places" rows="2"></textarea></label>
    </div>
  </details>
  <p id="live-status" class="status-line" role="status" aria-live="polite"></p>
  <div id="live-out"></div>`;

const factRow = fact => `<li>${badge(STATUS[fact.status])}<span><b>${esc(factWord(fact.type))}:</b> ${esc(fact.value)}${fact.heard !== fact.value ? ` <span class="muted">(heard “${esc(fact.heard)}”)</span>` : ''}<small>${esc(fact.reason)}</small></span></li>`;

function resultCard(result) {
  const t = result.telemetry;
  return `<article class="live-result">
    <div class="call-pair">
      <section class="call-side"><h3>Speech model (${esc(t.model)})</h3><p class="transcript">${esc(result.raw_text)}</p></section>
      <section class="call-side is-main"><h3>With Pehchaan</h3><p class="transcript">${esc(result.verified_text)}</p></section>
    </div>
    ${result.clarifier_prompt ? `<p class="live-ask">${badge('ask')} <span>${esc(result.clarifier_prompt)}</span></p>` : ''}
    <ul class="live-facts">${result.entities.map(factRow).join('') || '<li class="muted">No facts found.</li>'}</ul>
    <p class="note">${t.stt_ms ? `Speech ${ms(t.stt_ms)}, ` : ''}Pehchaan ${ms(t.harness_ms)}, LLM judge ${t.judge === 'on' ? `${t.judge_calls} calls` : 'off'}. ${esc(EVIDENCE[t.evidence])}</p>
  </article>`;
}

export function mountLive(root, {model}) {
  root.innerHTML = layout;
  const find = name => root.querySelector(`#live-${name}`);
  const say = text => { find('status').textContent = text; };
  let session = null;

  const lines = name => find(name).value.split('\n').map(x => x.trim()).filter(Boolean);
  function context() {
    const out = {};
    if (find('city').value.trim()) out.user = {city: find('city').value.trim()};
    if (lines('contacts').length) out.contacts = lines('contacts').map(name => ({name}));
    if (lines('places').length) out.places = lines('places');
    return out;
  }

  function showAuth() {
    find('pass').placeholder = getPasscode() ? 'Saved for this tab' : '';
    find('key').placeholder = getOpenAIKey() ? 'Held in this tab' : 'sk-...';
  }

  function needAccess() {
    if (hasLiveAccess()) return true;
    find('auth-status').textContent = 'Enter the demo passcode or your own key first.';
    find('pass').focus();
    return false;
  }

  function failed(error) {
    say(error.message || 'Something went wrong. Try again.');
    if (error.status === 401) {
      find('auth-status').textContent = error.message;
      setPasscode('');
      setOpenAIKey('');
      showAuth();
    }
  }

  async function run(work, label) {
    if (!needAccess()) return;
    say(label);
    find('out').innerHTML = '';
    try {
      find('out').innerHTML = resultCard(await work());
      say('Done.');
    } catch (error) {
      failed(error);
    }
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
      say(message.result ? 'Done. This is the whole call, checked again.' : 'No speech was heard.');
      finish();
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
    if (session || !needAccess()) return;
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
    socket.onopen = () => socket.send(JSON.stringify({type: 'start', mode: 'audio', model: model(), auth: liveAuth(), context: context()}));
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
        const seconds = (Date.now() - began) / 1000;
        find('elapsed').textContent = elapsed(seconds);
        if (seconds >= message.limits.max_audio_seconds - 0.5) stop();
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
    const pass = find('pass').value.trim();
    const key = find('key').value.trim();
    if (pass) setPasscode(pass);
    if (key) setOpenAIKey(key);
    find('pass').value = '';
    find('key').value = '';
    find('auth-status').textContent = pass || key ? 'Ready for live calls in this tab.' : 'Type a passcode or a key first.';
    showAuth();
  });
  find('forget').addEventListener('click', () => {
    setPasscode('');
    setOpenAIKey('');
    find('auth-status').textContent = 'Forgotten.';
    showAuth();
  });
  root.addEventListener('click', event => {
    const tab = event.target.closest('[data-tab]');
    if (!tab) return;
    for (const button of root.querySelectorAll('[data-tab]')) button.setAttribute('aria-selected', String(button === tab));
    for (const pane of root.querySelectorAll('[data-pane]')) pane.hidden = pane.dataset.pane !== tab.dataset.tab;
  });
  find('start').addEventListener('click', () => void start());
  find('stop').addEventListener('click', () => void stop());
  find('file').addEventListener('change', event => {
    const file = event.currentTarget.files[0];
    event.currentTarget.value = '';
    if (file) void run(() => verifyAudio(file, context(), model()), `Checking ${file.name}…`);
  });
  find('paste').addEventListener('submit', event => {
    event.preventDefault();
    const text = find('text').value.trim();
    if (text) void run(() => verifyTranscript({text, alt_text: find('alt').value.trim() || null, model: find('model').value.trim() || 'external', context: context()}), 'Checking the transcript…');
  });
  showAuth();
}
