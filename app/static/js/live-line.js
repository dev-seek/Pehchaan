// Your voice: run the recording on its clear copy and a worse phone line, at the same time.
import {badge, esc, factWord, icon, ms} from './util.js';
import {lineTest} from './api.js';

const LINES = [['noisy', 'Noisy'], ['very_noisy', 'Very noisy'], ['dropouts', 'Dropouts']];
const VERDICT = {right: ['verified', 'Right'], asked: ['ask', 'Asked'], silent: ['wrong', 'Wrong, no warning']};
const SAMPLE_RATE = 16000;

/** 16 kHz mono 16-bit samples as a WAV file. */
export function wavFrom(chunks) {
  const bytes = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
  const out = new Uint8Array(44 + bytes);
  const view = new DataView(out.buffer);
  const text = (at, word) => [...word].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  text(0, 'RIFF'); view.setUint32(4, 36 + bytes, true); text(8, 'WAVE'); text(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, SAMPLE_RATE, true); view.setUint32(28, SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, bytes, true);
  let at = 44;
  for (const chunk of chunks) { out.set(new Uint8Array(chunk), at); at += chunk.byteLength; }
  return new File([out], 'recording.wav', {type: 'audio/wav'});
}

/** Says what this one take showed, including when Pehchaan did not help. */
export function verdictLine(score, label) {
  const alone = score.alone.silent;
  const checked = score.pehchaan.silent;
  const wrong = n => `${n} ${n === 1 ? 'fact' : 'facts'} wrong with no warning`;
  if (!score.alone.right && !score.alone.asked && !alone) return 'The clear copy had no facts to compare. Say a name, number, place or amount clearly.';
  if (!alone && !checked) return `The speech model got every fact right on the ${label} line, so there was nothing to catch. Run it again or pick another line.`;
  if (checked < alone) return `Speech alone: ${wrong(alone)}. With Pehchaan: ${checked ? wrong(checked) : 'none'}.`;
  if (checked === alone) return `Pehchaan did not catch these on this take: ${wrong(checked)}.`;
  return `Pehchaan did worse on this take: ${wrong(checked)}, against ${alone} for speech alone.`;
}

const mark = verdict => {
  const [kind, word] = VERDICT[verdict];
  return `<span class="line-mark is-${verdict}">${badge(kind, {withInfo: false, label: word})}</span>`;
};
const tally = side => `${side.right} right, ${side.asked} asked, ${side.silent} wrong`;

function copyCard(title, result, url, alone, score = null) {
  const count = side => (score ? ` <small>${esc(tally(score[side]))}</small>` : '');
  return `<section class="line-copy">
    <h4>${esc(title)}</h4>
    <audio controls preload="metadata" src="${esc(url)}"></audio>
    <dl>
      <dt>Speech alone${count('alone')}</dt><dd class="transcript">${esc(alone)}</dd>
      <dt>With Pehchaan${count('pehchaan')}</dt><dd class="transcript">${esc(result.verified_text)}</dd>
    </dl>
    ${result.clarifier_prompt ? `<p class="live-ask">${badge('ask')} <span>${esc(result.clarifier_prompt)}</span></p>` : ''}
  </section>`;
}

function resultView(answer, clearUrl, label) {
  const rows = answer.facts.map(f => `<tr><th scope="row">${esc(factWord(f.type))}: ${esc(f.value)}</th><td>${mark(f.alone)}</td><td class="is-ours">${mark(f.pehchaan)}</td></tr>`).join('');
  return `<p class="line-verdict" role="status">${esc(verdictLine(answer.noisy_score, label))}</p>
    <div class="line-copies">
      ${copyCard('Clear recording', answer.clear, clearUrl, answer.clear_alone)}
      ${copyCard(`${label} line`, answer.noisy, answer.noisy_audio, answer.noisy_alone, answer.noisy_score)}
    </div>
    ${rows ? `<div class="table-scroll" tabindex="0"><table class="line-table"><caption>Each fact on the ${esc(label.toLowerCase())} line</caption>
      <thead><tr><th scope="col">Fact both heard clearly</th><th scope="col">Speech alone</th><th scope="col">With Pehchaan</th></tr></thead><tbody>${rows}</tbody></table></div>` : ''}
    <p class="note">Your real voice on a simulated line. Scored by the benchmark's scorer on the facts both systems agreed on in the clear copy. Speech ${ms(Math.max(answer.clear.telemetry.stt_ms, answer.noisy.telemetry.stt_ms))}. Noise is random, so each run can differ.</p>`;
}

export function mountLine(box, {context, model, language, failed}) {
  let recording = null;
  let clearUrl = null;
  let line = 'very_noisy';
  let run = 0;

  function clear() {
    run += 1;
    recording = null;
    if (clearUrl) URL.revokeObjectURL(clearUrl);
    clearUrl = null;
    box.hidden = true;
    box.innerHTML = '';
  }

  function draw() {
    box.hidden = false;
    box.innerHTML = `<div class="line-head"><h3>Put it on a worse phone line</h3>
      <p class="note">The same noise the benchmark uses, added to your recording.</p></div>
      <div class="line-controls">
        <div class="seg" role="group" aria-label="Phone line">${LINES.map(([id, name]) => `<button type="button" data-line="${id}" aria-pressed="${id === line}">${name}</button>`).join('')}</div>
        <button class="button button-primary" type="button" data-line-run>${icon('play')} Add noise and run both</button>
      </div>
      <p class="status-line" data-line-status role="status" aria-live="polite"></p>
      <div data-line-out></div>`;
  }

  function offer(file) {
    clear();
    recording = file;
    clearUrl = URL.createObjectURL(file);
    draw();
  }

  async function go() {
    if (!recording) return;
    const mine = ++run;
    const label = LINES.find(([id]) => id === line)[1];
    const button = box.querySelector('[data-line-run]');
    const status = box.querySelector('[data-line-status]');
    const out = box.querySelector('[data-line-out]');
    button.disabled = true;
    out.innerHTML = '';
    status.textContent = `Adding ${label.toLowerCase()} noise and checking both copies…`;
    try {
      const answer = await lineTest(recording, line, context(), model(), language());
      if (mine !== run) return;
      status.textContent = '';
      out.innerHTML = resultView(answer, clearUrl, label);
    } catch (error) {
      if (mine !== run) return;
      status.textContent = error instanceof TypeError ? 'The connection dropped. Check your network and run it again.' : (error.message || 'That did not work. Run it again.');
      if (error.status === 401) failed(error);
    } finally {
      if (mine === run) button.disabled = false;
    }
  }

  box.addEventListener('click', event => {
    const pick = event.target.closest('[data-line]');
    if (pick) {
      line = pick.dataset.line;
      for (const b of box.querySelectorAll('[data-line]')) b.setAttribute('aria-pressed', String(b === pick));
      return;
    }
    if (event.target.closest('[data-line-run]')) void go();
  });

  return {offer, clear};
}
