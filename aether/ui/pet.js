"use strict";

const TOKEN = document.querySelector('meta[name="aether-token"]').content;
const $ = (s) => document.querySelector(s);
const api = async (path, body) => {
  const opt = { headers: { "X-Aether-Token": TOKEN } };
  if (body !== undefined) { opt.method = "POST"; opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.status);
  return d;
};

let avatar = null, current = "", bubbleTimer = null, busy = false, lastDone = 0, micName = "";
function say(text, hold, you) {
  const b = $("#bubble");
  b.textContent = text;
  b.classList.toggle("you", !!you);
  b.classList.add("on");
  clearTimeout(bubbleTimer);
  bubbleTimer = setTimeout(() => b.classList.remove("on"), hold || 9000);
}

let quietUntil = 0;
Speaker.src = (id) => `/api/audio?t=${TOKEN}&id=${encodeURIComponent(id)}`;
Speaker.onState = (on) => { if (!on) quietUntil = Date.now() + 800; Ears.render(); };
VoiceClock.post = (body) => api("/api/voice/timing", body);
function hush() { Speaker.clear(); }

async function refresh() {
  try {
    const st = await api("/api/state");
    current = st.current;
    busy = !!st.busy;
    const mic = (st.settings && st.settings.mic_device) || "";
    if (mic !== micName) { micName = mic; if (Ears.on) { Ears.stop(); Ears.start(); } }
    if (avatar && st.life && st.life.mood) avatar.setMood(st.life.mood.name);
    const nm = st.agent && st.agent.name;
    if (nm) { document.title = nm; const box = document.getElementById("say"); if (box) box.placeholder = `Talk to ${nm}…`; }
  } catch (e) {  }
  Ears.render();
}

function connect() {
  const es = new EventSource(`/api/events?t=${encodeURIComponent(TOKEN)}`);
  let reply = "";
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "audio" && ev.pet) Speaker.add(ev);
    else if (ev.type === "audio_stop") hush();
    else if (ev.type === "user") { busy = true; reply = ""; if (ev.chat === current) say((ev.voice ? "🎤 " : "") + ev.text, 15000, true); Ears.render(); }
    else if (ev.type === "say") { VoiceClock.mark("words", ev.chat); reply += ev.text; say(reply, 15000); }
    else if (ev.type === "done" || ev.type === "error") {
      if (ev.type === "error") VoiceClock.cancel(); else VoiceClock.done();
      busy = false; lastDone = Date.now(); if (ev.type === "error") say(ev.text, 6000); refresh();
    }
    else if (ev.type === "reach_out") say(ev.text, 15000);
    else if (ev.type === "mood" || ev.type === "life") refresh();
  };
}

async function send(text, voice, tone, speaker) {
  text = (text || "").trim();
  if (!text) return false;
  if (!voice || busy) VoiceClock.cancel();
  if (busy) { say("Hold on, I'm still on the last one.", 3000); return false; }
  if (!current) await refresh();
  try {
    await api("/api/send", { id: current, text, voice: !!voice, tone: tone || "", speaker: speaker || "" });
    busy = true; Ears.render();
    return true;
  } catch (e) { VoiceClock.cancel(); say(String(e.message || e), 4000); return false; }
}

const input = $("#say");
input.addEventListener("keydown", async (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (await send(input.value)) { input.value = ""; $("#bar").classList.remove("has-text"); }
  }
  e.stopPropagation();
});
let lastTypingPing = 0;
input.addEventListener("input", () => {
  $("#bar").classList.toggle("has-text", !!input.value);
  if (Date.now() - lastTypingPing > 10000) { lastTypingPing = Date.now(); api("/api/typing", {}).catch(() => {}); }
});
$("#send").addEventListener("click", async () => { if (await send(input.value)) { input.value = ""; $("#bar").classList.remove("has-text"); } });
$("#mic").addEventListener("click", () => Ears.toggle());

const RATE = 16000, FRAME = 1024;
const LAUGH_WINDOW = 20000;
const Ears = {
  wanted: true,
  on: false, state: "idle", floor: 0.004, run: 0, quiet: 0, pre: [], clip: [], hearing: false,
  async start() {
    try {
      if (!micName) await refresh();
      this.stream = await MicPick.open(micName, { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true });
    } catch (e) { this.wanted = false; this.render(); return say("I can't hear you: the mic is blocked.", 5000); }
    if (MicPick.missing) say(`Your mic "${MicPick.missing}" isn't plugged in, so I'm using the default one.`, 6000);
    this.ctx = new AudioContext({ sampleRate: RATE });
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(FRAME, 1, 1);
    this.node.onaudioprocess = (e) => this.frame(new Float32Array(e.inputBuffer.getChannelData(0)));
    src.connect(this.node); this.node.connect(this.ctx.destination);
    this.on = true; this.reset(); this.render();
  },
  stop() {
    this.on = false; this.reset();
    try { this.node.disconnect(); this.stream.getTracks().forEach((t) => t.stop()); this.ctx.close(); } catch (e) {  }
    this.render();
  },
  toggle() { this.wanted = !this.wanted; if (this.wanted) this.start(); else this.stop(); },
  reset() { this.state = "idle"; this.run = 0; this.quiet = 0; this.pre = []; this.clip = []; },

  deaf() { return busy || Speaker.busy || Date.now() < quietUntil || this.hearing || document.activeElement === input && !!input.value; },
  frame(x) {
    let s = 0;
    for (let i = 0; i < x.length; i++) s += x[i] * x[i];
    const rms = Math.sqrt(s / x.length);
    if (this.deaf()) { if (this.state !== "idle") { this.reset(); this.render(); } return; }
    if (this.state === "idle") this.floor = rms < this.floor ? this.floor * 0.9 + rms * 0.1 : this.floor * 0.995 + rms * 0.005;
    const loud = rms > Math.max(0.012, this.floor * 3);
    if (this.state === "idle") {
      this.pre.push(x); if (this.pre.length > 6) this.pre.shift();
      this.run = loud ? this.run + 1 : 0;
      if (this.run >= 3) { this.state = "speech"; this.clip = this.pre.slice(); this.quiet = 0; this.lastLoud = performance.now(); this.render(); }
    } else {
      this.clip.push(x);
      if (loud) this.lastLoud = performance.now();
      this.quiet = loud ? 0 : this.quiet + 1;
      if (this.quiet >= 14 || this.clip.length * FRAME / RATE > 25) this.finish();
    }
  },
  async finish() {
    const clip = this.clip;
    this.reset();
    if (clip.length * FRAME / RATE - 0.9 < 0.35) { this.render(); return; }
    this.hearing = true; this.render();
    VoiceClock.start(this.lastLoud, "pet");
    try {
      const r = await api("/api/hear", { data: "data:audio/wav;base64," + wav(clip) });
      VoiceClock.mark("heard");
      const text = (r.text || "").trim();
      if (text.replace(/[^\p{L}\p{N}]/gu, "").length >= 2) await send(text, true, r.tone, r.sounds_like);

      else if (r.tone === "laughing" && Date.now() - Math.max(quietUntil, lastDone) < LAUGH_WINDOW) await send("(laughs)", true, "laughing", r.sounds_like);
      else VoiceClock.cancel();
    } catch (e) { VoiceClock.cancel();  }
    finally { this.hearing = false; this.render(); }
  },
  render() {
    const b = $("#mic");
    if (!b) return;
    const mode = !this.on ? "off" : this.state === "speech" || this.hearing ? "hearing" : this.deaf() ? "paused" : "listening";
    b.className = mode;
    b.title = { off: "Mic off. Click to have it listen.", listening: "Listening. Click to turn the mic off.",
      hearing: "Hearing you…", paused: "Its turn; listening again when it's done. Click to turn the mic off." }[mode];
  },
};
function wav(chunks) {
  const n = chunks.reduce((a, c) => a + c.length, 0);
  const buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); str(8, "WAVEfmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, RATE, true); v.setUint32(28, RATE * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, n * 2, true);
  let o = 44;
  for (const c of chunks) for (let i = 0; i < c.length; i++, o += 2) v.setInt16(o, Math.max(-1, Math.min(1, c[i])) * 0x7fff, true);
  let bin = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

const petBox = $("#pet");
let drag = null, moveFrame = 0;
petBox.addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;

  drag = { sx: e.screenX, sy: e.screenY, wx: e.screenX - e.clientX, wy: e.screenY - e.clientY, moved: false };
  petBox.setPointerCapture(e.pointerId);
});
petBox.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const dx = e.screenX - drag.sx, dy = e.screenY - drag.sy;
  if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
  drag.moved = true; petBox.classList.add("dragging");
  cancelAnimationFrame(moveFrame);
  moveFrame = requestAnimationFrame(() => window.aetherDesktop?.petMove(drag.wx + dx, drag.wy + dy));
});
const endDrag = () => {
  if (drag && !drag.moved) input.focus();
  drag = null; petBox.classList.remove("dragging");
};
petBox.addEventListener("pointerup", endDrag);
petBox.addEventListener("pointercancel", endDrag);
let lastScale = 0;
petBox.addEventListener("wheel", (e) => {
  e.preventDefault();
  if (Date.now() - lastScale < 60) return;
  lastScale = Date.now();
  window.aetherDesktop?.petScale(e.deltaY < 0 ? 1.07 : 1 / 1.07);
}, { passive: false });

document.addEventListener("contextmenu", (e) => { e.preventDefault(); window.aetherDesktop?.petMenu(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { hush(); api("/api/stop", {}).catch(() => {}); }
});

(async () => {
  api("/api/pet", { open: true }).catch(() => {});
  window.addEventListener("beforeunload", () => fetch("/api/pet", { method: "POST", keepalive: true,
    headers: { "X-Aether-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify({ open: false }) }));
  try {
    const a = await api("/api/avatar");
    if (a.info && a.info.kind === "orb") {
      avatar = (a.info.style === "logo" ? mountOrb : mountWireOrb)(petBox, { full: true, info: a.info });
    } else {
      if (!a.runtime) throw new Error("the Live2D runtime isn't installed (see the README)");
      if (!a.info) throw new Error("no avatar yet: add one in Settings");
      avatar = await mountAvatar(petBox, { full: true, info: a.info });
    }
  } catch (e) { say("My avatar didn't load: " + e.message, 20000); }
  await refresh();
  connect();
  setInterval(refresh, 30000);
  if (Ears.wanted) Ears.start();
})();
