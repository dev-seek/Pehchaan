// The product's signature visual: a transcript with each fact marked by what happened to it.
import {esc, glyph, badge, statuses, statusOfEntity, int} from './util.js';

/** Is this entity wrong with no warning, according to the scored sample call? Only baselines are judged this way. */
function isSilent(result, entity) {
  const scored = result.scored;
  if (!scored?.silent_errors?.includes(entity.etype)) return false;
  const known = scored.entities?.filter(f => f.type === entity.etype) || [];
  const shown = result.entities.filter(e => e.etype === entity.etype);
  return known.length === 1 && shown.length === 1;     // only blame a fact when it is unambiguous which one it is
}

/** One status key for an entity as shown in a given panel. */
export function factStatus(entity, result, baseline) {
  if (baseline) return isSilent(result, entity) ? 'wrong' : 'heard';
  return statusOfEntity(entity);
}

/** The transcript, with every fact the engine found wrapped in a button that opens its evidence. */
export function passage(result, baseline) {
  const chars = [...(result.text || '')];
  const spans = (result.entities || []).slice().sort((a, b) => a.start - b.start);
  let cursor = 0;
  let html = '';
  for (const entity of spans) {
    const {start, end} = entity;
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < cursor || end <= start || end > chars.length) continue;
    const key = factStatus(entity, result, baseline);
    const literal = chars.slice(start, end).join('');
    const heard = !baseline && entity.status === 'FIXED' && entity.surface && entity.surface !== literal ? ` title="Heard: ${esc(entity.surface)}"` : '';
    html += esc(chars.slice(cursor, start).join(''));
    html += `<button class="fact fact-${key}" type="button" data-evidence="${esc(entity.id)}"${heard} aria-label="${esc(literal)}. ${statuses[key].label}. Show evidence.">${esc(literal)}${glyph(statuses[key].glyph)}</button>`;
    cursor = end;
  }
  html += esc(chars.slice(cursor).join(''));
  return html.trim() ? html : '<span class="empty">No speech was transcribed.</span>';
}

/** Human form of a labelled fact value. */
export function showValue(type, value) {
  const v = String(value ?? '');
  if (type === 'AMOUNT' && /^\d+$/.test(v)) return `₹${Number(v).toLocaleString('en-IN')}`;
  if (type === 'PHONE' && /^\d{10}$/.test(v)) return `${v.slice(0, 5)} ${v.slice(5)}`;
  return v;
}

/** What happened to each known fact of a scored sample call. Null when the call has no labels. */
export function outcomes(result) {
  const list = result?.scored?.entities;
  if (!Array.isArray(list) || !list.length) return null;
  return list.map(f => ({type: f.type, value: f.value, right: !!f.correct, asked: !f.correct && !!f.flagged, silent: !f.correct && !f.flagged}));
}

export function tally(result) {
  const o = outcomes(result);
  if (!o) return null;
  return {n: o.length, right: o.filter(x => x.right).length, asked: o.filter(x => x.asked).length, silent: o.filter(x => x.silent).length};
}

export const outcomeBadge = o => o.right ? badge('right') : o.asked ? badge('ask', {label: 'Asked'}) : badge('wrong');

/** One plain sentence about a scored sample call. */
export function storySentence(base, main) {
  const b = tally(base);
  const m = tally(main);
  if (!b || !m) return '';
  const unit = n => `${int(n)} ${n === 1 ? 'fact' : 'facts'}`;
  const baseLine = b.silent ? `Plain speech-to-text got ${unit(b.silent)} wrong with no warning.` : 'Plain speech-to-text got every known fact right on this call.';
  const parts = [];
  if (m.right) parts.push(`${m.right} of ${m.n} right`);
  if (m.asked) parts.push(`${m.asked} asked as a question`);
  if (m.silent) parts.push(`${m.silent} wrong with no warning`);
  return `${baseLine} Pehchaan: ${parts.join(', ')}.`;
}
