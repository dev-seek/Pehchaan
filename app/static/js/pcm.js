// Live microphone as 16 kHz mono 16-bit PCM, the format WS /v1/stream reads.
const TARGET_RATE = 16000;
const CHUNK_SAMPLES = 1600;       // 100 ms

export const canStream = () => !!(navigator.mediaDevices?.getUserMedia && window.AudioWorkletNode && window.WebSocket);

/** Average the input down to 16 kHz, keeping the position between calls so no sample is lost at a block edge. */
function resampler(inputRate, onChunk) {
  const step = inputRate / TARGET_RATE;
  let held = new Int16Array(CHUNK_SAMPLES);
  let filled = 0;
  let sum = 0;
  let count = 0;
  let position = 0;
  const emit = () => { onChunk(held.buffer.slice(0, filled * 2)); held = new Int16Array(CHUNK_SAMPLES); filled = 0; };
  return {
    push(block) {
      for (const sample of block) {
        sum += sample;
        count += 1;
        position += 1;
        if (position >= step) {
          position -= step;
          held[filled++] = Math.max(-1, Math.min(1, sum / count)) * 32767;
          sum = 0;
          count = 0;
          if (filled === CHUNK_SAMPLES) emit();
        }
      }
    },
    flush() { if (filled) emit(); },
  };
}

/** Call this directly inside the click handler, before any await. Safari only allows audio to start there. */
export function openMic() {
  const context = new AudioContext();
  context.resume().catch(() => {});
  const media = navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}});
  return {context, media};
}

/** Starts capturing from openMic(). Returns {stop()}. Rejects with the browser's error if the microphone is blocked. */
export async function startPcm({context, media: pending}, onChunk) {
  let media = null;
  try {
    media = await pending;
    await context.audioWorklet.addModule('/static/js/pcm-worklet.js');
  } catch (error) {
    media?.getTracks().forEach(track => track.stop());
    await context.close().catch(() => {});
    throw error;
  }
  context.resume().catch(() => {});
  const source = context.createMediaStreamSource(media);
  const node = new AudioWorkletNode(context, 'pcm-capture', {numberOfOutputs: 0});
  const convert = resampler(context.sampleRate, onChunk);
  node.port.onmessage = ({data}) => convert.push(data);
  source.connect(node);
  return {
    async stop() {
      node.port.onmessage = null;
      source.disconnect();
      media.getTracks().forEach(track => track.stop());
      convert.flush();
      await context.close();
    },
  };
}
