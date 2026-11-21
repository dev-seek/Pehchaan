// Integrate: one install, one line, and the exact snippet for the speech model you already use.
import {esc, badge} from './util.js';

const REPO = 'git+https://github.com/dev-seek/Pehchaan.git';
const FACTS = 'city="Hyderabad", contacts=["Ravi Kumar"]';
const OUTPUT = `print(result)                       # the checked transcript
print(result.pehchaan.clarifier_prompt)  # the question to ask, or None`;

const stacks = origin => [
  {id: 'openai', name: 'OpenAI', file: 'python', code: `from openai import OpenAI
from pehchaan_sdk import wrap

client = wrap(OpenAI(), ${FACTS})

result = client.audio.transcriptions.create(
    model="gpt-transcribe", file=open("call.wav", "rb"))
print(result.text)                       # the checked transcript
print(result.pehchaan.clarifier_prompt)  # the question to ask, or None`},
  {id: 'azure', name: 'Azure OpenAI', file: 'python', code: `from openai import AzureOpenAI
from pehchaan_sdk import wrap

client = wrap(AzureOpenAI(api_version="2025-01-01-preview"), ${FACTS})

result = client.audio.transcriptions.create(
    model="your-deployment", file=open("call.wav", "rb"))
print(result.text, result.pehchaan.clarifier_prompt)`},
  {id: 'deepgram', name: 'Deepgram', file: 'python', code: `import os, requests
from pehchaan_sdk import wrap

def deepgram(path):
    return requests.post(
        "https://api.deepgram.com/v1/listen?model=nova-3&language=multi",
        headers={"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}",
                 "Content-Type": "audio/wav"},
        data=open(path, "rb")).json()

transcribe = wrap(deepgram, ${FACTS})
result = transcribe("call.wav")
${OUTPUT}`},
  {id: 'sarvam', name: 'Sarvam', file: 'python', code: `import os, requests
from pehchaan_sdk import wrap

def sarvam(path):
    return requests.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]},
        data={"model": "saaras:v4", "mode": "transcribe", "language_code": "hi-IN"},
        files={"file": open(path, "rb")}).json()

transcribe = wrap(sarvam, ${FACTS})
result = transcribe("call.wav")
${OUTPUT}`},
  {id: 'google', name: 'Google', file: 'python', code: `from google.cloud import speech
from pehchaan_sdk import wrap

client = speech.SpeechClient()
config = speech.RecognitionConfig(language_code="hi-IN")

def google(path):
    audio = speech.RecognitionAudio(content=open(path, "rb").read())
    return client.recognize(config=config, audio=audio)

transcribe = wrap(google, ${FACTS})
result = transcribe("call.wav")
${OUTPUT}`},
  {id: 'own', name: 'Your own model', file: 'python', code: `from pehchaan_sdk import wrap

def my_model(path):
    return my_speech_engine.transcribe(path)  # return text or a dict

transcribe = wrap(my_model, ${FACTS})
result = transcribe("call.wav")
${OUTPUT}`},
  {id: 'node', name: 'Node or any language', file: 'javascript', code: `import fs from "node:fs";
import OpenAI from "openai";

// Point any OpenAI client at Pehchaan. Your key pays for your calls.
const client = new OpenAI({baseURL: "${origin}/v1"});

const result = await client.audio.transcriptions.create({
  model: "gpt-transcribe", file: fs.createReadStream("call.wav"),
});
console.log(result.text, result.pehchaan.clarifier_prompt);`},
  {id: 'stream', name: 'Live calls', file: 'javascript', code: `const ws = new WebSocket("${origin.replace(/^http/, 'ws')}/v1/stream");
const send = message => ws.send(JSON.stringify(message));

ws.onopen = () => send({type: "start", mode: "transcript",
                        auth: {openai_key: "sk-..."}});
ws.onmessage = ({data}) => {
  const event = JSON.parse(data);  // ready, phrase, fact, clarifier, final
  if (event.type === "ready") {
    send({type: "transcript", text: "Mera number 98480 12345 hai", is_final: true});
    send({type: "stop"});
  }
  if (event.type === "final") {
    console.log(event.result.verified_text);
    ws.close();
  }
};`},
];

const COMPANY_DATA = `from openai import OpenAI
from pehchaan_sdk import wrap, HttpSource

crm = HttpSource("crm", "https://crm.example.in/customers?phone={phone}",
                 headers={"Authorization": "Bearer ..."},
                 fields={"people": "records.*.Name", "amounts.emi": "records.0.Emi"})

client = wrap(OpenAI(), knowledge=[crm])
result = client.audio.transcriptions.create(
    model="gpt-transcribe", file=open("call.wav", "rb"),
    pehchaan={"caller": {"number": "9848012345"}})
print(result.pehchaan.knowledge)         # what each system gave`;

const copyBlock = (id, label, code) => `<div class="code-block"><pre tabindex="0" aria-label="${esc(label)}"><code id="${id}">${esc(code)}</code></pre>
  <button class="button" type="button" data-copy="${id}">Copy</button></div>`;

export function mountIntegration(root) {
  const origin = location.origin;
  const all = stacks(origin);
  root.classList.add('page', 'api');
  root.innerHTML = `
    <header class="page-head"><h1>Add it in one line</h1>
      <p class="lede">Keep your speech model. Wrap it. Your code works the same, and every answer comes back checked.</p></header>
    <section class="install" aria-label="Install">
      <h2>Install</h2>${copyBlock('install-code', 'Install command', `pip install "${REPO}"`)}
      <h2>Wrap your model</h2>${copyBlock('wrap-code', 'One line', `client = wrap(OpenAI(), ${FACTS})`)}
      <h2>Or try one call with no code</h2>${copyBlock('try-code', 'One command', `uvx --from "${REPO}" pehchaan call.wav --city Hyderabad --contact "Ravi Kumar"`)}
    </section>
    <section class="stack-pick" aria-labelledby="stack-title">
      <h2 id="stack-title">What do you use today?</h2>
      <div class="stack-tabs" role="tablist" aria-label="Speech provider">${all.map((s, i) => `<button role="tab" type="button" data-stack="${s.id}" aria-selected="${i === 0}">${esc(s.name)}</button>`).join('')}</div>
      ${all.map((s, i) => `<div class="stack-pane" data-pane="${s.id}" ${i ? 'hidden' : ''}>${copyBlock(`stack-${s.id}`, s.name, s.code)}</div>`).join('')}
      <p class="note">Measured: four OpenAI speech models. Other providers use the same check but have not been benchmarked, so results are marked <code>unmeasured</code>.</p>
    </section>
    <section class="install" aria-labelledby="company-title">
      <h2 id="company-title">Connect your company data</h2>
      <p class="note">Your systems are looked up from your own app, so their keys never reach Pehchaan. Records can confirm a fact or raise a question, and never change money, PINs or phone numbers. <a href="#playground?tab=knowledge">Try the simulated demo</a>.</p>
      ${copyBlock('company-code', 'Connect a company system', COMPANY_DATA)}
    </section>
    <section class="returns" aria-labelledby="returns-title">
      <h2 id="returns-title">Every fact comes back with one status</h2>
      <ul>
        <li>${badge('verified')}<span>Use it.</span></li>
        <li>${badge('fixed')}<span>Use it and log the original.</span></li>
        <li>${badge('heard')}<span>Fine for notes. Confirm before acting.</span></li>
        <li>${badge('ask')}<span>Play the question and wait.</span></li>
      </ul>
      <p class="note">Hosted limits: 15 live requests per hour per address, 30 seconds and 5 MB per clip. The installed package has none. <a href="/docs">API docs</a></p>
    </section>
    <p id="api-copy-status" class="sr-only" role="status"></p>`;

  root.addEventListener('click', async event => {
    const tab = event.target.closest('[data-stack]');
    if (tab) {
      for (const button of root.querySelectorAll('[data-stack]')) button.setAttribute('aria-selected', String(button === tab));
      for (const pane of root.querySelectorAll('.stack-pane')) pane.hidden = pane.dataset.pane !== tab.dataset.stack;
      return;
    }
    const button = event.target.closest('[data-copy]');
    if (!button) return;
    const code = document.getElementById(button.dataset.copy);
    const status = root.querySelector('#api-copy-status');
    try {
      await navigator.clipboard.writeText(code.textContent);
      button.textContent = 'Copied';
      status.textContent = 'Copied.';
      setTimeout(() => { button.textContent = 'Copy'; }, 1500);
    } catch {
      getSelection().selectAllChildren(code);
      code.closest('pre').focus();
      status.textContent = 'Selected. Use your keyboard to copy.';
    }
  });
}
