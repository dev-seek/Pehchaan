// Workbench views: pure functions that turn state into markup. No network, no DOM reads.
import {esc, ms, int, icon, glyph, badge, statuses, factWord, plural} from './util.js';
import {info} from './info.js';
import {passage, tally, outcomes, outcomeBadge, showValue} from './transcript.js';
import {ruleName} from './evidence.js';

export const levels = {
  C0: {label: 'No hints', blurb: 'Only number and sound rules. It knows nothing about this caller.'},
  C2: {label: 'Built-in lists', blurb: 'Adds well-known brands and local areas.'},
  C3: {label: 'This call’s hints', blurb: 'Adds the contacts, caller ID, messages and saved places for this call.'},
  C4: {label: 'Misleading hints', blurb: 'A stress test. The true names are removed and sound-alike decoys are added.'},
};

// ---- choosing a call ----
const chip = (p, selected, disabled) => `<li><button class="sample-chip" type="button" data-preset="${esc(p.id)}" aria-pressed="${p.id === selected}" ${disabled ? 'disabled' : ''}>${esc(p.label)}</button></li>`;

export function sampleChips(presets, selected, disabled) {
  if (!presets.length) return '<p class="note">Sample calls could not be loaded. Use the Your voice tab.</p>';
  const group = (title, kind) => {
    const list = presets.filter(p => (p.kind === 'real') === kind);
    return list.length ? `<div class="sample-group"><h3>${title}</h3><ul class="sample-strip">${list.map(p => chip(p, selected, disabled)).join('')}</ul></div>` : '';
  };
  return group(`Real voice${info('real_voice')}`, true) + group('Synthetic voice', false);
}

export const sampleNote = preset => preset?.watch_for ? `<strong>Watch for:</strong> ${esc(preset.watch_for)}` : esc(preset?.description || '');

export function contextFacts(context) {
  const {caller, contacts, places, sms, user, domain} = context || {};
  const items = [
    ['Contacts', contacts?.map(c => c.name)],
    ['Caller ID', [caller?.cnap_name || caller?.number]],
    ['Messages', sms?.map(s => s.body)],
    ['Saved places', places],
    ['City', [user?.city]],
    ['Call type', [domain]],
  ].map(([label, values]) => [label, (values || []).filter(Boolean)]).filter(([, values]) => values.length);
  if (!items.length) return '<p class="note">Nothing about this caller.</p>';
  return `<dl class="context-facts">${items.map(([label, values]) => `<div><dt>${label}</dt><dd>${values.map(esc).join(', ')}</dd></div>`).join('')}</dl>`;
}

// ---- compare ----
export function storyTitle(base, keyword, main) {
  const b = tally(base);
  const k = tally(keyword);
  const m = tally(main);
  if (!m) return 'What Pehchaan did with each fact';
  if (k && m.silent < k.silent) return `Pehchaan caught ${plural(k.silent - m.silent, 'error')} keywords alone missed`;
  if (k && m.silent > k.silent) return 'On this call Pehchaan did worse than keywords alone';
  if (b && b.silent > m.silent) return k ? 'Keywords fixed this one. Pehchaan kept it right' : `Pehchaan removed ${plural(b.silent - m.silent, 'silent error')}`;
  if (!m.silent && m.asked) return 'Nothing wrong slipped through. It asks about the rest';
  if (!m.silent) return 'Every fact right. Pehchaan changed nothing it should not';
  return 'Here is how the two compare';
}

export function transcriptCard(title, sub, key, result, baseline, ours = false) {
  return `<article class="call-side${ours ? ' is-main' : ''}" data-system="${esc(key)}" data-baseline="${baseline ? 1 : 0}">
    <h3>${esc(title)}${sub ? ` <small>${esc(sub)}</small>` : ''}</h3>
    <p class="transcript">${result ? passage(result, baseline) : '<span class="empty">Waiting…</span>'}</p></article>`;
}

function callback(result) {
  const numbers = result.entities.filter(e => e.etype === 'PHONE');
  if (!numbers.length || new Set(numbers.map(n => n.value)).size > 1 || numbers.some(n => n.status === 'FLAGGED')) return '';
  if (!/^(?:\+91)?[6-9]\d{9}$/.test(numbers[0].value)) return '';
  return `<button class="button" type="button" data-callback="${esc(numbers[0].display || numbers[0].value)}">${icon('phone')} Preview callback</button>`;
}

export function nextAction(result) {
  if (!result) return '';
  const question = result.questions?.[0]?.question;
  const refused = result.refused || [];
  return `<div class="next ${question ? 'is-hold' : ''}">
      <div><h3>${question ? 'Your agent should ask' : 'No open question'}</h3>${question ? `<p>${esc(question)}</p>` : ''}</div>${callback(result)}
    </div>
    <p class="note run-note">${refused.length ? `Blocked ${plural(refused.length, 'risky change')} (${esc([...new Set(refused.map(r => ruleName(r.rule)))].join(', '))})${info('gate')}. ` : ''}Pehchaan added ${ms(result.timings_ms?.total)}${info('latency')}. LLM calls: ${result.llm_calls ?? 0}${info('llm_calls')}.</p>`;
}

// ---- a fact table across any set of systems ----
export function columnPicker(name, columns, active) {
  return `<div class="col-pick" role="group" aria-label="Show a transcript">${columns.map(c => `<button type="button" data-col="${name}:${esc(c.id)}" aria-pressed="${c.id === active}" class="${c.ours ? 'is-ours' : ''}">${esc(c.title)}</button>`).join('')}</div>`;
}

export function factMatrix(columns, caption) {
  const rows = columns.map(c => outcomes(c.result));
  const facts = rows.find(Boolean);
  if (!facts || rows.some(r => !r || r.length !== facts.length)) return '<p class="note">This call has no known answer to score against.</p>';
  const head = columns.map(c => `<th scope="col" class="${c.ours ? 'is-ours' : ''}">${esc(c.title)}${c.info ? info(c.info) : ''}</th>`).join('');
  const body = facts.map((fact, i) => `<tr><th scope="row">${esc(factWord(fact.type))}<small>${esc(showValue(fact.type, fact.value))}</small></th>
    ${columns.map((c, j) => `<td data-label="${esc(c.title)}" class="${c.ours ? 'is-ours' : ''}">${outcomeBadge(rows[j][i])}</td>`).join('')}</tr>`).join('');
  const totals = columns.map((c, j) => `<td data-label="${esc(c.title)}" class="${c.ours ? 'is-ours' : ''}"><b class="num">${int(rows[j].filter(o => o.silent).length)}</b></td>`).join('');
  return `<div class="matrix-wrap"><table class="matrix"><caption class="sr-only">${esc(caption)}</caption>
    <thead><tr><th scope="col">Fact</th>${head}</tr></thead><tbody>${body}</tbody>
    <tfoot><tr><th scope="row">Silent errors${info('silent_error')}</th>${totals}</tr></tfoot></table></div>`;
}

// ---- verified learning ----
export function checkList(checks) {
  return `<ol class="checks">${(checks || []).map((c, i) => {
    const key = c.passed === true ? 'verified' : c.passed === false ? 'wrong' : 'heard';
    const word = c.passed === true ? 'Passed' : c.passed === false ? 'Failed' : 'Not run';
    return `<li class="check" style="--i:${i}"><span class="badge badge-${key}">${glyph(statuses[key].glyph)}${word}</span>
      <span><b>${esc(String(c.name).replaceAll('_', ' '))}</b>${info(`learn_${c.name}`)}<small>${esc(c.detail || '')}</small></span></li>`;
  }).join('')}</ol>`;
}

export function ledger(events) {
  if (!events?.length) return '<p class="note">Nothing learned yet.</p>';
  return `<ol class="ledger">${events.map(e => {
    const state = e.decision === 'adopted' ? (e.active ? 'active' : 'undone') : e.decision === 'rolled_back' ? 'rollback' : 'rejected';
    const label = {active: 'Adopted', undone: 'Undone later', rollback: 'Undo', rejected: 'Rejected'}[state];
    const key = {active: 'verified', undone: 'heard', rollback: 'heard', rejected: 'wrong'}[state];
    return `<li class="ledger-item ledger-${state}"><span class="badge badge-${key}">${glyph(statuses[key].glyph)}${label}</span>
      <span>“${esc(e.heard)}” to “${esc(e.canonical)}”</span><span class="note">${esc(factWord(e.etype))}</span></li>`;
  }).join('')}</ol>`;
}
