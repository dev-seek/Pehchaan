// Small shared helpers: escaping, number formats, icons, status vocabulary.
import {info} from './info.js';

export const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

export const isRate = v => Number.isFinite(v) && v >= 0 && v <= 1;
export const pct = (v, digits = 1) => isRate(v) ? `${(v * 100).toFixed(digits)}%` : '—';
export const int = v => Number.isFinite(v) ? Math.round(v).toLocaleString('en-IN') : '—';
export const dec = (v, d = 2) => Number.isFinite(v) && v >= 0 ? v.toFixed(d) : '—';
export const ms = v => Number.isFinite(v) && v >= 0 ? `${Number(v.toFixed(v < 10 ? 1 : 0)).toLocaleString('en-IN')} ms` : '—';
export const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

const paths = {
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-3 0h6"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  play: '<path d="m9 5 11 7-11 7z"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  type: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01m4 0h.01m4 0h.01m4 0h.01M6 13h.01m4 0h.01m4 0h.01m4 0h.01M8 16h8"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  cross: '<path d="M6 6l12 12M18 6 6 18"/>',
  ask: '<path d="M9 9a3 3 0 1 1 4.4 2.6c-.9.5-1.4 1.1-1.4 2.1M12 18h.01"/>',
  fix: '<path d="M4 8h13l-3-3m6 11H7l3 3"/>',
  dot: '<circle cx="12" cy="12" r="3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  phone: '<path d="M22 17v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3l2 5-3 2a14 14 0 0 0 9 9l2-3z"/>',
  replay: '<path d="M3 12a9 9 0 1 1 3 7m-3-1v-6h6"/>',
  undo: '<path d="M9 14 4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
};
export const icon = (name, size = 18) =>
  `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]}</svg>`;
export const glyph = name =>
  `<svg class="glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]}</svg>`;

/** One vocabulary for how a fact ended up. Each has a word, a shape (glyph) and a colour. */
export const statuses = {
  verified: {label: 'Verified', glyph: 'check', info: 'status_verified'},
  fixed: {label: 'Fixed', glyph: 'fix', info: 'status_fixed'},
  ask: {label: 'Asks', glyph: 'ask', info: 'status_ask'},
  heard: {label: 'Heard', glyph: 'dot', info: 'status_heard'},
  wrong: {label: 'Silent error', glyph: 'cross', info: 'status_wrong'},
};
export const statusOfEntity = entity => ({CONFIRMED: 'verified', FIXED: 'fixed', FLAGGED: 'ask'})[entity.status] || 'heard';

export const badge = (key, {withInfo = false} = {}) => {
  const s = statuses[key];
  return `<span class="badge badge-${key}">${glyph(s.glyph)}${s.label}</span>${withInfo ? info(s.info) : ''}`;
};

export const elapsed = seconds => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;

export const languageNames = {en: 'Indian English', hi: 'Hindi', hl: 'Hinglish', te: 'Telugu'};
export const factTypes = {AMOUNT: 'Amount', ORG: 'Company', PERSON: 'Person', PHONE: 'Phone number', PIN: 'PIN code', PLACE: 'Place'};
export const factWord = type => factTypes[type] || type;
