// The Learning demo: Pehchaan asks, you answer, six checks run, the question disappears, and you can undo it.
import {esc, icon, int, ms, glyph} from './util.js';
import {info} from './info.js';
import {passage} from './transcript.js';
import {checkList, ledger} from './pg-views.js';

const NUMBERS = ['PHONE', 'PIN', 'AMOUNT'];
const FAR_ANSWER = 'Mumbai Central';  // sounds nothing like any heard word, so the sound check can refuse it

/** An open question this call could learn from. One whose known answer differs from what was heard shows the most. */
export function learnTarget(results, mainId) {
  const found = [];
  for (const [level, id] of [['C3', mainId], ['C4', 'P_on_B1_C4']]) {
    const result = results.get(id);
    for (const q of result?.questions || []) {
      const entity = result.entities.find(e => e.id === q.entity_id);
      if (entity && !NUMBERS.includes(entity.etype)) {
        const known = result.scored?.entities?.find(f => f.type === entity.etype && f.flagged && !f.correct)?.value;
        found.push({level, systemId: id, entityId: q.entity_id, question: q.question, heard: entity.surface, known, choices: (q.choices || []).filter(Boolean)});
      }
    }
  }
  return found.find(t => t.known && t.known !== t.heard) || found[0] || null;
}

const step = (n, title, state, body) => `<li class="step is-${state}"><span class="step-n" aria-hidden="true">${state === 'done' ? glyph('check') : n}</span>
  <div class="step-body"><h3>${title}</h3>${state === 'todo' ? '' : body}</div></li>`;

function askStep(target, result, learn) {
  if (learn.verdict?.adopted) return `<p class="learn-q">“${esc(target.question)}”</p>`;
  const answers = target.known ? [target.known] : target.choices.slice(0, 2);
  return `<p class="transcript">${passage(result, false)}</p>
    <p class="learn-q">“${esc(target.question)}”</p>
    <div class="choices">
      ${answers.map(a => `<button class="button button-primary" type="button" data-learn="${esc(a)}" ${learn.busy ? 'disabled' : ''}>Answer: ${esc(a)}</button>`).join('')}
      <button class="button" type="button" data-learn="${FAR_ANSWER}" ${learn.busy ? 'disabled' : ''}>Try a wrong answer</button>
    </div>
    <form class="learn-own" data-learn-form><label>Or type an answer<input name="canonical" type="text" autocomplete="off" maxlength="100" required></label><button class="button" type="submit" ${learn.busy ? 'disabled' : ''}>Test it</button></form>
    ${learn.rejected ? rejected(learn.rejected) : ''}`;
}

function rejected(v) {
  const failed = (v.checks || []).find(c => c.passed === false);
  return `<div class="verdict is-rejected is-fresh" role="status"><h4>${glyph('cross')} Refused. Nothing was saved.</h4>
    ${failed ? `<p>“${esc(v.canonical)}” failed <b>${esc(String(failed.name).replaceAll('_', ' '))}</b>.</p>` : ''}${checkList(v.checks)}</div>`;
}

function adopted(v, learn) {
  const settled = learn.replay || learn.replaying;
  const checks = settled ? `<details><summary>See the ${int(v.checks?.length || 0)} checks</summary>${checkList(v.checks)}</details>` : checkList(v.checks);
  return `<div class="verdict is-adopted${settled ? '' : ' is-fresh'}" role="status"><h4>${glyph('check')} Learned “${esc(v.canonical)}”</h4>
    <p>Replayed <b class="num">${int(v.clips_replayed)}</b> labelled calls in ${ms(v.ms)}. <b class="num">${int(v.facts_harmed)}</b> facts harmed.</p>${checks}</div>`;
}

export function learningView({target, result, learn, events}) {
  if (!target || !result) return `<div class="state-box"><strong>${learn.none ? 'No sample call has an open question right now.' : 'Loading a call with an open question…'}</strong></div>`;
  const {verdict, replay} = learn;
  const replayBody = `${replay ? `<div class="call-pair">
      <section class="call-side"><h3>Before</h3><p class="transcript">${passage(result, false)}</p></section>
      <section class="call-side is-main"><h3>After learning</h3><p class="transcript">${passage(replay, false)}</p></section></div>
      <p class="note">${replay.questions?.length ? 'A question remains.' : 'The question is gone.'} ${replay.llm_calls ?? 0} LLM calls.</p>`
    : `<button class="button button-primary" type="button" data-replay ${learn.replaying ? 'disabled' : ''}>${icon('replay')} ${learn.replaying ? 'Replaying…' : 'Replay the same call'}</button>`}`;
  const undoBody = verdict?.adopted ? `<button class="button" type="button" data-undo="${esc(verdict.event_id)}">${icon('undo')} Undo what it learned</button>
    <p class="note">A wrong answer that sounds right can pass these checks. That is why every lesson can be undone.</p>` : '';
  return `<ol class="steps">
    ${step(1, `Pehchaan is not sure${info('status_ask')}`, verdict?.adopted ? 'done' : 'now', askStep(target, result, learn))}
    ${step(2, `Your answer is tested first${info('verified_learning')}`, verdict?.adopted ? 'done' : 'todo', verdict?.adopted ? adopted(verdict, learn) : '')}
    ${step(3, 'The same call, again', replay ? 'done' : verdict?.adopted ? 'now' : 'todo', replayBody)}
    ${step(4, 'You stay in control', replay ? 'now' : 'todo', undoBody)}
  </ol>
  <details class="history"><summary>History (${int(events?.length || 0)})${info('ledger')}</summary>${ledger(events)}</details>`;
}
