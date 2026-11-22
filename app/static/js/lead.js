// The top of the site: the promise, how close the locked exam got to it, and the speech-model picker.
// Every number is computed from /v1/bench when the page opens.
import {esc, glyph, int, pct} from './util.js';
import {info} from './info.js';

const LINES = [['standard', 'Standard phone line'], ['noisy', 'Noisy phone line']];
const LADDER = [['B0_asr_plain', 'Speech model alone'], ['B1_asr_keywords_C3', 'With keywords'], ['P_on_B1_C3', 'With Pehchaan']];
const silentCount = row => Math.round(row.silent_error_rate * row.entities);
const whole = rate => `${Math.round(rate * 100)}%`;

export const defaultModel = lab => Object.entries(lab?.model_profiles || {}).find(([, p]) => p.evidence === 'exam')?.[0] || 'gpt-transcribe';

function measuredLine(lab) {
  const at = (line, id) => lab?.exam?.[line]?.systems?.[id]?.silent_error_rate;
  const [after, before, noisyAfter, noisyBefore] = [at('standard', 'P_on_B1_C3'), at('standard', 'B1_asr_keywords_C3'), at('noisy', 'P_on_B1_C3'), at('noisy', 'B1_asr_keywords_C3')];
  if (![after, before, noisyAfter, noisyBefore].every(Number.isFinite)) return '';
  return `<p class="lede">Speech models get names, numbers and money wrong with no warning. Pehchaan works out what the caller meant, checks every fact, and asks when it cannot be sure.</p>
    <p class="note">On the locked real-voice exam, silent errors${info('silent_error')} fell from ${whole(before)} to <strong>${whole(after)}</strong>, and from ${whole(noisyBefore)} to ${whole(noisyAfter)} on a noisy line. One speaker, simulated phone line. <a href="#benchmark">See the results</a></p>`;
}

function row(name, count, total, ours) {
  return `<li class="${ours ? 'is-ours' : ''}"><span>${esc(name)}</span><b class="num">${int(count)}</b><i style="--share:${(count / total).toFixed(3)}" aria-hidden="true"></i></li>`;
}

function hardFigure(hard) {
  if (!hard) return '';
  const rows = hard.steps.map((step, i) => row(step.label, step.unsafe, hard.calls, i === hard.steps.length - 1)).join('');
  return `<figure class="ladder-line"><figcaption>False answers on ${int(hard.calls)} hard calls</figcaption><ol>${rows}</ol></figure>`;
}

function examFigure(key, label, lab) {
  const systems = lab?.exam?.[key]?.systems;
  if (!systems || !LADDER.every(([id]) => systems[id])) return '';
  const facts = systems.P_on_B1_C3.entities;
  const rows = LADDER.map(([id, name]) => row(name, silentCount(systems[id]), facts, id.startsWith('P_'))).join('');
  return `<figure class="ladder-line"><figcaption>${esc(label)}</figcaption><ol>${rows}</ol></figure>`;
}

function ladder(lab) {
  const hard = lab?.hard_calls;
  const exam = hard
    ? examFigure('standard', `Silent errors on the real-voice exam, of ${int(lab?.exam?.standard?.systems?.P_on_B1_C3?.entities || 0)} facts`, lab)
    : LINES.map(([key, label]) => examFigure(key, label, lab)).join('');
  if (!exam && !hard) return '';
  const note = hard
    ? 'A separate AI wrote the hard calls, and we sealed them before the fix. The exam measured the core engine.'
    : `Wrong with no warning, of ${int(lab.exam.standard.systems.P_on_B1_C3.entities)} facts. The keyword step is OpenAI's. The last is ours.`;
  return `<div class="ladder" aria-label="What each stage of Pehchaan changed">${hardFigure(hard)}${exam}<p class="note">${note}</p></div>`;
}

export function leadBlock(lab) {
  return `<div class="lead-copy"><h1 id="hero-title">Every fact in an Indian call: <span class="hold"><span class="mark mark-right">right${glyph('check')}</span>,</span> or <span class="mark mark-ask">it asks${glyph('ask')}</span></h1>
    ${measuredLine(lab)}</div>${ladder(lab)}`;
}

/** One honest sentence about what a speech model brings. */
export function modelBlurb(profile) {
  if (!profile) return '';
  return profile.keywords ? 'Takes call keywords. This setup sat the locked exam.' : 'Takes no keywords, so a second model backs it up. Not in the exam.';
}

export function modelPicker(lab, selected) {
  const names = Object.keys(lab?.model_profiles || {});
  if (!names.length) return '';
  const bad = lab?.models?.datasets?.real_bad_lines?.models?.[selected];
  return `<fieldset class="model-pick"><legend>Speech model${info('asr')}</legend>
      <div class="model-options">${names.map(name => `<label class="${name === selected ? 'is-on' : ''}"><input type="radio" name="pg-model" value="${esc(name)}" ${name === selected ? 'checked' : ''}><span>${esc(name)}</span></label>`).join('')}</div>
    </fieldset>
    <p class="note">${esc(modelBlurb(lab.model_profiles[selected]))}${bad ? ` On bad real lines: ${pct(bad.plain.silent, 0)} silent errors alone, ${pct(bad.C3.silent, 0)} with Pehchaan.` : ''}</p>`;
}
