// Saved calls for one caller: the list, what this caller taught, and delete.
import {esc, icon, plural} from './util.js';
import {deleteCall, forgetCaller, listCalls} from './api.js';

const STORE = 'pehchaan.callers';
const SOURCES = {audio: 'Audio', text: 'Text', stream: 'Live', recheck: 'Checked again'};

function knownCallers() {
  try { return JSON.parse(localStorage.getItem(STORE) || '[]').filter(x => typeof x === 'string'); } catch { return []; }
}

function rememberCaller(id) {
  try { localStorage.setItem(STORE, JSON.stringify([id, ...knownCallers().filter(x => x !== id)].slice(0, 12))); } catch { /* storage blocked */ }
}

function dropCaller(id) {
  try { localStorage.setItem(STORE, JSON.stringify(knownCallers().filter(x => x !== id))); } catch { /* storage blocked */ }
}

function newCallerId() {
  const bytes = crypto.getRandomValues(new Uint8Array(4));
  return `caller-${[...bytes].map(b => b.toString(16).padStart(2, '0')).join('')}`;
}

export const callerField = `
  <div class="caller-row">
    <label>Caller ID<input id="live-caller" list="live-callers" maxlength="80" autocomplete="off" spellcheck="false"></label>
    <datalist id="live-callers"></datalist>
    <button class="button" id="live-new-caller" type="button">New caller</button>
  </div>
  <p class="note">Each call is saved as text under this ID. Audio is never saved.</p>`;

const when = seconds => new Date(seconds * 1000).toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit'});

function row(call) {
  const facts = call.result.entities || [];
  const asks = facts.filter(f => f.status === 'FLAGGED').length;
  return `<li><button class="saved-open" type="button" data-open-call="${esc(call.id)}">
      <span class="saved-meta">${esc(when(call.at))}, ${esc(SOURCES[call.source] || call.source)}</span>
      <span class="saved-text">${esc(call.result.verified_text)}</span>
      <span class="saved-meta">${plural(facts.length, 'fact')}${asks ? `, ${asks} to confirm` : ''}</span>
    </button><button class="icon-button" type="button" data-delete-call="${esc(call.id)}" aria-label="Delete this call">${icon('cross', 16)}</button></li>`;
}

export function mountCalls(root, {onOpen, say}) {
  const input = root.querySelector('#live-caller');
  const list = root.querySelector('#live-callers');
  const box = root.querySelector('#live-saved');
  const state = {calls: []};
  const caller = () => input.value.trim();

  const fillOptions = () => { list.innerHTML = knownCallers().map(id => `<option value="${esc(id)}"></option>`).join(''); };

  function draw(data) {
    state.calls = data.calls;
    const learned = data.learned.length ? `<p class="saved-learned"><b>Learned for this caller:</b> ${data.learned.map(x => `<span class="chip">${esc(x.heard)} to ${esc(x.canonical)}</span>`).join(' ')}</p>` : '';
    box.innerHTML = `<div class="saved-head"><h3>Saved calls for ${esc(data.caller)}</h3>
        ${data.calls.length || data.learned.length ? '<button class="link-button" type="button" data-forget-caller>Forget this caller</button>' : ''}</div>
      ${learned}
      ${data.calls.length ? `<ol class="saved-list">${data.calls.map(row).join('')}</ol>` : '<p class="note">No saved calls yet. Check a call and it appears here.</p>'}`;
  }

  async function refresh() {
    const id = caller();
    if (!id) { box.innerHTML = '<p class="note">Enter a caller ID to save calls.</p>'; return; }
    try {
      const data = await listCalls(id);
      if (id === caller()) draw(data);
    } catch (error) {
      box.innerHTML = `<p class="note">${esc(error.message || 'Saved calls could not be loaded.')}</p>`;
    }
  }

  function use(id) {
    input.value = id;
    rememberCaller(id);
    fillOptions();
    void refresh();
  }

  input.addEventListener('change', () => { if (caller()) use(caller()); else void refresh(); });
  root.querySelector('#live-new-caller').addEventListener('click', () => use(newCallerId()));
  box.addEventListener('click', async event => {
    const open = event.target.closest('[data-open-call]');
    const remove = event.target.closest('[data-delete-call]');
    try {
      if (open) {
        const call = state.calls.find(c => c.id === open.dataset.openCall);
        if (call) onOpen({...call.result, call_id: call.id}, call.caller);
      } else if (remove) {
        await deleteCall(remove.dataset.deleteCall);
        say('Call deleted.');
        await refresh();
      } else if (event.target.closest('[data-forget-caller]')) {
        const id = caller();
        await forgetCaller(id);
        dropCaller(id);
        fillOptions();
        say(`Forgot ${id}: its calls and what it taught.`);
        await refresh();
      }
    } catch (error) {
      say(error.message || 'That did not work. Try again.');
    }
  });

  use(knownCallers()[0] || newCallerId());
  return {caller, refresh};
}
