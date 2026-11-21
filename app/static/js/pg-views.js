// Live Playground: pure functions that turn state into markup. No network, no DOM reads.
import {esc, ms, int, icon, glyph, badge, statuses, languageNames, factWord, plural} from './util.js';
import {info} from './info.js';
import {passage, factStatus, tally, scorecard, storySentence} from './transcript.js';
import {gateRules, ruleName, timingDetails} from './evidence.js';
import {systemTitle} from './charts.js';

export const levels = {
  C0: {label: 'Rules only', blurb: 'Uses number rules and sound rules, with no call hints and no built-in lists.'},
  C2: {label: 'Built-in lists', blurb: 'Adds the built-in brand and locality lists.'},
  C3: {label: 'This call’s context', blurb: 'Uses the contacts, caller ID, messages and saved places for this call. This is the product setting.'},
  C4: {label: 'Misleading context', blurb: 'A stress test: the hints are deliberately wrong. A system that trusts them blindly will copy the decoys.'},
};

const NUMBERS = ['PHONE', 'PIN', 'AMOUNT'];
const FACT_ROWS = [
  ['Caller', ['PERSON', 'ORG']], ['Place', ['PLACE']], ['Amount', ['AMOUNT']], ['PIN code', ['PIN']], ['Callback number', ['PHONE']],
];

// ---- sample gallery ----
export function sampleChip(preset, {selected, disabled}) {
  const voice = preset.kind === 'real' ? 'Real voice' : 'Synthetic voice';
  return `<li><button class="sample-chip" type="button" data-preset="${esc(preset.id)}" aria-pressed="${selected}" ${disabled ? 'disabled' : ''}>${esc(preset.label)}<small>${voice}${preset.language ? ` · ${esc(preset.language)}` : ''}</small></button></li>`;
}

export function sampleNote(preset) {
  if (!preset) return '';
  return `${esc(preset.description)}${preset.watch_for ? ` <strong>Watch for:</strong> ${esc(preset.watch_for)}` : ''}`;
}

export function emptySamples() {
  return `<li class="state-box sample-empty"><strong>No sample calls available</strong>The packaged samples could not be loaded. You can still try your own call below.</li>`;
}

// ---- context ----
export function contextFacts(context) {
  const {caller, contacts, places, sms, user, domain} = context || {};
  const items = [
    ['Contacts', contacts?.map(c => [c.name, c.number].filter(Boolean).join(' · '))],
    ['Caller ID', [[caller?.cnap_name, caller?.number].filter(Boolean).join(' · ')]],
    ['Messages', sms?.map(s => [s.sender, s.body].filter(Boolean).join(' · '))],
    ['Saved places', places],
    ['City', [user?.city]],
    ['Call type', [domain]],
  ];
  return `<dl class="context-facts">${items.map(([label, values]) => {
    const lines = (values || []).filter(Boolean);
    return `<div><dt>${label}</dt><dd>${lines.length ? lines.map(esc).join('<br>') : '<span class="muted">None supplied</span>'}</dd></div>`;
  }).join('')}</dl>`;
}

// ---- the story on top of a result ----
export function storyBanner({base, main, input, level, keywords}) {
  if (!main) return '';
  const sentence = storySentence(base, main);
  const b = tally(base);
  const m = tally(main);
  const refused = main.refused || [];
  const found = main.entities || [];
  const counts = {verified: 0, fixed: 0, ask: 0, heard: 0};
  for (const e of found) counts[factStatus(e, main, false)]++;
  const chips = ['verified', 'fixed', 'ask', 'heard'].filter(k => counts[k])
    .map(k => `<li>${badge(k)} <b class="num">${counts[k]}</b></li>`).join('');
  const headline = b && m ? (b.silent > m.silent ? 'Fewer wrong facts slipped through with Pehchaan.' : b.silent === 0 && m.silent === 0 ? (main.questions?.length ? 'No silent errors. Pehchaan asks about what it could not prove.' : 'Both got every known fact right.') : 'Here is how the two compare.') : 'What Pehchaan did with each fact.';
  return `<div class="story card">
    <h2 id="result-title" tabindex="-1">${esc(headline)}</h2>
    ${sentence ? `<p class="story-line">${esc(sentence)}</p>` : '<p class="story-line">This call has no stored answer key, so facts are shown by what Pehchaan did with them rather than scored.</p>'}
    <ul class="story-chips" aria-label="What Pehchaan did with each fact">${chips || '<li class="muted">No facts found in this call.</li>'}</ul>
    ${refused.length ? `<p class="note">The gate blocked ${plural(refused.length, 'proposed change')} here (${[...new Set(refused.map(r => ruleName(r.rule)))].join(', ')}).</p>` : ''}
    ${keywords ? '<p class="note">The Pehchaan side starts from a keyword-assisted transcript, so part of any gain here is OpenAI’s keyword feature.</p>' : ''}
    <p class="note">${esc(levels[level]?.label || level)} · ${input?.preset ? esc(input.preset.label) : input?.text ? 'Typed transcript' : esc(input?.label || '')}</p>
  </div>`;
}

// ---- fact summary ----
function factSummary(result, baseline) {
  return `<dl class="facts">${FACT_ROWS.map(([label, types]) => {
    const distinct = new Map();
    for (const e of result.entities.filter(x => types.includes(x.etype))) {
      const key = `${e.etype}:${e.value || e.surface}`;
      if (!distinct.has(key) || e.status === 'FLAGGED') distinct.set(key, e);
    }
    const list = [...distinct.values()];
    if (!list.length) {
      const missed = baseline && result.scored?.silent_errors?.some(t => types.includes(t));
      return `<div><dt>${label}</dt><dd><span class="muted">Not detected</span> ${missed ? badge('wrong') : ''}</dd></div>`;
    }
    return `<div><dt>${label}</dt><dd>${list.map(e => {
      const key = factStatus(e, result, baseline);
      return `<span class="fact-line"><button class="value-button" type="button" data-evidence="${esc(e.id)}">${esc(e.display || e.surface || e.value || 'Unclear')}</button> ${badge(key)}</span>`;
    }).join('')}${list.length > 1 ? '<span class="note">Multiple values heard</span>' : ''}</dd></div>`;
  }).join('')}</dl>`;
}

function callbackAction(result, baseline) {
  const numbers = result.entities.filter(e => e.etype === 'PHONE');
  if (!numbers.length) return '<p class="note">Callback unavailable. No number heard.</p>';
  if (new Set(numbers.map(n => n.value)).size > 1) return '<p class="note">Callback blocked. Conflicting numbers.</p>';
  if (numbers.some(n => n.status === 'FLAGGED') || (baseline && result.scored?.silent_errors?.includes('PHONE'))) {
    return '<p class="note">Callback blocked. The number needs review.</p>';
  }
  if (!/^(?:\+91)?[6-9]\d{9}$/.test(numbers[0].value)) return '<p class="note">Callback unavailable. The number is incomplete.</p>';
  return `<button class="button" type="button" data-callback="${esc(numbers[0].display || numbers[0].value)}">${icon('phone')} Preview callback</button>`;
}

function actionCard(result, baseline) {
  if (baseline) return `<div class="callback">${callbackAction(result, true)}</div>`;
  const question = result.questions?.[0]?.question;
  return `<div class="action-card ${question ? 'is-hold' : ''}"><h4>${question ? 'Next action: ask first' : 'Next action: no open question'}</h4>
    ${question ? `<p>${esc(question)}</p>` : ''}<div class="callback">${callbackAction(result, false)}</div></div>`;
}

function refusedList(result) {
  const refused = result.refused || [];
  if (!refused.length) return '';
  return `<section class="refused" aria-label="Changes the gate refused">
    <h4>Changes the Admission Gate refused${info('gate')}</h4>
    <ul>${refused.map(r => `<li><span class="rule">${esc(ruleName(r.rule))}${gateRules[r.rule] ? info(gateRules[r.rule]) : ''}</span>
      Would have changed ${esc(factWord(r.etype).toLowerCase())} “${esc(r.surface)}”${r.proposed && r.proposed !== r.surface ? ` to “${esc(r.proposed)}”` : ' to a confirmed status'}. Refused.</li>`).join('')}</ul></section>`;
}

// ---- verdict from verified learning ----
export function checkList(checks) {
  return `<ul class="checks">${(checks || []).map(c => {
    const key = c.passed === true ? 'verified' : c.passed === false ? 'wrong' : 'heard';
    const word = c.passed === true ? 'Passed' : c.passed === false ? 'Failed' : 'Not run';
    return `<li class="check check-${key}"><span class="badge badge-${key}">${glyph(statuses[key].glyph)}${word}</span>
      <span><b>${esc(String(c.name).replaceAll('_', ' '))}</b>${info(`learn_${c.name}`)}<small>${esc(c.detail || '')}</small></span></li>`;
  }).join('')}</ul>`;
}

export function verdictBlock(v) {
  if (!v) return '';
  if (v.adopted) {
    return `<div class="verdict is-adopted" role="status">
      <h4>${glyph('check')} Tested, then adopted</h4>
      <p>Tested on <b class="num">${int(v.clips_replayed)}</b> labelled calls in <b class="num">${ms(v.ms)}</b>:
        <b class="num">${int(v.facts_harmed)}</b> ${v.facts_harmed === 1 ? 'fact' : 'facts'} harmed, <b class="num">${int(v.new_damage)}</b> damaged edits,
        <b class="num">${int(v.facts_helped)}</b> helped. Adopted for this session: “${esc(v.heard)}” is corrected to “${esc(v.canonical)}”, unless the caller really said “${esc(v.heard)}”.</p>
      ${checkList(v.checks)}</div>`;
  }
  const failed = (v.checks || []).find(c => c.passed === false);
  return `<div class="verdict is-rejected" role="status">
    <h4>${glyph('cross')} Not adopted. Nothing was saved.</h4>
    <p>${failed ? `It failed the check “${esc(String(failed.name).replaceAll('_', ' '))}”: ${esc(failed.detail || '')}.` : 'It did not pass every check.'}
      This is a normal outcome. A confirmation is only a candidate until it is shown to be safe.</p>
    ${checkList(v.checks)}
    ${v.clips_replayed ? `<p class="note">Replayed on ${int(v.clips_replayed)} labelled calls in ${ms(v.ms)}.</p>` : ''}</div>`;
}

// ---- questions ----
function questionsBlock(id, result, ui) {
  if (!result.questions?.length) return '';
  return `<section class="questions" aria-label="Questions Pehchaan asks">
    <h4>Pehchaan asks${info('status_ask')}</h4>
    ${result.questions.map(q => {
      const entity = result.entities.find(e => e.id === q.entity_id);
      if (!entity) return '';
      const learnable = !NUMBERS.includes(entity.etype) && !ui.modelView;
      const key = `${id}:${q.entity_id}`;
      const verdict = ui.verdicts.get(key);
      const choices = (q.choices || []).filter(Boolean);
      const busy = ui.confirming === key;
      return `<div class="question">
        <p class="q-text">${badge('ask')} <span>${esc(q.question)}</span></p>
        ${learnable ? `<form class="confirm" data-confirm="${esc(q.entity_id)}">
          ${verdict ? verdictBlock(verdict) : ''}
          ${verdict?.adopted ? '' : `
            <p class="note">${verdict ? 'You can try a different answer.' : 'Pick the right answer. Pehchaan will test it before it learns anything.'}</p>
            ${choices.length ? `<div class="choices">${choices.map(c => `<button class="button" type="button" data-choice="${esc(c)}" ${busy ? 'disabled' : ''}>${esc(c)}</button>`).join('')}</div>` : ''}
            <label>Or type the correct name or place<input name="canonical" type="text" autocomplete="off" required ${busy ? 'disabled' : ''}></label>
            <button type="submit" class="button" ${busy ? 'disabled' : ''}>${busy ? 'Testing…' : 'Test and save this answer'}</button>`}
          <p class="confirm-status" role="status">${busy ? 'Testing this correction on labelled calls…' : ''}</p>
        </form>`
        : `${choices.length ? `<ul class="choice-list">${choices.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : '<p>Repeat that detail.</p>'}
          <p class="note">${ui.modelView && !NUMBERS.includes(entity.etype) ? `Switch back to ${esc(ui.defaultModel)} to teach Pehchaan this answer.` : 'Review only. Phone numbers, PIN codes and amounts are never changed or learned automatically.'}</p>`}
      </div>`;
    }).join('')}</section>`;
}

// A learning verdict stays on screen after its question is gone (for example after a replay).
function keptVerdicts(id, result, ui) {
  const open = new Set((result.questions || []).map(q => `${id}:${q.entity_id}`));
  const kept = [...ui.verdicts].filter(([key, v]) => key.startsWith(`${id}:`) && !open.has(key) && v.adopted);
  return kept.length ? `<section class="kept-verdicts" aria-label="Learning test result"><h4>Learning test${info('verified_learning')}</h4>${kept.map(([, v]) => verdictBlock(v)).join('')}</section>` : '';
}

// ---- one result panel ----
export function resultPanel({id, result, error, baseline, level, done, ui}) {
  const heading = baseline ? 'Base model' : 'With Pehchaan';
  const sub = baseline ? `Plain speech-to-text, ${ui.model}` : `${levels[level]?.label}, ${ui.model}`;
  const subInfo = baseline ? info('sys_plain') : info(level, `${level}`);
  const head = `<div class="panel-head"><h3>${heading}</h3><p class="panel-sub">${esc(sub || '')}${subInfo}</p></div>`;
  if (!result) {
    const waiting = ui.input ? (done ? 'This approach returned no result.' : 'Waiting for this approach…') : (baseline ? 'What the speech model heard will appear here.' : 'Which facts were fixed, verified or asked about will appear here.');
    return `${head}<p class="placeholder${error ? ' is-error' : ''}">${esc(error ? `This approach failed. ${error}` : waiting)}</p>`;
  }
  const replaying = ui.replaying === id;
  const isReplay = ui.replays.get(id) === result;
  const hits = Array.isArray(result.memory_hits) ? result.memory_hits.length : (result.memory_hits || 0);
  return `${head}<div class="panel-body">
    <section><h4>Transcript</h4><p class="transcript">${passage(result, baseline)}</p></section>
    <section><h4>Call summary</h4>${factSummary(result, baseline)}${actionCard(result, baseline)}</section>
    ${baseline ? '' : refusedList(result)}
    ${baseline ? '' : questionsBlock(id, result, ui)}
    ${baseline ? '' : keptVerdicts(id, result, ui)}
    ${!baseline && ui.canReplay && !ui.modelView ? `<div class="replay">
      <button class="button" type="button" data-replay ${replaying || ui.working ? 'disabled' : ''}>${icon('replay')} ${replaying ? 'Replaying…' : 'Replay the same call'}</button>
      <p class="note">${isReplay ? `Replayed in ${ms(result.replay_ms ?? result.timings_ms?.total)}, ${hits} memory ${hits === 1 ? 'hit' : 'hits'}, ${result.llm_calls ?? 0} LLM calls. The question is gone because Pehchaan now knows the answer.` : 'Runs the same speech-to-text input again with what was learned, and no LLM judge.'}</p>
    </div>` : ''}
    <div class="run-meta">${!baseline ? `<span>Pehchaan processing <b class="num">${ms(result.timings_ms?.total)}</b>${info('latency')}</span><span>LLM calls <b class="num">${result.llm_calls ?? '—'}</b>${info('llm_calls')}</span>` : ''}</div>
    ${timingDetails(result)}
  </div>`;
}

export function scorecardBlock(base, main, level) {
  const card = scorecard(base, main, `With Pehchaan (${level})`);
  return card ? `<section class="scorecard-wrap" aria-label="Known facts">${card}</section>` : '';
}

// ---- learning ledger ----
export function ledger(events) {
  if (!events) return `<p class="note">Loading the ledger…</p>`;
  if (!events.length) return `<div class="state-box"><strong>Nothing learned yet</strong>When you confirm an answer to a question, the decision is recorded here, with the checks it passed or failed.</div>`;
  return `<ol class="ledger">${events.map(e => {
    const state = e.decision === 'adopted' ? (e.active ? 'active' : 'undone') : e.decision === 'rolled_back' ? 'rollback' : 'rejected';
    const label = {active: 'Adopted', undone: 'Adopted, then undone', rollback: 'Undone', rejected: 'Rejected'}[state];
    const key = {active: 'verified', undone: 'heard', rollback: 'heard', rejected: 'wrong'}[state];
    return `<li class="ledger-item ledger-${state}">
      <div class="ledger-top"><span class="badge badge-${key}">${glyph(statuses[key].glyph)}${label}</span>
        <span><b>“${esc(e.heard)}” → “${esc(e.canonical)}”</b> <span class="note">${esc(factWord(e.etype).toLowerCase())} · ${esc(e.at)}</span></span>
        ${e.active ? `<button class="button" type="button" data-undo="${esc(e.event_id)}">${icon('undo')} Undo</button>` : ''}</div>
      <details><summary>${e.decision === 'rolled_back' ? 'Details' : `Checks and test results${e.clips_replayed ? `: ${int(e.clips_replayed)} calls replayed, ${int(e.facts_harmed)} facts harmed` : ''}`}</summary>
        ${checkList(e.checks)}</details>
    </li>`;
  }).join('')}</ol>`;
}

export {systemTitle, languageNames};
