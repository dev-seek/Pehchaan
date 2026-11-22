// The Meaning tab: saved answers that show what the caller meant, and what code then allowed.
import {esc} from './util.js';
import {getJSON} from './api.js';
import {showValue} from './transcript.js';

const FACT_NAMES = {PERSON: 'Person', ORG: 'Company', PLACE: 'Place', PHONE: 'Phone', PIN: 'PIN', AMOUNT: 'Money'};
const STATUS_WORDS = {FIXED: 'corrected', VERIFIED: 'verified', HEARD: 'as heard', FLAGGED: 'asks the caller'};
const ASIDE = {
  corrected_by_caller: 'Caller took this back',
  other_number: 'A different kind of number',
  everyday_word: 'An everyday word',
  command_in_speech: 'A command, not a fact',
};

const factList = facts => (facts.length
  ? `<ul class="meaning-facts">${facts.map(f => `<li><span>${esc(FACT_NAMES[f.type])}</span><b>${esc(showValue(f.type, f.value))}</b><small>${esc(STATUS_WORDS[f.status])}</small></li>`).join('')}</ul>`
  : '<p class="note">No facts claimed.</p>');

const asideList = items => (items.length
  ? `<ul class="meaning-aside">${items.map(u => `<li><s>${esc(u.heard)}</s><span>${esc(ASIDE[u.meaning])}</span></li>`).join('')}</ul>`
  : '');

function tag(row) {
  const by = row.fixed_by === 'code' ? 'Fixed by exact arithmetic in code' : 'Fixed by the meaning layer';
  return row.right_runs === row.runs ? `${by}. Right in ${row.runs} of ${row.runs} runs.`
    : `${row.right_runs ? 'Not reliable yet' : 'Still wrong'}: right in ${row.right_runs} of ${row.runs} runs. This run shows the miss.`;
}

function evidence(gate) {
  const row = gate?.table?.fresh_attacks;
  if (!row) return '';
  return `<p class="meaning-proof"><b>${row.baseline.unsafe} → ${row.with_meaning.unsafe}</b>
    <span>confidently wrong answers on ${row.baseline.calls} new test sentences, written before this layer was built. Recorded calls got no worse. ${row.with_meaning.unsafe} still get through, and the locked exam did not include this layer.</span></p>`;
}

export function mountMeaning(root) {
  let data = null;
  let chosen = null;
  let failed = false;

  function render() {
    if (failed) { root.innerHTML = '<p class="note">The saved examples did not load. Refresh the page to try again.</p>'; return; }
    if (!data) { root.innerHTML = '<p class="note">Loading examples…</p>'; return; }
    const row = data.examples.find(x => x.id === chosen) || data.examples[0];
    root.innerHTML = `<div class="seg" role="group" aria-label="Example sentences">
        ${data.examples.map(x => `<span class="seg-item"><button type="button" data-meaning="${esc(x.id)}" aria-pressed="${x.id === row.id}">${esc(x.label)}</button></span>`).join('')}
      </div>
      <blockquote class="meaning-said">${esc(row.said)}</blockquote>
      <p class="meaning-tag${row.right_runs < row.runs ? ' is-miss' : ''}">${esc(tag(row))}</p>
      <div class="call-pair">
        <section class="call-side"><h3>Exam engine</h3>${factList(row.before.facts)}</section>
        <section class="call-side is-main"><h3>Now</h3>${factList(row.after.facts)}${asideList(row.after.set_aside)}${row.after.question ? `<p class="live-ask"><span>${esc(row.after.question)}</span></p>` : ''}</section>
      </div>
      <p class="note">An LLM says what the words are. It never sees the caller's contacts or records, and code works out every number. Free pasted text skips the LLM, so connect a passcode to try this live.</p>
      ${evidence(data.gate)}`;
  }

  root.addEventListener('click', event => {
    const button = event.target.closest('[data-meaning]');
    if (!button) return;
    chosen = button.dataset.meaning;
    render();
    root.querySelector(`[data-meaning="${CSS.escape(chosen)}"]`)?.focus();
  });

  return {
    async activate() {
      if (data) { render(); return; }
      render();
      try { data = await getJSON('/api/demo/meaning'); failed = !data?.examples?.length; } catch { failed = true; }
      render();
    },
  };
}
