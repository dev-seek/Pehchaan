// Checks the deployed service from outside, the way a customer reaches it. Prints results, never a secret.
//   node deploy/verify_live.mjs https://host            everything free, plus one paid proxy call and one paid stream
//   node deploy/verify_live.mjs https://host --free     only what costs nothing
import {readFileSync, existsSync} from 'node:fs';
import {homedir} from 'node:os';
import {join} from 'node:path';

const BASE = process.argv[2]?.replace(/\/$/, '');
const FREE = process.argv.includes('--free');
const passFile = join(homedir(), '.pehchaan', 'demo_passcode');
const PASSCODE = existsSync(passFile) ? readFileSync(passFile, 'utf8').trim() : '';
const SAMPLE = 'data/demo/audio/real';
const CONTEXT = {user: {city: 'Hyderabad'}, contacts: [{name: 'Ravi Kumar', number: '9848012345'}]};
let failed = 0;

function report(name, ok, detail = '') {
  if (!ok) failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
}
const status = async (path, init) => (await fetch(BASE + path, init)).status;

function pcmFromWav(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let at = 12;
  while (at + 8 <= bytes.length) {
    const id = String.fromCharCode(...bytes.subarray(at, at + 4));
    const size = view.getUint32(at + 4, true);
    if (id === 'data') return {pcm: bytes.subarray(at + 8, at + 8 + size), rate: view.getUint32(24, true), channels: view.getUint16(22, true)};
    at += 8 + size + (size % 2);
  }
  throw new Error('no audio data in sample');
}

function to16k({pcm, rate, channels}) {
  const input = new Int16Array(pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.length - (pcm.length % 2)));
  const frames = Math.floor(input.length / channels);
  const out = new Int16Array(Math.floor(frames * 16000 / rate));
  for (let i = 0; i < out.length; i++) out[i] = input[Math.floor(i * rate / 16000) * channels];
  return new Uint8Array(out.buffer);
}

function stream(start, send) {
  return new Promise(resolve => {
    const ws = new WebSocket(`${BASE.replace(/^http/, 'ws')}/v1/stream`);
    const events = [];
    const done = closed => { clearTimeout(timer); resolve({events, closed}); };
    const timer = setTimeout(() => { ws.close(); done('timeout'); }, 60000);
    ws.onopen = () => ws.send(JSON.stringify({type: 'start', ...start}));
    ws.onmessage = ({data}) => {
      const m = JSON.parse(data);
      events.push(m);
      if (m.type === 'ready') send(ws);
    };
    ws.onclose = ({code}) => done(code);
    ws.onerror = () => {};
  });
}

const health = await (await fetch(`${BASE}/health`)).json();
report('/health', health.status === 'ok' && health.mode === 'production', `mode ${health.mode}`);
report('engine is the one that sat the exam', health.engine_matches_exam === true);
report('/docs', (await status('/docs')) === 200);
const paths = Object.keys((await (await fetch(`${BASE}/openapi.json`)).json()).paths);
report('/docs lists no private route', !paths.some(p => p.startsWith('/api') || /record|studio/.test(p)), `${paths.length} public routes`);
for (const path of ['/api/scripts', '/record', '/studio', '/static/record.html', '/static/studio.html']) {
  report(`private ${path} is gone`, (await status(path)) === 404);
}
report('recording upload is gone', (await status('/api/record', {method: 'POST'})) === 404);

const presets = await (await fetch(`${BASE}/api/demo/presets`)).json();
let samplesOk = 0;
for (const preset of presets) {
  const form = new FormData();
  form.set('preset', preset.id);
  const text = await (await fetch(`${BASE}/api/demo/compare`, {method: 'POST', body: form})).text();
  const events = text.trim().split('\n').map(l => JSON.parse(l));
  if (events.some(e => e.event === 'result') && !events.some(e => e.event === 'system_error')) samplesOk += 1;
}
report('sample calls work with no credential', samplesOk === presets.length && presets.length > 0, `${samplesOk} of ${presets.length}`);
const bench = await (await fetch(`${BASE}/v1/bench`)).json();
report('/v1/bench serves both exam lines', bench.exam.standard?.n_clips === 30 && bench.exam.noisy?.n_clips === 30);

const json = {'Content-Type': 'application/json'};
const body = JSON.stringify({text: 'Main Ravi Kumaar bol raha hoon, mera number 9848012345 hai', context: CONTEXT});
report('audio route refuses no credential', (await status('/v1/verify-audio', {method: 'POST', body: new FormData()})) === 401);
const freeCheck = await fetch(`${BASE}/v1/verify-transcript`, {method: 'POST', headers: json, body});
report('pasted text works free, with no paid model', freeCheck.ok && (await freeCheck.json()).telemetry.judge === 'off');
report('live route refuses a wrong passcode', (await status('/v1/verify-transcript', {method: 'POST', headers: {...json, 'X-Demo-Passcode': 'wrong'}, body})) === 401);
const refused = await stream({mode: 'transcript'}, () => {});
report('stream refuses no credential', refused.closed === 4401, `close ${refused.closed}`);

if (!FREE) {
  report('passcode is available on this machine', Boolean(PASSCODE));
  const wav = readFileSync(join(SAMPLE, (await import('node:fs')).readdirSync(SAMPLE).filter(f => f.endsWith('.wav')).sort()[0]));
  const form = new FormData();
  form.set('file', new Blob([wav], {type: 'audio/wav'}), 'call.wav');
  form.set('model', 'gpt-transcribe');
  const reply = await fetch(`${BASE}/v1/audio/transcriptions`, {method: 'POST', body: form,
    headers: {Authorization: `Bearer ${PASSCODE}`, 'X-Pehchaan-Context': JSON.stringify(CONTEXT)}});
  const answer = await reply.json();
  report('passcode-gated OpenAI proxy call', reply.status === 200 && Boolean(answer.text) && Boolean(answer.pehchaan?.telemetry),
    reply.status === 200 ? `${answer.pehchaan.entities.length} facts, speech ${answer.pehchaan.telemetry.stt_ms} ms, harness ${answer.pehchaan.telemetry.harness_ms} ms` : `HTTP ${reply.status}`);

  const pcm = to16k(pcmFromWav(wav));
  const live = await stream({mode: 'audio', auth: {passcode: PASSCODE}, context: CONTEXT}, ws => {
    for (let at = 0; at < pcm.length; at += 6400) ws.send(pcm.subarray(at, at + 6400));
    ws.send(JSON.stringify({type: 'stop'}));
  });
  const phrases = live.events.filter(e => e.type === 'phrase').length;
  const final = live.events.find(e => e.type === 'final');
  const error = live.events.find(e => e.type === 'error');
  report('live WS /v1/stream with real audio', phrases > 0 && Boolean(final?.result), error ? error.message : `${phrases} phrases, ${live.events.filter(e => e.type === 'fact').length} fact events`);
}
console.log(failed ? `\n${failed} check(s) failed` : '\nAll checks passed');
process.exit(failed ? 1 : 0);
