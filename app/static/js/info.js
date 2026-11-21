// The reusable "i" explainer. Opens on hover, keyboard focus and tap; closes on Escape or an outside click.
// Markup comes from info(key). One shared popover is positioned next to the button and kept on screen.
import {glossary, hasTerm} from './glossary.js';

const escape = value => String(value).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

/** Button markup. `label` is the visible term, used for the accessible name. */
export function info(key, label) {
  if (!hasTerm(key)) return '';
  const name = label || glossary[key].name;
  return `<button class="info" type="button" data-info="${escape(key)}" aria-label="What is ${escape(name)}?" aria-expanded="false">i</button>`;
}

/** Text followed by its info button. */
export const term = (key, text) => `${text}${info(key, text)}`;

let pop = null;
let current = null;
let pinned = false;
let timer = 0;
let ready = false;

function ensurePop() {
  if (pop) return pop;
  pop = document.createElement('div');
  pop.id = 'info-pop';
  pop.className = 'info-pop';
  pop.setAttribute('role', 'tooltip');
  pop.hidden = true;
  if ('popover' in HTMLElement.prototype) pop.setAttribute('popover', 'manual');   // top layer: stays above open dialogs
  document.body.append(pop);
  pop.addEventListener('pointerenter', () => clearTimeout(timer));
  pop.addEventListener('pointerleave', () => { if (!pinned) schedule(close, 200); });
  return pop;
}

function place() {
  if (!current || !pop) return;
  const b = current.getBoundingClientRect();
  const margin = 8;
  pop.style.left = '0px';
  pop.style.top = '0px';
  const w = pop.offsetWidth;
  const h = pop.offsetHeight;
  const vw = document.documentElement.clientWidth;
  const vh = window.innerHeight;
  let left = Math.min(Math.max(margin, b.left + b.width / 2 - w / 2), vw - w - margin);
  let top = b.bottom + 8;
  if (top + h > vh - margin) top = b.top - h - 8;           // flip above when there is no room below
  top = Math.min(Math.max(margin, top), Math.max(margin, vh - h - margin));
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
}

function open(button) {
  const entry = glossary[button.dataset.info];
  if (!entry) return;
  clearTimeout(timer);
  if (current && current !== button) release(current);
  current = button;
  const p = ensurePop();
  p.innerHTML = `<strong>${escape(entry.name)}</strong><dl>
    <div><dt>What it is</dt><dd>${escape(entry.what)}</dd></div>
    <div><dt>How it works</dt><dd>${escape(entry.how)}</dd></div>
    <div><dt>Why it matters</dt><dd>${escape(entry.why)}</dd></div></dl>`;
  p.hidden = false;
  if (p.showPopover) { try { p.showPopover(); } catch { /* already open */ } }
  button.setAttribute('aria-expanded', 'true');
  button.setAttribute('aria-describedby', 'info-pop');
  place();
}

function release(button) {
  button.setAttribute('aria-expanded', 'false');
  button.removeAttribute('aria-describedby');
}

function close() {
  clearTimeout(timer);
  if (current) release(current);
  current = null;
  pinned = false;
  if (pop) {
    if (pop.hidePopover) { try { pop.hidePopover(); } catch { /* not open */ } }
    pop.hidden = true;
  }
}

function schedule(fn, delay) {
  clearTimeout(timer);
  timer = setTimeout(fn, delay);
}

const buttonOf = event => event.target instanceof Element ? event.target.closest('.info') : null;

export function initInfo() {
  if (ready) return;
  ready = true;
  document.addEventListener('pointerover', event => {
    const button = buttonOf(event);
    if (!button || event.pointerType !== 'mouse') return;
    if (!pinned) schedule(() => open(button), 120);
  });
  document.addEventListener('pointerout', event => {
    const button = buttonOf(event);
    if (!button || event.pointerType !== 'mouse' || pinned) return;
    schedule(close, 200);
  });
  document.addEventListener('focusin', event => {
    const button = buttonOf(event);
    if (button && !pinned) open(button);
  });
  document.addEventListener('focusout', event => {
    const button = buttonOf(event);
    if (button && !pinned && current === button) schedule(close, 100);
  });
  document.addEventListener('click', event => {
    const button = buttonOf(event);
    if (button) {
      event.preventDefault();
      event.stopPropagation();
      if (current === button && pinned) close();
      else { open(button); pinned = true; }          // a tap, or a click while hovering, keeps it open
      return;
    }
    if (current && !(pop && pop.contains(event.target))) close();
  }, true);
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !current) return;
    const button = current;
    close();
    button.focus({preventScroll: true});
    event.preventDefault();                       // close the tooltip first, not an open dialog
    event.stopPropagation();
  }, true);
  window.addEventListener('resize', () => place());
  document.addEventListener('scroll', () => place(), true);
}
