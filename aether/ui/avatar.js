"use strict";

const Lip = {
  ctx: null, analyser: null, buf: null,

  ensure() {
    try {
      if (!this.ctx) {
        this.ctx = new AudioContext();
        this.analyser = this.ctx.createAnalyser();
        this.analyser.fftSize = 1024;
        this.buf = new Float32Array(this.analyser.fftSize);
        this.analyser.connect(this.ctx.destination);
      }
      if (this.ctx.state === "suspended") this.ctx.resume().catch(() => {});
      return this.ctx;
    } catch (e) { return null; }
  },

  attach(audio) {
    try { if (this.ensure()) this.ctx.createMediaElementSource(audio).connect(this.analyser); }
    catch (e) {  }
  },
  level() {
    if (!this.analyser) return 0;
    this.analyser.getFloatTimeDomainData(this.buf);
    let s = 0;
    for (let i = 0; i < this.buf.length; i++) s += this.buf[i] * this.buf[i];
    return Math.min(1, Math.sqrt(s / this.buf.length) * 7);
  },
};

const Speaker = {
  LEAD: 0.5, queue: [], job: null, until: 0, sources: [], talking: false, timer: 0, quietTimer: 0,
  src: (id) => id, onState: null,
  add(ev) { this.queue.push(ev); this._state(true); if (!this.job) this.next(); },
  next() {
    const ev = this.job = this.queue.shift() || null;
    if (!ev) return this._whenDone();
    if (ev.stream) return this._stream(ev);

    this.timer = setTimeout(() => {
      if (this.job !== ev) return;
      const a = ev.el = new Audio(this.src(ev.id));
      Lip.attach(a);
      a.onplaying = () => VoiceClock.finish(performance.now());
      a.onended = a.onerror = () => { if (this.job === ev) this.next(); };
      a.play().catch(() => { if (this.job === ev) this.next(); });
    }, this._left() * 1000);
  },
  async _stream(ev) {
    const ctx = Lip.ensure();
    if (!ctx) return this.next();
    const ctl = ev.ctl = new AbortController();
    let carry = null, first = true;
    try {
      const r = await fetch(this.src(ev.id), { signal: ctl.signal });
      if (!r.ok || !r.body) throw new Error(String(r.status));
      const reader = r.body.getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done || this.job !== ev) break;
        let b = value;
        if (carry) { const j = new Uint8Array(carry.length + b.length); j.set(carry); j.set(b, carry.length); b = j; carry = null; }
        if (b.length % 2) { carry = b.slice(b.length - 1); b = b.subarray(0, b.length - 1); }
        const n = b.length >> 1;
        if (!n) continue;
        const buf = ctx.createBuffer(1, n, ev.rate || 24000), ch = buf.getChannelData(0);
        const dv = new DataView(b.buffer, b.byteOffset, b.length);
        for (let i = 0; i < n; i++) ch[i] = dv.getInt16(i * 2, true) / 32768;
        const s = ctx.createBufferSource();
        s.buffer = buf;
        s.connect(Lip.analyser);

        const idle = this.until <= ctx.currentTime;
        const at = first ? Math.max(this.until, ctx.currentTime + this.LEAD) : idle ? ctx.currentTime + 0.03 : this.until;
        if (first) VoiceClock.finish(performance.now() + (at - ctx.currentTime) * 1000);
        first = false;
        s.start(at);
        this.until = at + buf.duration;
        this.sources.push(s);
        s.onended = () => { this.sources = this.sources.filter((x) => x !== s); };
      }
    } catch (e) {  }
    if (this.job === ev) this.next();
  },
  _left() { return Lip.ctx ? Math.max(0, this.until - Lip.ctx.currentTime) : 0; },
  _whenDone() {
    clearTimeout(this.quietTimer);
    this.quietTimer = setTimeout(() => { if (!this.job && !this.queue.length) this._state(false); }, this._left() * 1000 + 60);
  },
  _state(on) { if (this.talking !== on) { this.talking = on; if (this.onState) this.onState(on); } },
  clear() {
    const ev = this.job;
    this.queue = []; this.job = null;
    clearTimeout(this.timer); clearTimeout(this.quietTimer);
    if (ev && ev.ctl) ev.ctl.abort();
    if (ev && ev.el) ev.el.pause();
    this.sources.forEach((s) => { try { s.stop(); } catch (e) {  } });
    this.sources = []; this.until = 0;
    this._state(false);
  },
  get busy() { return this.talking; },
};

const VoiceClock = {
  t: null, post: null, timer: 0,
  start(spokeEnd, where) {
    const now = performance.now();
    clearTimeout(this.timer);
    this.t = { where, end: Math.min(spokeEnd || now, now), sent: now };
  },
  mark(k, chat) {
    if (!this.t || this.t[k] != null) return;
    if (k === "words" && this.t.heard == null) return;
    this.t[k] = performance.now();
    if (chat) this.t.chat = chat;
  },
  cancel() { this.t = null; clearTimeout(this.timer); },
  done() {
    if (this.t && this.t.words != null) this.timer = setTimeout(() => this.finish(null), 20000);
  },
  finish(soundAt) {
    const t = this.t;
    if (!t || t.words == null) return;
    this.cancel();
    const s = (a, b) => (a == null || b == null ? null : Math.max(0, (b - a) / 1000));
    const body = { where: t.where, chat: t.chat || "", quiet: s(t.end, t.sent), hear: s(t.sent, t.heard),
                   words: s(t.heard, t.words), sound: s(t.words, soundAt) };
    if (this.post) this.post(body).catch(() => {});
  },
};

function mountOrb(box, opts = {}) {
  const cv = document.createElement("canvas");
  cv.className = "l2d";
  cv.style.cssText = "width:100%;height:100%;display:block";
  box.appendChild(cv);
  const ctx = cv.getContext("2d");
  const off = document.createElement("canvas"), octx = off.getContext("2d");
  const logo = new Image(); logo.src = "/ui/orb.png";
  let W = 0, H = 0, S = 1;
  const size = () => {
    S = Math.min(2, window.devicePixelRatio || 1);
    W = box.clientWidth; H = box.clientHeight;
    cv.width = off.width = Math.max(1, W * S); cv.height = off.height = Math.max(1, H * S);
  };
  size();
  const ro = new ResizeObserver(size); ro.observe(box);
  const framing = Object.assign({ zoom: 1, y: 0 }, (opts.info && opts.info.framing) || {});
  const rand = (a, b) => a + Math.random() * (b - a);
  const newMote = (anywhere) => ({ a: rand(0, Math.PI * 2), r: anywhere ? rand(0.75, 1.7) : rand(1.4, 1.8),
    speed: rand(0.08, 0.3) * (Math.random() < 0.5 ? -1 : 1), drift: rand(0.02, 0.09), size: rand(0.6, 2.2),
    hue: Math.random() < 0.7 ? 230 : 280, life: rand(0, 1) });
  const motes = Array.from({ length: 26 }, () => newMote(true));
  const rings = [];
  const look = { x: 0, y: 0, tx: 0, ty: 0, next: 2 };
  let level = 0, lastPeak = 0, glitchUntil = 0, nextGlitch = 3, slices = [], prev = 0, raf = 0, alive = true;

  function backdrop(y = 0, h = H * S) {
    if (opts.full) { ctx.clearRect(0, y, W * S, h); return; }
    const bg = ctx.createRadialGradient(W * S / 2, H * S * 0.42, 0, W * S / 2, H * S * 0.42, Math.max(W, H) * S * 0.75);
    bg.addColorStop(0, "#15153a"); bg.addColorStop(1, "#06070f");
    ctx.fillStyle = bg; ctx.fillRect(0, y, W * S, h);
  }

  function scene(c, t, lv) {
    c.clearRect(0, 0, W * S, H * S);
    if (t > look.next) { look.tx = rand(-0.05, 0.05); look.ty = rand(-0.03, 0.03); look.next = t + rand(2.5, 6); }
    look.x += (look.tx - look.x) * 0.04; look.y += (look.ty - look.y) * 0.04;
    const cy0 = opts.full ? 0.5 : 0.45;
    const cx = (W / 2 + look.x * W) * S;
    const cy = (H * (cy0 + framing.y * 0.3) + Math.sin(t * 0.9) * H * 0.018 + look.y * H) * S;
    const R = Math.min(W, H) * (opts.full ? 0.4 : 0.34) * framing.zoom * S * (1 + Math.sin(t * 1.2) * 0.018) * (1 + lv * 0.14);
    const tilt = Math.sin(t * 0.5) * 0.06 + look.x * 1.5;
    const aura = c.createRadialGradient(cx, cy, R * 0.5, cx, cy, R * (1.9 + lv * 0.7));
    aura.addColorStop(0, `rgba(105,80,255,${0.28 + lv * 0.4})`);
    aura.addColorStop(0.55, `rgba(40,120,255,${0.10 + lv * 0.15})`);
    aura.addColorStop(1, "rgba(20,30,120,0)");
    c.fillStyle = aura; c.beginPath(); c.arc(cx, cy, R * 2.6, 0, Math.PI * 2); c.fill();
    if (lv > 0.55 && t - lastPeak > 0.18) { rings.push({ born: t, strength: lv }); lastPeak = t; }
    for (let i = rings.length - 1; i >= 0; i--) {
      const k = (t - rings[i].born) / 1.2;
      if (k >= 1) { rings.splice(i, 1); continue; }
      c.strokeStyle = `rgba(150,170,255,${(1 - k) * 0.5 * rings[i].strength})`;
      c.lineWidth = (2.5 - k * 2) * S;
      c.beginPath(); c.arc(cx, cy, R * (1.02 + k * 0.9), 0, Math.PI * 2); c.stroke();
    }
    const drawMotes = (front) => {
      for (const m of motes) {
        const z = Math.sin(m.a);
        if ((z > 0) !== front) continue;
        const x = cx + Math.cos(m.a) * R * m.r, y = cy + z * R * m.r * 0.35 - R * 0.05;
        const a = (0.25 + 0.6 * (z * 0.5 + 0.5)) * (0.4 + 0.6 * Math.sin(m.life * Math.PI)) * (1 + lv * 0.6);
        c.fillStyle = `hsla(${m.hue},95%,${70 + lv * 15}%,${Math.min(1, a)})`;
        c.beginPath(); c.arc(x, y, m.size * S * (front ? 1.2 : 0.8), 0, Math.PI * 2); c.fill();
      }
    };
    drawMotes(false);
    if (logo.complete && logo.naturalWidth) {
      c.save(); c.translate(cx, cy); c.rotate(tilt);
      c.shadowColor = `rgba(110,100,255,${0.6 + lv * 0.3})`; c.shadowBlur = (16 + lv * 22) * S;
      c.drawImage(logo, -R, -R, R * 2, R * 2);
      c.restore();
      c.save(); c.beginPath(); c.arc(cx, cy, R * 0.97, 0, Math.PI * 2); c.clip();
      c.globalCompositeOperation = "screen";
      const sx = cx + Math.sin(t * 0.35) * R * 0.7, sy = cy + Math.cos(t * 0.27) * R * 0.5 - R * 0.2;
      const sheen = c.createRadialGradient(sx, sy, 0, sx, sy, R * 0.6);
      sheen.addColorStop(0, `rgba(190,220,255,${0.2 + lv * 0.15})`); sheen.addColorStop(1, "rgba(190,220,255,0)");
      c.fillStyle = sheen; c.fillRect(cx - R, cy - R, R * 2, R * 2);
      if (lv > 0.05) {
        const core = c.createRadialGradient(cx, cy, 0, cx, cy, R * 0.8);
        core.addColorStop(0, `rgba(160,200,255,${lv * 0.28})`); core.addColorStop(1, "rgba(160,200,255,0)");
        c.fillStyle = core; c.fillRect(cx - R, cy - R, R * 2, R * 2);
      }
      c.restore();
    }
    drawMotes(true);
  }

  function frame(ms) {
    if (!alive) return;
    const t = ms / 1000, dt = Math.min(0.05, t - prev || 0.016); prev = t;
    level += (Lip.level() - level) * 0.35;
    const talking = level > 0.05;
    for (const m of motes) {
      m.a += m.speed * dt * (1 + level * 2);
      m.r -= m.drift * dt * (talking ? -0.8 : 1);
      m.life += dt * 0.25;
      if (m.r < 0.9 || m.r > 1.9 || m.life > 1) Object.assign(m, newMote(false), { r: talking ? 1.0 : rand(1.4, 1.8) });
    }
    scene(octx, t, level);
    backdrop();
    if (!talking && t > nextGlitch) {
      glitchUntil = t + rand(0.1, 0.32); nextGlitch = t + rand(3, 7);
      slices = Array.from({ length: 3 + (Math.random() * 4 | 0) }, () => ({ y: Math.random(), h: rand(0.01, 0.07), dx: rand(-0.09, 0.09) }));
    }
    if (t < glitchUntil) {
      const split = rand(4, 10) * S;
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = 0.8; ctx.drawImage(off, -split, 0);
      ctx.filter = "hue-rotate(150deg)"; ctx.drawImage(off, split, 0); ctx.filter = "none";
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
      for (const sl of slices) {
        const y = sl.y * H * S, h = sl.h * H * S;
        backdrop(y, h);
        ctx.drawImage(off, 0, y, W * S, h, sl.dx * W * S, y, W * S, h);
      }
      for (let i = 0; i < 6; i++) {
        ctx.fillStyle = ["#22d3ee", "#ff3ea5", "#8b5cf6"][i % 3];
        ctx.fillRect(Math.random() * W * S, Math.random() * H * S, rand(6, 28) * S, rand(2, 5) * S);
      }
    } else {
      ctx.drawImage(off, 0, 0);
      if (level > 0.25) {
        ctx.globalAlpha = (level - 0.25) * 0.35; ctx.globalCompositeOperation = "screen";
        ctx.filter = "hue-rotate(150deg)"; ctx.drawImage(off, level * 4 * S, 0); ctx.filter = "none";
        ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
      }
    }
    if (!opts.full) {
      ctx.fillStyle = "rgba(0,0,0,0.10)";
      for (let y = 0; y < H * S; y += 4 * S) ctx.fillRect(0, y, W * S, S);
    }
    raf = requestAnimationFrame(frame);
  }
  raf = requestAnimationFrame(frame);
  return {
    setMood() {  },
    setFraming(zoom, y) { framing.zoom = zoom; framing.y = y; },
    glitch() { nextGlitch = 0; },
    destroy() { alive = false; cancelAnimationFrame(raf); ro.disconnect(); cv.remove(); },
  };
}

function mountWireOrb(box, opts = {}) {
  const cv = document.createElement("canvas");
  cv.className = "l2d";
  cv.style.cssText = "width:100%;height:100%;display:block";
  box.appendChild(cv);
  const ctx = cv.getContext("2d");
  const glow = document.createElement("canvas"), gctx = glow.getContext("2d");
  let W = 0, H = 0, S = 1;
  const size = () => {
    S = Math.min(2, window.devicePixelRatio || 1);
    W = box.clientWidth; H = box.clientHeight;
    cv.width = Math.max(1, W * S); cv.height = Math.max(1, H * S);
    glow.width = Math.max(1, cv.width / 4 | 0); glow.height = Math.max(1, cv.height / 4 | 0);
  };
  size();
  const ro = new ResizeObserver(size); ro.observe(box);
  const NI = 96, NJ = 48, P = new Float32Array(NI * (NJ + 1) * 3);
  const rand = (a, b) => a + Math.random() * (b - a);
  const motes = Array.from({ length: 50 }, () => ({ i: rand(0, NI) | 0, j: rand(1, NJ - 1) | 0, life: Math.random(), dx: 0, dy: 0 }));
  const at = (i, j) => (((i + NI) % NI) * (NJ + 1) + j) * 3;
  let level = 0, energy = 0, phase = 0, glitchUntil = 0, nextGlitch = 4, prev = 0, raf = 0, alive = true;

  function radius(x, y, z, t, e) {
    return 1 + 0.13 * Math.sin(2.1 * x + 1.3 * t) * Math.cos(1.7 * y - 0.9 * t)
      + 0.09 * Math.sin(3.3 * y + 2.2 * z + 1.7 * t) + 0.06 * Math.sin(4.7 * z - 3.1 * x - 2.3 * t)
      + 0.05 * Math.sin(6 * (x + y) + 2.9 * t)
      + e * (0.22 * Math.sin(10 * z - phase * 8) * Math.max(0, z + 0.4) + 0.08 * Math.sin(7 * x + 9 * y - phase * 10));
  }
  function project(t) {
    const ay = t * 0.35, ax = 0.35 * Math.sin(t * 0.27), tw = 0.6 * Math.sin(t * 0.4);
    const cy = Math.cos(ay), sy = Math.sin(ay), cx = Math.cos(ax), sx = Math.sin(ax);
    const R = Math.min(W, H) * (opts.full ? 0.36 : 0.3) * S * (1 + energy * 0.08);
    const ox = W * S / 2, oy = H * S * (opts.full ? 0.5 : 0.45);
    let k = 0;
    for (let i = 0; i < NI; i++) {
      const lon = (i / NI) * Math.PI * 2;
      for (let j = 0; j <= NJ; j++) {
        const lat = (j / NJ) * Math.PI - Math.PI / 2, l2 = lon + tw * Math.sin(lat * 2);
        let x = Math.cos(lat) * Math.cos(l2), y = Math.sin(lat), z = Math.cos(lat) * Math.sin(l2);
        const r = radius(x, y, z, t, energy);
        x *= r; y *= r; z *= r;
        const x1 = x * cy + z * sy, z1 = -x * sy + z * cy, y2 = y * cx - z1 * sx, z2 = y * sx + z1 * cx;
        const persp = 3 / (3 + z2);
        P[k++] = ox + x1 * R * persp; P[k++] = oy - y2 * R * persp; P[k++] = z2;
      }
    }
  }
  function draw() {
    ctx.globalCompositeOperation = "source-over";
    if (opts.full) ctx.clearRect(0, 0, W * S, H * S);
    else { ctx.fillStyle = "rgba(4,5,15,0.6)"; ctx.fillRect(0, 0, W * S, H * S); }
    ctx.globalCompositeOperation = "lighter";
    const B = 6, paths = Array.from({ length: B }, () => new Path2D());
    const seg = (a, b) => {
      const depth = 1 - ((P[a + 2] + P[b + 2]) / 2 + 1.4) / 2.8;
      const p = paths[Math.max(0, Math.min(B - 1, depth * B | 0))];
      p.moveTo(P[a], P[a + 1]); p.lineTo(P[b], P[b + 1]);
    };
    for (let j = 1; j < NJ; j++) for (let i = 0; i < NI; i++) seg(at(i, j), at(i + 1, j));
    for (let i = 0; i < NI; i += 2) for (let j = 0; j < NJ; j++) seg(at(i, j), at(i, j + 1));
    ctx.lineWidth = 0.8 * S;
    const base = 0.14 + energy * 0.14;
    for (let k = 0; k < B; k++) {
      const d = (k + 0.5) / B;
      ctx.strokeStyle = `rgba(${100 + d * 80},${150 + d * 70},255,${base * (0.25 + d * 1.15)})`;
      ctx.stroke(paths[k]);
    }
    for (const m of motes) {
      m.life += 0.008 + energy * 0.02;
      if (m.life > 1) { m.life = 0; m.i = rand(0, NI) | 0; m.j = rand(1, NJ - 1) | 0; m.dx = rand(-20, 20) * S; m.dy = rand(-20, 20) * S; }
      const k = at(m.i, m.j);
      if (P[k + 2] > 0.3) continue;
      ctx.fillStyle = `rgba(215,232,255,${0.6 * Math.sin(m.life * Math.PI) + energy * 0.3})`;
      ctx.beginPath(); ctx.arc(P[k] + m.dx * m.life, P[k + 1] + m.dy * m.life, (1.1 + energy * 1.6) * S, 0, Math.PI * 2); ctx.fill();
    }
    gctx.clearRect(0, 0, glow.width, glow.height);
    gctx.filter = "blur(3px)"; gctx.drawImage(cv, 0, 0, glow.width, glow.height); gctx.filter = "none";
    ctx.globalAlpha = 0.6 + energy * 0.35; ctx.drawImage(glow, 0, 0, W * S, H * S); ctx.globalAlpha = 1;
  }
  function frame(ms) {
    if (!alive) return;
    const t = ms / 1000, dt = Math.min(0.05, t - prev || 0.016); prev = t;
    level += (Lip.level() - level) * 0.3;
    energy += (level - energy) * 0.15;
    phase += dt * (0.6 + energy * 3);
    project(t);
    draw();
    if (energy < 0.05 && t > nextGlitch) { glitchUntil = t + rand(0.12, 0.32); nextGlitch = t + rand(4, 9); }
    if (t < glitchUntil) {
      ctx.globalCompositeOperation = "source-over";
      for (let n = 0; n < 5; n++) {
        const y = Math.random() * H * S, h = rand(4, 24) * S;
        ctx.drawImage(cv, 0, y, W * S, h, rand(-0.12, 0.12) * W * S, y, W * S, h);
      }
      ctx.globalCompositeOperation = "lighter"; ctx.globalAlpha = 0.25; ctx.filter = "hue-rotate(160deg)";
      ctx.drawImage(cv, 5 * S, 0); ctx.filter = "none"; ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
    }
    raf = requestAnimationFrame(frame);
  }
  raf = requestAnimationFrame(frame);
  return {
    setMood() {  },
    setFraming() {  },
    glitch() { nextGlitch = 0; },
    destroy() { alive = false; cancelAnimationFrame(raf); ro.disconnect(); cv.remove(); },
  };
}

let live2dLoading = null;
function loadLive2D() {
  if (window.PIXI && PIXI.live2d) return Promise.resolve();
  const one = (src) => new Promise((ok, bad) => {
    const s = document.createElement("script");
    s.src = src; s.onload = ok; s.onerror = () => bad(new Error("couldn't load " + src));
    document.head.appendChild(s);
  });
  live2dLoading = live2dLoading || one("/vendor/live2dcubismcore.min.js").then(() => one("/vendor/pixi.min.js"))
    .then(() => one("/vendor/cubism4.min.js")).catch((e) => { live2dLoading = null; throw e; });
  return live2dLoading;
}

async function mountAvatar(box, opts = {}) {
  await loadLive2D();
  if (!window.PIXI || !PIXI.live2d) throw new Error("Live2D renderer didn't load");
  const canvas = document.createElement("canvas");
  canvas.className = "l2d";
  box.appendChild(canvas);
  const info = opts.info || {};
  if (!info.file) { canvas.remove(); throw new Error("no avatar model"); }
  const app = new PIXI.Application({ view: canvas, autoStart: true, backgroundAlpha: 0, resizeTo: box, antialias: true });
  let model;
  try {
    model = await PIXI.live2d.Live2DModel.from("/live2d/" + encodeURIComponent(info.file), { autoInteract: false });
  } catch (e) { app.destroy(true, { children: true }); throw e; }
  app.stage.addChild(model);
  const core = model.internalModel.coreModel;
  const baseW = model.width, baseH = model.height;
  const framing = Object.assign({ zoom: 1, y: 0 }, info.framing || {});
  const mouthParam = info.mouth || "ParamMouthOpenY";
  const moods = info.moods || {};

  function frame() {
    const W = box.clientWidth, H = box.clientHeight;
    if (!W || !H) return;
    if (opts.full) {
      const s = Math.min(H * 0.98 / baseH, W * 0.98 / baseW);
      model.scale.set(s); model.anchor.set(0.5, 1); model.position.set(W / 2, H);
    } else {
      const s = Math.max(W * 2.3 / baseW, H * 3.8 / baseH) * framing.zoom;
      model.scale.set(s); model.anchor.set(0.5, 0); model.position.set(W / 2, -H * 0.16 + framing.y * H);
    }
  }
  frame();
  const ro = new ResizeObserver(frame); ro.observe(box);

  let mouth = 0, t = 0;
  app.ticker.add((dt) => {
    t += dt / 60;
    const target = Lip.level();
    mouth += (target - mouth) * 0.5;
    try {
      core.setParameterValueById(mouthParam, mouth);
      core.setParameterValueById("ParamBodyAngleX", Math.sin(t * 0.8) * 3);
    } catch (e) {  }
  });

  let face;
  return {
    setMood(name) {
      const e = moods[name] || null;
      if (e === face) return;
      face = e;
      try {
        if (e) model.expression(e);
        else model.internalModel.motionManager.expressionManager?.resetExpression();
      } catch (err) {  }
    },
    setFraming(zoom, y) { framing.zoom = zoom; framing.y = y; frame(); },
    destroy() { ro.disconnect(); app.destroy(true, { children: true }); },
  };
}
