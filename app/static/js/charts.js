// Shared visual pieces for Home and Proof: the fact-dot panel, comparison bars and the evidence label.
import {esc, pct, int, plural} from './util.js';
import {info} from './info.js';
import {factCounts, interval} from './data.js';

export const systemInfo = id => ({
  B0_asr_plain: 'sys_plain', B1_asr_keywords_C3: 'sys_keywords', B1_asr_keywords_C4: 'sys_keywords',
  B2_naive_llm_C3: 'sys_rewrite', B2_naive_llm_C4: 'sys_rewrite',
  P_on_B1_C3: 'sys_pehchaan', P_on_B1_C4: 'sys_pehchaan',
  P_C0: 'sys_pehchaan_plain', P_C2: 'sys_pehchaan_plain', P_C3: 'sys_pehchaan_plain', P_C4: 'sys_pehchaan_plain',
})[id];

export const systemNames = new Map([
  ['B0_asr_plain', ['Plain speech-to-text', 'No context']],
  ['B1_asr_keywords_C3', ['Keyword-assisted speech-to-text', 'Normal context (C3)']],
  ['B1_asr_keywords_C4', ['Keyword-assisted speech-to-text', 'Misleading context (C4)']],
  ['B2_naive_llm_C3', ['Generative rewrite', 'Normal context (C3)']],
  ['B2_naive_llm_C4', ['Generative rewrite', 'Misleading context (C4)']],
  ['P_on_B1_C3', ['Pehchaan', 'Normal context (C3)']],
  ['P_on_B1_C4', ['Pehchaan', 'Misleading context (C4)']],
  ['P_C0', ['Pehchaan on a plain transcript', 'Rules only (C0)']],
  ['P_C2', ['Pehchaan on a plain transcript', 'Built-in lists (C2)']],
  ['P_C3', ['Pehchaan on a plain transcript', 'Normal context (C3)']],
  ['P_C4', ['Pehchaan on a plain transcript', 'Misleading context (C4)']],
]);
export const systemTitle = id => (systemNames.get(id) || [id]).join(' · ');

/** Where the numbers on a page come from, said plainly. Never lets dev numbers pass as real-voice results. */
export function evidenceBanner({report, final}) {
  if (!report) {
    return `<div class="evidence is-empty" role="note"><strong>No measured results yet</strong>
      <p>Numbers appear here after a benchmark run has been recorded. Nothing on this page is a placeholder.</p></div>`;
  }
  const exam = final
    ? `<p><strong>Locked final test.</strong> ${int(report.n_clips)} clips, single-speaker real voice, simulated phone line${info('exam')}. One speaker, so coverage of other accents is limited.</p>`
    : `<p><strong>Real-voice exam: pending.</strong> The 30-clip single-speaker real-voice test (simulated phone line)${info('exam')} has not been run. Until it has, we claim no real-voice accuracy. Charts use the development set unless labelled otherwise.</p>`;
  const dev = final ? '' : `<p><strong>These numbers: ${int(report.n_clips)} clips, synthetic voices${info('synthetic_voice')}, used for tuning${info('dev_set')}, so likely optimistic.</strong>
    Run ${esc(report.ran_at)}.</p>`;
  return `<div class="evidence${final ? ' is-final' : ''}" role="note">${exam}${dev}</div>`;
}

/** 100-ish dots: each is one labelled fact. Right facts are plain dots, asked facts are rings, silent errors are crosses. */
export function dotPanel({id, title, context, row, emphasis = false}) {
  const counts = factCounts(row);
  if (!counts) return `<figure class="dots is-empty"><figcaption><h3>${esc(title)}</h3></figcaption><p class="note">No result for this system in the report.</p></figure>`;
  const {n, right, silent, asked} = counts;
  const dots = [...Array(right).fill('right'), ...Array(asked).fill('asked'), ...Array(silent).fill('silent')]
    .map(kind => `<i class="d d-${kind}"></i>`).join('');
  const ci = interval(row, 'silent_error_rate');
  const label = `${title}${context ? `, ${context}` : ''}: ${n} facts, ${right} right, ${asked} asked, ${silent} silent ${silent === 1 ? 'error' : 'errors'}.`;
  return `<figure class="dots${emphasis ? ' is-main' : ''}">
    <figcaption><h3>${esc(title)}${systemInfo(id) ? info(systemInfo(id)) : ''}</h3>${context ? `<span class="ctx">${esc(context)}</span>` : ''}</figcaption>
    <div class="dot-grid" role="img" aria-label="${esc(label)}">${dots}</div>
    <p class="dot-stat"><strong class="num">${pct(row.silent_error_rate)}</strong> silent errors${info('silent_error')}</p>
    <p class="note num">${plural(silent, 'fact')} wrong with no warning, ${int(asked)} asked, of ${int(n)}${ci ? `. 95% interval ${pct(ci[0])} to ${pct(ci[1])}` : ''}</p>
  </figure>`;
}

export const dotLegend = () => `<ul class="dot-legend" aria-label="Key">
  <li><i class="d d-right"></i>Right</li><li><i class="d d-asked"></i>Wrong, but it asked</li><li><i class="d d-silent"></i>Wrong, no warning</li></ul>`;

/** A horizontal bar with its number. `max` sets the scale so rows can be compared. */
export function barRow({label, value, max, text, tone = 'neutral', sub = ''}) {
  const width = Number.isFinite(value) && max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return `<div class="bar-row bar-${tone}"><span class="bar-label">${label}${sub ? `<small>${esc(sub)}</small>` : ''}</span>
    <span class="bar-track" aria-hidden="true"><span style="width:${width}%"></span></span><b class="num">${text}</b></div>`;
}
