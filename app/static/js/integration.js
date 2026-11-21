// Integrate: five ways to put Pehchaan behind a speech model, each ready to copy.
import {esc} from './util.js';

const REPO = 'https://github.com/dev-seek/Pehchaan.git';

function examples(origin) {
  return [
    {id: 'proxy', wide: true, title: 'Change one line in an OpenAI app', note: 'Your OpenAI key keeps working and pays for its own calls. The answer is a normal transcription with one extra field, <code>pehchaan</code>.',
      code: `from openai import OpenAI

client = OpenAI(base_url="${origin}/v1")  # the only change

result = client.audio.transcriptions.create(model="gpt-transcribe", file=open("call.wav", "rb"))
print(result.text)
print(result.model_extra["pehchaan"]["clarifier_prompt"])`},
    {id: 'sdk', title: 'Wrap any speech model in three lines', note: 'Deepgram, Sarvam, Google, Azure or your own. These providers work through the same call but have not been benchmarked.',
      code: `# pip install "git+${REPO}"
from pehchaan_sdk import Pehchaan
p = Pehchaan(city="Hyderabad", contacts=[{"name": "Ravi Kumar"}])
print(p.verify_transcript(text_from_any_stt).verified_text)`},
    {id: 'context', title: 'Tell it what the phone knows', note: 'Call context is what lets Pehchaan verify a fact. It goes in one header. To try the demo, pass the passcode as <code>api_key</code>.',
      code: `import json
from openai import OpenAI

context = {"user": {"city": "Hyderabad"},
           "contacts": [{"name": "Ravi Kumar"}]}
client = OpenAI(
    base_url="${origin}/v1",
    default_headers={"X-Pehchaan-Context": json.dumps(context)})`},
    {id: 'stream', title: 'Check a call while it happens', note: 'Send 16 kHz mono 16-bit audio, or final transcripts from another speech model. Facts arrive phrase by phrase, after each pause.',
      code: `const ws = new WebSocket("${origin.replace(/^http/, 'ws')}/v1/stream");
const send = message => ws.send(JSON.stringify(message));
ws.onopen = () => send({type: "start", mode: "transcript",
                        auth: {passcode: "..."}});
ws.onmessage = ({data}) => {
  const event = JSON.parse(data);
  console.log(event);  // ready, phrase, fact, clarifier, final
  if (event.type !== "ready") return;
  send({type: "transcript", text: "Mera number 98480 12345 hai",
        is_final: true});
  send({type: "stop"});
};`},
    {id: 'curl', title: 'Try it with curl', note: 'Verify a transcript from any model. Replace the passcode, or send <code>X-OpenAI-Key</code>.',
      code: `curl "${origin}/v1/verify-transcript" \\
  -H "X-Demo-Passcode: ..." \\
  -H "Content-Type: application/json" \\
  -d '{"text": "Main Ravi Kumaar bol raha hoon",
       "context": {"contacts": [{"name": "Ravi Kumar"}]}}'`},
  ];
}

const FIELDS = [
  ['verified_text', 'The transcript after checking.'],
  ['entities', 'Each fact, with what was heard, the final value, the reason and one status.'],
  ['clarifier_prompt', 'One short question, ready for your voice agent to say.'],
  ['telemetry', 'Timings, models used, and which benchmark (if any) covers this setup.'],
];
const STATUSES = [
  ['FIXED', 'Changed, with a reason. Never a phone number, PIN or amount.'],
  ['VERIFIED', 'Independent evidence matches what was heard, even if the spelling is tidied.'],
  ['HEARD', 'Left as transcribed. No evidence for or against it.'],
  ['FLAGGED', 'Could not be settled, so ask the caller.'],
];

export function mountIntegration(root) {
  const origin = location.origin;
  root.classList.add('page', 'api');
  root.innerHTML = `
    <header class="page-head"><h1>Integrate</h1>
      <p class="lede">Pehchaan is a layer after speech-to-text. Keep your model, add the check, and get back the facts and one question to ask.</p>
      <p class="head-links"><a class="button button-primary" href="/docs">Open the API docs</a> <a class="button" href="#how">How the engine works</a></p></header>
    <div class="examples">
      ${examples(origin).map(({id, wide, title, note, code}) => `<article class="card-soft example${wide ? ' is-wide' : ''}">
        <header><h2>${esc(title)}</h2><button class="button" type="button" data-copy="${id}-example">Copy</button></header>
        <p class="note">${note}</p>
        <pre tabindex="0" aria-label="${esc(title)}"><code id="${id}-example">${esc(code)}</code></pre></article>`).join('')}
    </div>
    <p id="api-copy-status" class="sr-only" role="status"></p>
    <div class="api-reference">
      <article class="card-soft fields"><h2>What comes back</h2><dl>${FIELDS.map(([k, v]) => `<div><dt><code>${k}</code></dt><dd>${esc(v)}</dd></div>`).join('')}</dl></article>
      <article class="card-soft fields"><h2>The four statuses</h2><dl>${STATUSES.map(([k, v]) => `<div><dt><code>${k}</code></dt><dd>${esc(v)}</dd></div>`).join('')}</dl></article>
    </div>
    <p class="note">Public limits: 15 live requests per hour per address, 150 per day in total, 30 seconds and 5 MB per clip. Sample calls and benchmark results are free.</p>`;
  root.addEventListener('click', async event => {
    const button = event.target.closest('[data-copy]');
    if (!button) return;
    const code = document.getElementById(button.dataset.copy);
    const status = root.querySelector('#api-copy-status');
    try {
      await navigator.clipboard.writeText(code.textContent);
      button.textContent = 'Copied';
      status.textContent = 'Example copied.';
      setTimeout(() => { button.textContent = 'Copy'; }, 1500);
    } catch {
      getSelection().selectAllChildren(code);
      code.closest('pre').focus();
      status.textContent = 'Example selected. Use your keyboard to copy.';
    }
  });
}
