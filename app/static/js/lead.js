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
  return `<p class="lede">Not there yet. On our locked exam, <strong>${whole(after)}</strong> of facts still slip through silently${info('silent_error')}, down from ${whole(before)} with keywords alone.</p>
    <p class="note">Noisy line: ${whole(noisyBefore)} to ${whole(noisyAfter)}. One speaker, simulated phone line. <a href="#benchmark">See the results</a></p>`;
}

function ladder(lab) {
  const figures = LINES.map(([key, label]) => {
    const systems = lab?.exam?.[key]?.systems;
    if (!systems || !LADDER.every(([id]) => systems[id])) return '';
    const facts = systems.P_on_B1_C3.entities;
    return `<figure class="ladder-line"><figcaption>${esc(label)}</figcaption><ol>${LADDER.map(([id, name]) => {
      const count = silentCount(systems[id]);
      return `<li class="${id.startsWith('P_') ? 'is-ours' : ''}"><span>${esc(name)}</span><b class="num">${int(count)}</b><i style="--share:${(count / facts).toFixed(3)}" aria-hidden="true"></i></li>`;
    }).join('')}</ol></figure>`;
  }).join('');
  if (!figures) return '';
  const facts = lab.exam.standard.systems.P_on_B1_C3.entities;
  return `<div class="ladder" aria-label="Facts wrong with no warning at each step">${figures}
    <p class="note">Wrong with no warning, of ${int(facts)} facts. The keyword step is OpenAI's. The last is ours.</p></div>`;
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
