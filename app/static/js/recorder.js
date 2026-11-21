// Microphone recording, used by the Studio page.
import {elapsed} from './util.js';

export const canRecord = () => !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);

const extensions = {'audio/mp4': 'm4a', 'audio/ogg': 'ogg', 'audio/wav': 'wav'};

/**
 * Ask for the microphone and start recording. Resolves to a handle:
 *   handle.finish()  -> Promise<{blob, filename}|null>   (null when nothing was captured)
 *   handle.cancel()  -> discards the take
 * Rejects with the browser error (error.name === 'NotAllowedError' when the microphone is blocked).
 */
export async function startRecording(onTick = () => {}) {
  const media = await navigator.mediaDevices.getUserMedia({audio: true});
  const recorder = new MediaRecorder(media);
  const chunks = [];
  const startedAt = performance.now();
  let discard = false;
  let settle;
  const finished = new Promise(resolve => { settle = resolve; });
  recorder.addEventListener('dataavailable', e => { if (e.data.size) chunks.push(e.data); });
  recorder.addEventListener('error', () => { discard = true; if (recorder.state !== 'inactive') recorder.stop(); });
  recorder.addEventListener('stop', () => {
    clearInterval(timer);
    media.getTracks().forEach(t => t.stop());
    const type = recorder.mimeType || chunks[0]?.type || '';
    const blob = new Blob(chunks, {type});
    if (discard || !blob.size) return settle(null);
    settle({blob, filename: `recording.${extensions[type.split(';')[0]] || 'webm'}`});
  });
  const timer = setInterval(() => onTick(elapsed(Math.floor((performance.now() - startedAt) / 1000))), 250);
  recorder.start();
  onTick(elapsed(0));
  const stop = () => { if (recorder.state !== 'inactive') recorder.stop(); };
  return {finish: () => { stop(); return finished; }, cancel: () => { discard = true; stop(); return finished; }};
}

/** A plain-words reason for a microphone failure. */
export function micProblem(error) {
  if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') {
    return 'The microphone is blocked. Allow microphone access for this site in your browser settings, then try again.';
  }
  if (error?.name === 'NotFoundError') return 'No microphone was found on this device.';
  return 'The microphone could not start. Check that no other app is using it, then try again.';
}
