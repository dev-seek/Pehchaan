// The top of the site: the claim, the honest summary, the three-step ladder, and the speech-model picker.
// Every number is computed from /v1/bench when the page opens.
import {esc, glyph, int, ms, pct} from './util.js';
import {info} from './info.js';

const LINES = [['standard', 'test_real_phone', 'Standard phone line'], ['noisy', 'test_real_noisy', 'Noisy phone line']];
const LADDER = [['B0_asr_plain', 'Plain speech-to-text'], ['B1_asr_keywords_C3', 'OpenAI keywords'], ['P_on_B1_C3', 'Pehchaan']];
const silentCount = row => Math.round(row.silent_error_rate * row.entities);
const percent = share => Math.round(share * 100);

export const defaultModel = lab => Object.entries(lab?.model_profiles || {}).find(([, p]) => p.evidence === 'exam')?.[0] || 'gpt-transcribe';

function range(values) {
  const low = Math.min(...values);
  const high = Math.max(...values);
  return low === high ? `${low}%` : `${low}–${high}%`;
}

function summary(lab) {
  const lines = lab?.exam_paired?.lines;
  if (!lines) return '';
  const normal = LINES.map(([, id]) => lines[id].C3);
  const misleading = LINES.map(([, id]) => lines[id].C4);
  const halved = normal.every(x => x.critical_silent_after * 2 <= x.critical_silent_before);
  const critical = normal.map(x => `${int(x.critical_silent_before)} to ${int(x.critical_silent_after)}`).join(' and ');
  const worse = [...normal, ...misleading].reduce((n, x) => n + x.clips_worse, 0);
  return `<p class="lede">On a locked 30-clip real-voice exam, Pehchaan left <strong>${range(normal.map(x => percent(x.silent_drop_share)))} fewer silent errors</strong>${info('silent_error')} than OpenAI keywords alone.
    Silent money, phone and PIN errors ${halved ? 'were cut by more than half' : 'fell'} (${critical} of ${int(normal[0].critical_facts)}).${worse === 0 ? ' No clip ended up with more silent errors.' : ''}</p>
    <p class="note">One speaker, simulated phone line, normal call hints. With deliberately misleading hints the drop is ${range(misleading.map(x => percent(x.silent_drop_share)))}. The clip-by-clip count was chosen after the results were seen. <a href="#benchmark">See the full results</a></p>`;
}

function ladder(lab) {
  const figures = LINES.map(([key,, label]) => {
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
    <p class="note">Facts wrong with no warning, out of ${int(facts)}. The first drop is OpenAI's keyword feature. Only the last step is Pehchaan.</p></div>`;
}

export function leadBlock(lab) {
  const mark = `<span class="mark mark-ask">it asks${glyph('ask')}</span>`;
  return `<div class="lead-copy"><h1 id="hero-title">Fewer wrong facts slip through. When unsure, ${mark}.</h1>
    ${summary(lab)}</div>${ladder(lab)}`;
}

// ---- the model picker: what each model can do, from what was probed and measured ----
function modelFacts(model, lab) {
  const dev = lab?.models?.datasets?.dev?.models;
  const bad = lab?.models?.datasets?.real_bad_lines?.models;
  return {profile: lab?.model_profiles?.[model], dev: dev?.[model], bad: bad?.[model], devAll: dev, badAll: bad};
}

function strengths(model, {profile, dev, bad, devAll, badAll}) {
  const out = [];
  if (profile?.keywords) out.push('The only model here that accepts call keywords. It is the setup that sat the locked exam.');
  else out.push('Takes no call keywords. Its second opinion comes from gpt-transcribe, so a weak model is partly helped by a stronger one.');
  if (devAll && Object.values(devAll).every(m => dev.C3.silent <= m.C3.silent)) out.push('Fewest silent errors with Pehchaan on the development calls.');
  if (badAll && Object.values(badAll).every(m => bad.C3.silent <= m.C3.silent)) out.push('Fewest silent errors with Pehchaan on bad real phone lines.');
  if (devAll && Object.values(devAll).every(m => dev.asr_ms_p50 <= m.asr_ms_p50)) out.push('Fastest median transcription on the development calls.');
  if (badAll && Object.values(badAll).every(m => bad.plain.silent >= m.plain.silent)) out.push('Weakest on its own on bad lines, so expect more wrong facts and more questions.');
  return out;
}

export function modelPicker(lab, selected) {
  const names = Object.keys(lab?.model_profiles || {});
  if (!names.length) return '';
  const facts = modelFacts(selected, lab);
  const row = (label, data) => data ? `<div><dt>${esc(label)}</dt><dd><b class="num">${pct(data.plain.silent)}</b> alone → <b class="num">${pct(data.C3.silent)}</b> with Pehchaan</dd></div>` : '';
  return `<fieldset class="model-pick"><legend>Speech model${info('asr')}</legend>
      <div class="model-options">${names.map(name => `<label class="${name === selected ? 'is-on' : ''}"><input type="radio" name="pg-model" value="${esc(name)}" ${name === selected ? 'checked' : ''}><span>${esc(name)}</span></label>`).join('')}</div>
    </fieldset>
    <div class="model-why">
      <ul>${strengths(selected, facts).map(line => `<li>${esc(line)}</li>`).join('')}</ul>
      <dl>${row('Silent errors, development calls', facts.dev)}${row('Silent errors, bad real lines', facts.bad)}
        ${facts.dev ? `<div><dt>Median transcription time</dt><dd><b class="num">${ms(facts.dev.asr_ms_p50)}</b></dd></div>` : ''}
        <div><dt>Evidence for this setup</dt><dd>${facts.profile?.evidence === 'exam' ? 'Locked real-voice exam' : 'Development and sample calls only, not the exam'}</dd></div></dl>
      <p class="note">Silent-error figures were measured with no keywords on any model, so the four compare fairly.</p>
    </div>`;
}
