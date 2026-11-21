// The line-quality curve: silent errors as the phone line gets worse. One axis, three labelled series, hover for values.
import {esc, int} from './util.js';

const LINES = [['clean', 'Clear'], ['phone', 'Standard'], ['noisy', 'Noisy'], ['very_noisy', 'Very noisy'], ['dropouts', 'Dropouts']];
const SERIES = [
  {id: 'B0_asr_plain', name: 'Plain speech-to-text', color: '#b5651d', dash: '2 5'},
  {id: 'B1_asr_keywords_C3', name: 'OpenAI keywords', color: '#3f6fd8', dash: '8 5'},
  {id: 'P_on_B1_C3', name: 'Pehchaan', color: '#0f8a5a', dash: ''},
];
const W = 720;
const H = 290;
const M = {top: 12, right: 150, bottom: 34, left: 40};

/** Keep end labels readable when series finish close together. */
function spread(items, gap) {
  const sorted = [...items].sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i++) sorted[i].y = Math.max(sorted[i].y, sorted[i - 1].y + gap);
  return sorted;
}

export function lineChart(real) {
  const lines = LINES.filter(([key]) => real[key]?.totals);
  const series = SERIES.filter(s => lines.every(([key]) => real[key].totals[s.id]));
  if (lines.length < 2 || !series.length) return '';
  const facts = real[lines[0][0]].totals[series[0].id].facts;
  const x = i => M.left + i * (W - M.left - M.right) / (lines.length - 1);
  const value = (s, key) => real[key].totals[s.id].silent;
  const highest = Math.max(1, ...series.flatMap(s => lines.map(([key]) => value(s, key))));
  const step = Math.ceil(highest / 4);
  const top = step * Math.ceil(highest / step);
  const y = v => M.top + (1 - v / top) * (H - M.top - M.bottom);
  const ticks = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  const paths = series.map(s => {
    const points = lines.map(([key], i) => `${x(i).toFixed(1)},${y(value(s, key)).toFixed(1)}`);
    return `<polyline class="series" points="${points.join(' ')}" stroke="${s.color}"${s.dash ? ` stroke-dasharray="${s.dash}"` : ''}/>
      ${lines.map(([key], i) => `<circle class="point" cx="${x(i).toFixed(1)}" cy="${y(value(s, key)).toFixed(1)}" r="5" fill="${s.color}"/>`).join('')}`;
  }).join('');
  const last = lines[lines.length - 1][0];
  const ends = spread(series.map(s => ({s, y: y(value(s, last)) + 4})), 15);
  const band = (W - M.left - M.right) / (lines.length - 1);
  const bands = lines.map(([key, label], i) => {
    const tip = series.map(s => `${s.name}|${int(value(s, key))}`).join(';');
    return `<rect class="band" tabindex="0" x="${(x(i) - band / 2).toFixed(1)}" y="${M.top}" width="${band.toFixed(1)}" height="${H - M.top - M.bottom}"
      data-tip="${esc(tip)}" data-label="${esc(label)}" data-x="${x(i).toFixed(1)}" aria-label="${esc(label)}: ${esc(series.map(s => `${s.name} ${value(s, key)}`).join(', '))}"/>`;
  }).join('');
  return `<figure class="curve" id="line-curve">
    <figcaption class="sr-only">Facts wrong with no warning, out of ${int(facts)}, for each phone line quality.</figcaption>
    <ul class="curve-legend">${series.map(s => `<li><svg viewBox="0 0 26 8" aria-hidden="true"><line x1="0" y1="4" x2="26" y2="4" stroke="${s.color}" stroke-width="2.5"${s.dash ? ` stroke-dasharray="${s.dash}"` : ''}/></svg>${esc(s.name)}</li>`).join('')}</ul>
    <div class="curve-scroll"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Silent errors by line quality">
      ${ticks.map(v => `<line class="grid" x1="${M.left}" x2="${W - M.right}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/><text x="${M.left - 8}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${v}</text>`).join('')}
      ${lines.map(([, label], i) => `<text x="${x(i).toFixed(1)}" y="${H - 10}" text-anchor="middle">${esc(label)}</text>`).join('')}
      ${paths}
      ${ends.map(({s, y: at}) => `<text class="end" x="${W - M.right + 10}" y="${at.toFixed(1)}">${esc(s.name)} ${int(value(s, last))}</text>`).join('')}
      ${bands}
    </svg></div>
    <p class="note">Facts wrong with no warning, out of ${int(facts)}. Lower is better.</p>
    <div class="curve-tip" role="status" hidden></div>
  </figure>`;
}

export function wireChart(root) {
  const figure = root.querySelector('#line-curve');
  if (!figure) return;
  const tip = figure.querySelector('.curve-tip');
  const svg = figure.querySelector('.curve-scroll svg');
  const show = band => {
    tip.innerHTML = `<b>${esc(band.dataset.label)}</b>${band.dataset.tip.split(';').map(row => {
      const [name, value] = row.split('|');
      return `<span>${esc(name)}<strong>${esc(value)}</strong></span>`;
    }).join('')}`;
    tip.hidden = false;
    const box = svg.getBoundingClientRect();
    const host = figure.getBoundingClientRect();
    const left = box.left - host.left + Number(band.dataset.x) / W * box.width + 12;
    tip.style.left = `${Math.max(4, Math.min(left, host.width - tip.offsetWidth - 4))}px`;
    tip.style.top = `${box.top - host.top + 12}px`;
  };
  figure.addEventListener('pointerover', event => { if (event.target.matches('.band')) show(event.target); });
  figure.addEventListener('focusin', event => { if (event.target.matches('.band')) show(event.target); });
  figure.addEventListener('pointerleave', () => { tip.hidden = true; });
  figure.addEventListener('focusout', () => { tip.hidden = true; });
}
