import { buildSegments, isSpeakingAt, mouthAt } from "./coarticulation.js";
import { VisemeDetector } from "./visemeDetector.js";
import { parseVisemeModel } from "./visemeModel.js";
// ZAELAR CHANGE: self-hosted model, nothing fetched from a CDN.
export const DEFAULT_MODEL_URL = new URL("./viseme-model.bin", import.meta.url).href;
const DEFAULT_STREAM_DELAY_MS = 150;
const SPEAK_START_MS = 50; // scheduling margin before a clip starts
const HISTORY_MS = 5000; // viseme events kept behind the playhead (coarticulation looks back up to ~250 ms)
const STREAM_GAP_S = 0.02; // a jump this big in captured audio time restarts the stream's viseme timeline
const ANALYSIS_CHUNK_S = 1; // speak(): analyse this much audio between yields to keep the page responsive
// Hands the stream's audio from the audio thread to the model, in 1024-sample blocks stamped with context time.
const CAPTURE_PROCESSOR = "talking-avatar-capture";
const CAPTURE_WORKLET = `
class Capture extends AudioWorkletProcessor {
  constructor() { super(); this.block = new Float32Array(1024); this.filled = 0; this.time = 0; }
  send() {
    this.port.postMessage({ time: this.time, samples: this.block.slice(0, this.filled) });
    this.filled = 0;
  }
  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;
    if (this.filled + input.length > this.block.length) this.send();
    if (this.filled === 0) this.time = currentTime;
    this.block.set(input, this.filled);
    this.filled += input.length;
    if (this.filled === this.block.length) this.send();
    return true;
  }
}
registerProcessor("${CAPTURE_PROCESSOR}", Capture);
`;
const models = new Map();
function loadModel(url) {
    let model = models.get(url);
    if (!model) {
        model = fetch(url).then((res) => {
            if (!res.ok)
                throw new Error(`talking-avatar: viseme model ${url}: HTTP ${res.status}`);
            return res.arrayBuffer();
        }).then(parseVisemeModel);
        model.catch(() => models.delete(url)); // let a later call retry
        models.set(url, model);
    }
    return model;
}
/**
 * A 3D avatar whose mouth follows any audio. Give it a container and an avatar URL, then either
 * `attachStream(mediaStream)` (live audio, e.g. WebRTC) or `speak(audio)` (a clip). The avatar plays the audio
 * itself; don't also play it elsewhere. Call those from a user gesture (or after one) so the browser allows sound.
 */
export class TalkingAvatar {
    /** Resolves when the first avatar is on screen; rejects if it fails to load. */
    ready;
    renderer;
    modelUrl;
    streamDelayS;
    onError;
    context = null;
    contextReady = null;
    events = []; // in "heard" audio-context time, ms
    segments = null;
    stream = null;
    speech = null;
    streamToken = 0;
    speechToken = 0;
    status = "listening";
    disposed = false;
    constructor(options) {
        this.modelUrl = options.modelUrl ?? DEFAULT_MODEL_URL;
        this.streamDelayS = (options.streamDelayMs ?? DEFAULT_STREAM_DELAY_MS) / 1000;
        this.onError = options.onError ?? ((error) => console.error(error));
        // ZAELAR CHANGE: the renderer is injected (Zaelar draws its own non-human faces; upstream's GLB human
        // renderer is not vendored). Contract: getFrame() -> { visemes, mode } once per frame; dispose().
        this.renderer = options.createRenderer(options.container, () => this.frameNow());
        this.ready = Promise.resolve(this.renderer.ready);
        this.ready.catch(() => { }); // reported through onError; awaiting `ready` is optional
        loadModel(this.modelUrl).catch((error) => this.onError(error)); // warm up
    }
    /**
     * How the avatar behaves while it isn't speaking: "listening" (default) or "thinking" (e.g. while your agent is
     * generating a reply). Speaking is detected automatically from its audio and takes priority.
     */
    setStatus(status) {
        this.status = status;
    }
    /**
     * Lip sync a live audio stream (WebRTC, getUserMedia, captureStream…). The avatar plays it, `streamDelayMs`
     * late. Replaces any previously attached stream.
     */
    async attachStream(stream) {
        this.detachStream();
        if (!stream.getAudioTracks().length)
            throw new Error("talking-avatar: the stream has no audio track");
        const token = ++this.streamToken;
        const [context, model] = await Promise.all([this.audioContext(), loadModel(this.modelUrl)]);
        if (token !== this.streamToken || this.disposed)
            return;
        // Chrome only feeds a remote (WebRTC) stream into Web Audio while a media element is playing it.
        const element = new Audio();
        element.muted = true;
        element.srcObject = stream;
        element.play().catch(() => { });
        const source = context.createMediaStreamSource(stream);
        const delay = context.createDelay(Math.max(1, this.streamDelayS * 2));
        delay.delayTime.value = this.streamDelayS;
        source.connect(delay).connect(context.destination);
        const capture = new AudioWorkletNode(context, CAPTURE_PROCESSOR, {
            numberOfOutputs: 0, channelCount: 1, channelCountMode: "explicit", channelInterpretation: "speakers",
        });
        source.connect(capture);
        const attached = { source, delay, capture, element, detector: null, expectedTime: 0 };
        capture.port.onmessage = ({ data }) => {
            if (this.stream !== attached)
                return;
            try {
                // (Re)start the timeline when capture begins or after a gap (e.g. the context was suspended).
                if (!attached.detector || Math.abs(data.time - attached.expectedTime) > STREAM_GAP_S) {
                    attached.detector?.flush();
                    const heardAtMs = (data.time + this.streamDelayS) * 1000;
                    attached.detector = new VisemeDetector(model, context.sampleRate, heardAtMs, (event) => this.addEvent(event));
                }
                attached.detector.push(data.samples);
                attached.expectedTime = data.time + data.samples.length / context.sampleRate;
            }
            catch (error) {
                this.onError(error);
            }
        };
        this.stream = attached;
    }
    /**
     * ZAELAR CHANGE — capture-only lip sync: same pipeline as attachStream(), but the avatar NEVER plays the audio.
     * The app keeps playing the stream through its own element, so the voice is never doubled and gets no added
     * latency. The price: the model's lookahead is not hidden behind a delay, so the mouth trails by `lipLagMs`.
     */
    async observeStream(stream) {
        this.detachStream();
        if (!stream || !stream.getAudioTracks().length)
            throw new Error("talking-avatar: the stream has no audio track");
        const token = ++this.streamToken;
        const [context, model] = await Promise.all([this.audioContext(), loadModel(this.modelUrl)]);
        if (token !== this.streamToken || this.disposed)
            return;
        this.lipLagMs = (((model.lookahead + 2) * model.HOP + model.WIN / 2) / model.SR) * 1000;
        const source = context.createMediaStreamSource(stream);
        const capture = new AudioWorkletNode(context, CAPTURE_PROCESSOR, {
            numberOfOutputs: 0, channelCount: 1, channelCountMode: "explicit", channelInterpretation: "speakers",
        });
        source.connect(capture);
        const attached = { source, delay: { disconnect() { } }, capture, element: { srcObject: null }, detector: null, expectedTime: 0 };
        capture.port.onmessage = ({ data }) => {
            if (this.stream !== attached)
                return;
            try {
                if (!attached.detector || Math.abs(data.time - attached.expectedTime) > STREAM_GAP_S) {
                    attached.detector?.flush();
                    attached.detector = new VisemeDetector(model, context.sampleRate, data.time * 1000, (event) => this.addEvent(event));
                }
                attached.detector.push(data.samples);
                attached.expectedTime = data.time + data.samples.length / context.sampleRate;
            }
            catch (error) {
                this.onError(error);
            }
        };
        this.stream = attached;
    }
    /** ZAELAR CHANGE — resume the audio context from a user gesture. */
    async unlock() {
        const context = await this.audioContext();
        if (context.state !== "running")
            await context.resume().catch(() => { });
        return context.state;
    }
    /** ZAELAR CHANGE — the injected renderer. */
    get view() { return this.renderer; }
    /** Stop playing and lip syncing the attached stream. */
    detachStream() {
        this.streamToken += 1;
        const attached = this.stream;
        if (!attached)
            return;
        this.stream = null;
        attached.capture.port.onmessage = null;
        attached.source.disconnect();
        attached.delay.disconnect();
        attached.capture.disconnect();
        attached.element.srcObject = null;
        this.events = [];
        this.segments = null;
    }
    /**
     * Play a clip (URL, encoded bytes or Blob, in any format the browser decodes) with lip sync. The whole clip is
     * analysed before it starts, so the mouth anticipates every sound. Resolves when it ends or is stopped.
     */
    async speak(audio) {
        this.stopSpeaking();
        const token = ++this.speechToken;
        let bytes;
        if (typeof audio === "string") {
            const res = await fetch(audio);
            if (!res.ok)
                throw new Error(`talking-avatar: ${audio}: HTTP ${res.status}`);
            bytes = await res.arrayBuffer();
        }
        else {
            bytes = audio instanceof Blob ? await audio.arrayBuffer() : audio.slice(0); // decodeAudioData detaches it
        }
        const [context, model] = await Promise.all([this.audioContext(), loadModel(this.modelUrl)]);
        const buffer = await context.decodeAudioData(bytes);
        const mono = new Float32Array(buffer.length);
        for (let c = 0; c < buffer.numberOfChannels; c += 1) {
            const channel = buffer.getChannelData(c);
            for (let i = 0; i < mono.length; i += 1)
                mono[i] += channel[i] / buffer.numberOfChannels;
        }
        const clipEvents = [];
        const detector = new VisemeDetector(model, buffer.sampleRate, 0, (event) => clipEvents.push(event));
        const chunk = Math.round(buffer.sampleRate * ANALYSIS_CHUNK_S);
        for (let i = 0; i < mono.length; i += chunk) {
            detector.push(mono.subarray(i, i + chunk));
            await new Promise((resolve) => setTimeout(resolve)); // yield between chunks
            if (token !== this.speechToken || this.disposed)
                return;
        }
        detector.flush();
        const startAt = context.currentTime + SPEAK_START_MS / 1000;
        for (const event of clipEvents)
            this.addEvent({ id: event.id, ms: startAt * 1000 + event.ms });
        const source = context.createBufferSource();
        source.buffer = buffer;
        source.connect(context.destination);
        const ended = new Promise((resolve) => { source.onended = () => resolve(); });
        source.start(startAt);
        this.speech = source;
        await ended;
        if (this.speech === source)
            this.speech = null;
    }
    /** Stop any clip started with speak(). */
    stopSpeaking() {
        this.speechToken += 1;
        const source = this.speech;
        if (!source)
            return;
        this.speech = null;
        source.stop();
        source.disconnect();
        this.events = [];
        this.segments = null;
    }
    /** Release the renderer, audio and model references. The instance can't be used afterwards. */
    dispose() {
        if (this.disposed)
            return;
        this.disposed = true;
        this.stopSpeaking();
        this.detachStream();
        this.renderer.dispose();
        void this.context?.close();
    }
    async audioContext() {
        this.contextReady ??= (async () => {
            const context = new AudioContext({ latencyHint: "interactive" });
            const url = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: "text/javascript" }));
            try {
                await context.audioWorklet.addModule(url);
            }
            finally {
                URL.revokeObjectURL(url);
            }
            this.context = context;
            return context;
        })();
        const context = await this.contextReady;
        if (context.state === "suspended")
            await context.resume();
        return context;
    }
    addEvent(event) {
        const { events } = this;
        let i = events.length;
        while (i > 0 && events[i - 1].ms > event.ms)
            i -= 1; // keep time order when clip and stream overlap
        events.splice(i, 0, event);
        // Drop history well behind the playhead, keeping the event still in effect.
        const cutoff = this.heardMs() - HISTORY_MS;
        let drop = 0;
        while (drop + 1 < events.length && events[drop + 1].ms < cutoff)
            drop += 1;
        if (drop)
            events.splice(0, drop);
        this.segments = null;
    }
    /** The audio-context time (ms) currently coming out of the speakers. */
    heardMs() {
        const { context } = this;
        if (!context)
            return 0;
        const stamp = context.state === "running" ? context.getOutputTimestamp?.() : undefined;
        if (stamp?.contextTime && stamp.performanceTime) {
            return stamp.contextTime * 1000 + (performance.now() - stamp.performanceTime);
        }
        return (context.currentTime - (context.outputLatency || 0)) * 1000;
    }
    frameNow() {
        if (!this.events.length)
            return { visemes: {}, mode: this.status };
        const now = this.heardMs();
        this.segments ??= buildSegments(this.events);
        return { visemes: mouthAt(this.segments, now), mode: isSpeakingAt(this.events, now) ? "speaking" : this.status };
    }
}
