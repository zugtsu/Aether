"use strict";

const TOKEN = document.querySelector('meta[name="aether-token"]').content;
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, body) {
  const opt = { headers: { "X-Aether-Token": TOKEN } };
  if (body !== undefined) {
    opt.method = "POST";
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function toast(msg, bad) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (bad ? " bad" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.className = ""), bad ? 5000 : 2600);
}

const P = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';
const ICONS = {
  chat: `<path d="M4 5h16v11H10l-5 4v-4H4z" ${P}/>`,

  brain: `<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" ${P}/>` +
    `<path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" ${P}/>` +
    `<path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4M17.599 6.5a3 3 0 0 0 .399-1.375M6.003 5.125A3 3 0 0 0 6.401 6.5` +
    `M3.477 10.896a4 4 0 0 1 .585-.396M19.938 10.5a4 4 0 0 1 .585.396M6 18a4 4 0 0 1-1.967-.516M19.967 17.484A4 4 0 0 1 18 18" ${P}/>`,
  person: `<circle cx="12" cy="8" r="3.6" ${P}/><path d="M5 20c1.4-4 12.6-4 14 0" ${P}/>`,
  folder: `<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.2h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" ${P}/>`,
  moon: `<path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.3 6.3 0 0 0 10 10z" ${P}/>`,
  image: `<rect x="3.5" y="4.5" width="17" height="15" rx="2.2" ${P}/><circle cx="9" cy="10" r="1.7" ${P}/><path d="M4.5 18l5-5 3.5 3.5 2.5-2.5 4 4" ${P}/>`,
  clock: `<circle cx="12" cy="12" r="8" ${P}/><path d="M12 8v4.2l3 1.8" ${P}/>`,

  shieldcheck: `<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" ${P}/><path d="m9 12 2 2 4-4" ${P}/>`,

  bookopen: `<path d="M12 5v16" ${P}/><path d="M20.001 19A2 2 0 0022 17V5a2 2 0 00-1.999-2L16 3.002A5 5 0 0012 5a5 5 0 00-4-2H4a2 2 0 00-2 2v12a2 2 0 001.999 2H8a5 5 0 014 2 5 5 0 014-2z" ${P}/>`,

  lock: `<rect width="18" height="11" x="3" y="11" rx="2" ry="2" ${P}/><path d="M7 11V7a5 5 0 0 1 10 0v4" ${P}/>`,

  cpu: `<path d="M12 20v2" ${P}/><path d="M12 2v2" ${P}/><path d="M17 20v2" ${P}/><path d="M17 2v2" ${P}/><path d="M2 12h2" ${P}/><path d="M2 17h2" ${P}/><path d="M2 7h2" ${P}/><path d="M20 12h2" ${P}/><path d="M20 17h2" ${P}/><path d="M20 7h2" ${P}/><path d="M7 20v2" ${P}/><path d="M7 2v2" ${P}/><rect x="4" y="4" width="16" height="16" rx="2" ${P}/><rect x="8" y="8" width="8" height="8" rx="1" ${P}/>`,

  calendar: `<rect x="3" y="4" width="18" height="18" rx="2" ${P}/><path d="M16 2v4M8 2v4M3 10h18" ${P}/>`,
  alarm: `<circle cx="12" cy="13" r="8" ${P}/><path d="M12 9v4l2 2" ${P}/><path d="M5 3 2 6" ${P}/><path d="m22 6-3-3" ${P}/><path d="M6.38 18.7 4 21" ${P}/><path d="M17.64 18.67 20 21" ${P}/>`,

  bell: `<path d="M10.268 21a2 2 0 0 0 3.464 0" ${P}/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326" ${P}/>`,

  moonstar: `<path d="M18 5h4" ${P}/><path d="M20 3v4" ${P}/><path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401" ${P}/>`,

  activity: `<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2" ${P}/>`,

  terminal: `<path d="M12 19h8" ${P}/><path d="m4 17 6-6-6-6" ${P}/>`,

  heartpulse: `<path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5" ${P}/>` +
    `<path d="M3.22 13H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27" ${P}/>`,
  link: `<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1" ${P}/>`,
  skills: `<path d="M4 7h9M18 7h2M4 17h3M12 17h8" ${P}/><circle cx="15.5" cy="7" r="2.2" ${P}/><circle cx="9.5" cy="17" r="2.2" ${P}/>`,
  gear: `<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" ${P}/><circle cx="12" cy="12" r="3" ${P}/>`,
  plus: `<path d="M12 5v14M5 12h14" ${P} stroke-width="2.2"/>`,
  pin: `<path d="M9 4h6l-1 5 3 3H7l3-3-1-5zM12 12v8" ${P}/>`,
  archive: `<rect width="20" height="5" x="2" y="3" rx="1" ${P}/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8M10 12h4" ${P}/>`,
  search: `<circle cx="10.5" cy="10.5" r="6" ${P}/><path d="M15 15l5 5" ${P}/>`,
  mic: `<rect x="9" y="3.5" width="6" height="11" rx="3" ${P}/><path d="M6 11.5a6 6 0 0 0 12 0M12 17.5v3" ${P}/>`,
  discord: `<path d="M7 6.3c1.7-.8 3.3-1.1 5-1.1s3.3.3 5 1.1c1.7 2.5 2.6 5.3 2.5 8.4-1.6 1.2-3.3 2-5 2.4l-1-1.6c-.5.1-1 .1-1.5.1s-1 0-1.5-.1l-1 1.6c-1.7-.4-3.4-1.2-5-2.4-.1-3.1.8-5.9 2.5-8.4z" fill="#5865F2"/><circle cx="9.6" cy="11.8" r="1.35" fill="#0b0d1a"/><circle cx="14.4" cy="11.8" r="1.35" fill="#0b0d1a"/>`,
};
const icon = (name, color) => `<span class="ico"${color ? ` style="color:${color}"` : ""}><svg viewBox="0 0 24 24">${ICONS[name] || ""}</svg></span>`;
function fillIcons(root = document) {
  $$("[data-icon]", root).forEach((el) => { el.innerHTML = `<svg viewBox="0 0 24 24">${ICONS[el.dataset.icon] || ""}</svg>`; });
}

const parseTs = (ts) => new Date(ts);
const clock = (ts) => parseTs(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
function ago(ts) {
  const m = (Date.now() - parseTs(ts)) / 60000;
  if (m < 2) return "now";
  if (m < 60) return `${Math.round(m)} min`;
  if (m < 60 * 24) return `${Math.round(m / 60)} h`;
  const d = Math.round(m / 1440);
  return d === 1 ? "1 day" : `${d} days`;
}

const S = {
  state: null,
  view: "chat",
  chat: null,
  busy: false,
  status: "",
  steps: 0,
  attach: [],
  showAll: false,
  recentOpen: true,
  archiveOpen: false,
  unfolded: new Set(),
  skills: null,
  work: null,
};
const picUrl = () => `/api/picture?t=${TOKEN}&v=${S.state?.agent?.picture_v || 0}`;
const name = () => S.state?.agent?.name || "Companion";
const userName = () => S.state?.settings?.user_name || "User";

const author = (a) => (a === "user" ? "you" : a);

function connect() {
  const es = new EventSource(`/api/events?t=${encodeURIComponent(TOKEN)}`);
  es.onmessage = (e) => { try { onEvent(JSON.parse(e.data)); } catch (err) { console.error(err); } };
}

function onEvent(ev) {
  const here = S.chat && ev.chat === S.chat.id;
  switch (ev.type) {
    case "user":
      S.busy = true; S.steps = 0; S.status = "thinking";
      workStart(ev.chat);
      if (here) { S.chat.events.push({ kind: "user", text: ev.text, images: ev.images, voice: ev.voice, tone: ev.tone, ts: new Date().toISOString(), place: "Aether app" }); if (S.view !== "chat") showView("chat"); else renderMessages(); }
      else renderWork();
      renderBusy();
      break;
    case "status":
      S.status = ev.text;
      if (ev.text !== "idle") {
        if (!S.work || S.work.chat !== ev.chat) workStart(ev.chat);
        S.work.status = ev.text;
        if (ev.text !== "stopped") S.busy = true;
      }
      renderBusy(); if (here) renderLive(); else renderWork(); break;
    case "step":
      S.steps += 1;
      if (!S.work || S.work.chat !== ev.chat) workStart(ev.chat);
      S.work.steps.push({ step: ev.step, res: null });
      if (here) { S.chat.events.push({ kind: "step", step: ev.step, live: true }); renderMessages(); } else renderWork();
      renderBusy(); break;
    case "result":
      { const w = S.work?.steps.findLast((s) => !s.res); if (w) w.res = { ok: ev.ok, text: ev.text }; }
      if (!here) renderWork();
      if (here) { S.chat.events.push({ kind: "result", ok: ev.ok, text: ev.text, of: ev.step?.step }); renderMessages(); }
      break;
    case "say":
      VoiceClock.mark("words", ev.chat);
      if (here) {
        let last = S.chat.events[S.chat.events.length - 1];
        if (!last || last.kind !== "reply" || !last.live) { last = { kind: "reply", text: "", live: true, ts: new Date().toISOString() }; S.chat.events.push(last); }
        last.text += ev.text;
        renderLive(last);
      }
      break;
    case "ask":
      if (here) { S.chat.events.push({ kind: "ask", qid: ev.qid, question: ev.question }); renderMessages(); }
      else toast(`${name()} is asking for permission in another chat`);
      break;
    case "asked": {
      const a = S.chat?.events.find((e) => e.kind === "ask" && e.qid === ev.qid);
      if (a) { a.answered = ev.allow ? "allowed" : "not allowed"; renderMessages(); }
      break;
    }
    case "reach_out":
      if (here) { S.chat.events.push({ kind: "reach_out", text: ev.text, ts: new Date().toISOString() }); renderMessages(); }
      notify(`${name()}`, ev.text);
      Attention.add();
      refreshState();
      break;
    case "wake":
      if (here) toast(`⏰ ${ev.text}`);
      break;
    case "proposal":
      if (here) openChat(S.chat.id, true);
      notify(name(), `has an idea for you: ${ev.title}`);
      Attention.add();
      refreshState();
      break;
    case "proposal_answer":
      if (here) openChat(S.chat.id, true);
      refreshState();
      if (S.view === "heartbeat") showView("heartbeat");
      break;
    case "life": case "mood":
      refreshState();
      if (S.view === "heartbeat" || S.view === "dreams") showView(S.view);
      break;
    case "brain":
      updateBrainBar();
      if (S.view === "settings") refreshBrain();
      if (ev.phase === "done") toast(`${name()}'s brain is now ${ev.to}`);
      if (ev.phase === "failed") toast(ev.error, true);
      break;
    case "stopped":
      S.status = "stopped"; if (S.work) S.work.status = "stopped"; renderBusy(); renderWork(); break;
    case "done": case "error":
      if (ev.type === "error") VoiceClock.cancel(); else VoiceClock.done();
      S.busy = false; S.status = ""; S.work = null; renderWork();
      if (ev.type === "error") toast(ev.text, true);

      if (ev.type === "done" && ev.text && ev.chat !== "heartbeat" && !String(ev.chat).startsWith("discord-")) Attention.add();
      if (here) openChat(S.chat.id, true); else refreshState();
      renderBusy();
      break;
    case "compacted":
      S.busy = false; S.status = ""; S.work = null; renderWork(); renderBusy();
      toast(`Compacted: ${name()} carries on from its own note (open it at the divider)`);
      if (here) openChat(S.chat.id, true); else refreshState();
      break;
    case "audio":
      if (!ev.pet) Player.add(ev);
      break;
    case "audio_stop":
      Player.clear();
      break;
    case "term":
      Term.add(ev.who, ev.kind, ev.text);
      if (ev.who === "her" && ev.kind === "cmd" && !Term.open) toast(`${name()} is running a command (the >_ button up top to watch)`);
      break;
    case "made_image":
      if (here) { S.chat.events.push({ kind: "made_image", images: ev.images, caption: ev.caption, title: ev.title, ts: new Date().toISOString() }); renderMessages(); }
      notify(name(), `made you a picture${ev.caption ? ": " + ev.caption : ""}`);
      if (S.view === "images") renderImages();
      Attention.add();
      refreshState();
      break;
    case "made_song":
      if (here) { S.chat.events.push({ kind: "made_song", audio: ev.audio, caption: ev.caption, title: ev.title, style: ev.style, ts: new Date().toISOString() }); renderMessages(); }
      notify(name(), `made you a song${ev.title ? ": " + ev.title : ""}`);
      if (S.view === "images") renderImages();
      Attention.add();
      refreshState();
      break;
    case "made_video":
      if (here) { S.chat.events.push({ kind: "made_video", video: ev.video, images: ev.images, caption: ev.caption, title: ev.title, ts: new Date().toISOString() }); renderMessages(); }
      notify(name(), `made you a video${ev.caption ? ": " + ev.caption : ""}`);
      if (S.view === "images") renderImages();
      Attention.add();
      refreshState();
      break;
    case "note":
      toast(ev.text, true);
      break;
    case "audio_error":
      toast(ev.text, true);
      break;
  }
}

const Player = Speaker;
Speaker.src = (id) => `/api/audio?t=${TOKEN}&id=${encodeURIComponent(id)}`;
Speaker.onState = (on) => setSpeaking(on);
VoiceClock.post = (body) => api("/api/voice/timing", body);

const Attention = {
  n: 0,
  add() { if (!document.hasFocus()) { this.n += 1; this.show(); } },
  clear() { if (this.n) { this.n = 0; this.show(); } },
  title() { return (this.n ? `(${this.n}) ` : "") + `Aether · ${name()}`; },
  show() {
    document.title = this.title();
    try { window.aetherDesktop?.attention(this.n, this.n ? this.badge() : ""); } catch (e) {  }
  },
  badge() {
    const c = document.createElement("canvas");
    c.width = c.height = 32;
    const g = c.getContext("2d");
    g.fillStyle = "#e5484d";
    g.beginPath(); g.arc(16, 16, 15, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#fff"; g.font = "bold 20px Segoe UI, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(this.n > 9 ? "9+" : String(this.n), 16, 17);
    return c.toDataURL("image/png");
  },
};
window.addEventListener("focus", () => Attention.clear());

function voiceLine(vs) {
  return {
    up: "Its own voice (Breeze) is loaded.",
    starting: "Its own voice (Breeze) is loading (~15 s); until then replies are text only.",
    aside: "The voice is resting while it draws (ComfyUI gets the graphics memory); text only until the picture's done.",
    failed: `The voice didn't start: ${vs.breeze_why || "see ~/.aether/logs/breeze.log"}. Text only for now.`,
    off: "Its own voice (Breeze) loads when it next speaks.",
  }[vs.breeze || "off"];
}

function setSpeaking(on) {
  const l = $(".avatar-label");
  if (l) l.textContent = on ? "speaking…" : !Avatar.view ? "portrait" : Avatar.kind === "orb" ? "orb" : "Live2D";
  $(".avatar-card")?.classList.toggle("speaking", on);
}

const Term = {
  open: false, lines: [], cwd: "", hist: [], hi: 0,
  toggle() { this.open = !this.open; if (S.view === "chat") renderChat(); else showView("chat"); if (this.open) setTimeout(() => $("#termIn")?.focus(), 50); },
  add(who, kind, text) {
    if (kind === "cwd") { this.cwd = text; }
    else if (kind === "out") { const last = this.lines[this.lines.length - 1]; if (last && last.kind === "out" && last.who === who && !last.text.endsWith("\n")) last.text += text; else this.lines.push({ who, kind, text }); }
    else this.lines.push({ who, kind, text });
    if (this.lines.length > 800) this.lines.splice(0, this.lines.length - 800);
    this.renderOutput();
  },
  render() {
    const el = $("#term");
    if (!el) return;
    el.hidden = !this.open;
    if (!this.open) return;
    if (!this.cwd) api("/api/term").then((t) => { this.cwd = t.cwd; this.render(); }).catch(() => {});
    el.innerHTML = `<div class="term-head"><span>TERMINAL</span><span class="faint small">yours · commands ${esc(name())} runs show here too</span>
      <button class="btn term-stop" data-action="term-stop">■ Stop</button><button class="icon-btn" data-action="term">✕</button></div>
      <div class="term-out" id="termOut"></div>
      <div class="term-in"><span class="mono cyan">${esc(this.cwd || "~")}&gt;</span><input id="termIn" spellcheck="false" autocomplete="off" placeholder="type a command (PowerShell)"></div>`;
    this.renderOutput();
    const inp = $("#termIn");
    inp.addEventListener("keydown", async (e) => {
      if (e.key === "Enter") {
        const cmd = inp.value; inp.value = "";
        if (!cmd.trim()) return;
        this.hist.push(cmd); this.hi = this.hist.length;
        if (/^(cls|clear)$/i.test(cmd.trim())) { this.lines = []; return this.renderOutput(); }
        try { const r = await api("/api/term/run", { command: cmd }); if (r.cwd !== this.cwd) { this.cwd = r.cwd; this.render(); } }
        catch (err) { this.lines.push({ who: "user", kind: "end", text: err.message }); this.renderOutput(); }
      } else if (e.key === "ArrowUp") { if (this.hi > 0) inp.value = this.hist[--this.hi]; e.preventDefault(); }
      else if (e.key === "ArrowDown") { this.hi = Math.min(this.hist.length, this.hi + 1); inp.value = this.hist[this.hi] || ""; e.preventDefault(); }
      else if (e.key === "c" && e.ctrlKey && !inp.selectionEnd) { api("/api/term/stop", {}); e.preventDefault(); }
    });
  },
  renderOutput() {
    const out = $("#termOut");
    if (!out) return;
    out.innerHTML = this.lines.map((l) => l.kind === "cmd"
      ? `<div class="t-cmd ${l.who}"><span class="t-who">${l.who === "her" ? esc(name()) : "you"}</span> ${esc(l.text)}</div>`
      : l.kind === "end" ? `<div class="t-end">${esc(l.text)}</div>` : `<pre class="t-out">${esc(l.text)}</pre>`).join("");
    out.scrollTop = out.scrollHeight;
  },
};

const Avatar = {
  view: null, tried: false, mood: null,
  async mount(st) {
    if (this.tried || !st.settings.avatar_enabled) return;
    this.tried = true;
    if (st.life && st.life.mood) this.mood = st.life.mood.name;
    await this.load();
  },

  async load() {
    if (this.view) { this.view.destroy(); this.view = null; }
    $("#avatarImg").style.visibility = "";
    $("#avatarBox").classList.remove("on");
    let a;
    try { a = await api("/api/avatar"); } catch (e) { $(".avatar-label").textContent = "portrait"; return; }
    this.kind = a.info ? a.info.kind : null;
    if (a.info && a.info.kind === "orb" && typeof mountWireOrb === "function") {
      this.view = (a.info.style === "logo" ? mountOrb : mountWireOrb)($("#avatarBox"), { info: a.info });
      $("#avatarImg").style.visibility = "hidden";
      $("#avatarBox").classList.add("on");
      $("#svcAvatar").className = "svc up";
      $(".avatar-label").textContent = "orb";
      return;
    }
    if (!a.runtime || typeof mountAvatar !== "function") {
      $(".avatar-label").textContent = "portrait (Live2D runtime not installed: see the README)"; return;
    }
    if (!a.info) { $(".avatar-label").textContent = "portrait (no avatar yet: add one in Settings)"; return; }
    try {
      this.view = await mountAvatar($("#avatarBox"), { info: a.info });
      $("#avatarImg").style.visibility = "hidden";
      $("#avatarBox").classList.add("on");
      $("#svcAvatar").className = "svc up";
      $(".avatar-label").textContent = "Live2D";
      if (this.mood) this.view.setMood(this.mood);
    } catch (e) { console.warn("avatar:", e); $(".avatar-label").textContent = "portrait (avatar didn't load)"; }
  },
};

const MIC_QUIET = 2, MIC_NOTHING = 15, MIC_MAX = 60;
const Mic = {
  on: false, ctx: null, stream: null, node: null, chunks: [], rate: 16000,
  floor: 0.004, talked: false, loudRun: 0, quietSecs: 0,
  listen(x) {

    let s = 0;
    for (let i = 0; i < x.length; i++) s += x[i] * x[i];
    const rms = Math.sqrt(s / x.length), secs = x.length / this.rate;
    const loud = rms > Math.max(0.012, this.floor * 3);
    if (!loud) this.floor = this.floor * 0.9 + rms * 0.1;
    else this.lastLoud = performance.now();
    this.loudRun = loud ? this.loudRun + secs : 0;
    if (this.loudRun >= 0.2) this.talked = true;
    this.quietSecs = loud ? 0 : this.quietSecs + secs;
    const heard = this.chunks.length * x.length / this.rate;
    if (this.talked && this.quietSecs >= MIC_QUIET) this.stop(false, true);
    else if (heard >= MIC_MAX) this.stop();
    else if (!this.talked && heard >= MIC_NOTHING) { this.stop(true); toast("Didn't hear anything, so I stopped listening."); }
  },
  async start() {
    if (S.busy) return toast(`${name()} is still working; stop it first.`, true);
    try {
      this.stream = await MicPick.open(S.state.settings.mic_device, { channelCount: 1, echoCancellation: true, noiseSuppression: true });
    } catch (e) { return toast("No microphone (or it was blocked): " + e.message, true); }
    if (MicPick.missing) toast(`"${MicPick.missing}" isn't plugged in, so I'm using the Windows default mic.`, true);
    Player.clear(); api("/api/voice/stop", {}).catch(() => {});
    this.ctx = new AudioContext({ sampleRate: 16000 });
    this.rate = this.ctx.sampleRate;
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    this.chunks = []; this.floor = 0.004; this.talked = false; this.loudRun = 0; this.quietSecs = 0; this.lastLoud = 0;
    this.node.onaudioprocess = (e) => {
      if (!this.on) return;
      const x = new Float32Array(e.inputBuffer.getChannelData(0));
      this.chunks.push(x);
      this.listen(x);
    };
    src.connect(this.node); this.node.connect(this.ctx.destination);
    this.on = true; renderMic();
  },
  async stop(cancel, auto) {
    if (!this.on) return;
    if (!cancel) VoiceClock.start(this.lastLoud, "app");
    this.on = false; renderMic();
    this.node.disconnect(); this.stream.getTracks().forEach((t) => t.stop()); await this.ctx.close();
    if (auto && this.chunks.length) {
      const per = this.chunks[0].length / this.rate;
      this.chunks = this.chunks.slice(0, Math.max(1, this.chunks.length - Math.floor((this.quietSecs - 0.5) / per)));
    }
    const n = this.chunks.reduce((a, c) => a + c.length, 0);
    if (cancel || n < this.rate * 0.3) return VoiceClock.cancel();
    const wav = toWav(this.chunks, n, this.rate);
    try {
      toast("Listening back…");
      const r = await api("/api/hear", { data: wav });
      VoiceClock.mark("heard");
      const words = (r.text || "").replace(/[^\p{L}\p{N}]/gu, "").length >= 2;
      const speaker = r.sounds_like || "";
      if (!words && r.tone === "laughing") return send("(laughs)", { voice: true, tone: "laughing", speaker });
      if (!r.text) { VoiceClock.cancel(); return toast("Didn't catch that.", true); }
      send(r.text, { voice: true, tone: r.tone || "", speaker });
    } catch (e) { VoiceClock.cancel(); toast(e.message, true); }
  },
};
function toWav(chunks, n, rate) {
  const buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); str(8, "WAVEfmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, n * 2, true);
  let o = 44;
  for (const c of chunks) for (let i = 0; i < c.length; i++, o += 2) v.setInt16(o, Math.max(-1, Math.min(1, c[i])) * 0x7fff, true);
  let bin = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return "data:audio/wav;base64," + btoa(bin);
}
function renderMic() {
  const m = $(".mic");
  if (m) { m.classList.toggle("rec", Mic.on); m.title = Mic.on ? `Listening: sends ${MIC_QUIET} s after you stop talking · click to send now · Esc to cancel` : "Mic is off · click to talk"; }
  const ta = $("#input");
  if (ta && Mic.on) ta.placeholder = `Listening… sends ${MIC_QUIET} s after you stop talking (or click the mic), Esc to cancel`;
  else renderBusy();
}

async function refreshState() {
  try { S.state = await api("/api/state"); } catch (e) { return; }

  const was = S.busy;
  S.busy = S.state.busy;
  if (was && !S.busy && S.view === "chat") renderMessages();
  renderChrome();
  if (S.view === "images") renderImageQueue();
}

function renderChrome() {
  const st = S.state;
  if (!st) return;
  const L = st.agent;
  $$('[data-bind="name"]').forEach((el) => (el.textContent = L.name));
  document.title = Attention.title();
  $("#agentPic").src = picUrl();
  $("#avatarImg").src = picUrl();
  $("#agentSub").textContent = `Level ${appLevel()}${L.age_days != null ? ` · ${L.age_days} days old` : ""}`;
  $("#agentSub").title = `Command line: level ${appLevel()} (${L.permission})`;
  const badge = $("#modeBadge");

  badge.hidden = L.memory_mode === "home";
  badge.textContent = L.memory_mode === "test copy" ? "TEST COPY of its memory" : "a protected memory folder";
  badge.className = "mode-badge" + (L.memory_mode === "test copy" ? "" : " real");
  $("#memMode").textContent = L.memory_mode === "home" ? "its memory" : L.memory_mode;
  document.documentElement.style.setProperty("--space", st.settings.space_intensity);

  const lf = st.life || {};
  Avatar.mount(st);
  if (lf.mood) Avatar.mood = lf.mood.name;
  if (Avatar.view && lf.mood) Avatar.view.setMood(lf.mood.name);
  const mood = lf.mood;
  $("#moodBody").innerHTML = !st.settings.mood_enabled ? `<div class="mood-empty">Moods are off (Settings → Life).</div>` :
    mood && mood.name !== "steady"
      ? `<div style="display:flex;align-items:baseline;gap:10px"><span class="mood-name">${esc(mood.name)}</span><span class="dim small">${esc(lf.mood_label)} · fading slowly</span></div>
         <div class="dim small" style="margin-top:6px">${mood.why ? "since: " + esc(mood.why) : ""}${mood.before ? ` · before: ${esc(mood.before)}` : ""}</div>`
      : `<div style="display:flex;align-items:baseline;gap:10px"><span class="mood-name steady">steady</span><span class="dim small">its baseline</span></div>${mood?.before ? `<div class="dim small" style="margin-top:6px">last: ${esc(mood.before)}</div>` : ""}`;
  $("#reachText").textContent = `${lf.reach_outs ?? 0} / ${lf.cap ?? 6}`;
  $("#reachBar").style.width = `${Math.min(100, (100 * (lf.reach_outs || 0)) / (lf.cap || 6))}%`;
  if (lf.next_heartbeat) {

    const wake = new Date(lf.wake_at || lf.next_heartbeat);
    const mins = Math.max(0, Math.round((wake - Date.now()) / 60000));
    const at = wake.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    $("#hbText").textContent = lf.gate === "quiet hours" ? `quiet hours · ${at}`
      : lf.gate ? `${lf.gate} · ~${at}` : mins ? `in ${mins} min` : "any moment";
    $("#hbBar").style.width = `${Math.max(3, 100 - Math.min(100, (100 * mins) / (st.settings.heartbeat_minutes || 60)))}%`;
  } else { $("#hbText").textContent = "off"; $("#hbBar").style.width = "0"; }
  $("#quietLine").textContent = `Quiet hours ${st.settings.quiet_start}–${st.settings.quiet_end}`;
  const pl = $("#permLine");
  if (pl) pl.textContent = `Permission: level ${appLevel()} (${levelName(appLevel())})`;
  const db = $('#nav [data-view="dreams"]');
  if (db) db.innerHTML = `<span class="ico" data-icon="moon"></span>Dreams${lf.dream_unseen ? '<span class="badge">1 new</span>' : ""}`;
  fillIcons($("#nav"));
  const rb = $("#residueBadge");
  if (rb) { const r = lf.residue; rb.hidden = !(r && r.text); if (r) rb.textContent = `dream residue: “${r.text}”`; }

  const used = st.context_used || 0, max = st.services.context_max || 0;
  $("#ctxText").textContent = max ? `${(used / 1000).toFixed(1)}k / ${Math.round(max / 1000)}k` : used ? `${(used / 1000).toFixed(1)}k` : "–";
  $("#ctxBar").style.width = max ? `${Math.min(100, (100 * used) / max)}%` : "0";

  const lm = $("#svcLm");
  lm.className = "svc " + (st.services.model_loaded ? "up" : st.services.lmstudio ? "warn" : "down");
  lm.title = st.services.model_loaded ? `${st.agent.model} loaded` : st.services.lmstudio ? `LM Studio is up but ${st.agent.model} isn't loaded` : "LM Studio isn't answering";
  const vs = st.services.voice || {}, vk = $("#svcKokoro");
  if (vs.engine === "breeze") {
    $("#svcVoiceName").textContent = "voice";
    vk.className = "svc " + ({ up: "up", starting: "warn", aside: "warn" }[vs.breeze] || "down");
    vk.title = voiceLine(vs);
  } else {
    $("#svcVoiceName").textContent = "voice server";
    vk.className = "svc " + (st.services.kokoro ? "up" : "down");
    vk.title = st.services.kokoro ? "the voice server is answering" : `the voice server at ${st.settings.tts_url} isn't answering`;
  }
  $("#svcEars").className = "svc " + (st.services.ears ? "up" : "down");
  const dsc = $("#svcDiscord");
  if (dsc) { dsc.className = "svc " + (st.services.discord === null ? "off" : st.services.discord ? "up" : "down"); dsc.title = st.services.discord === null ? "Discord is off (Settings)" : st.services.discord ? "Discord connected" : "Discord connecting…"; }
  $("#svcEars").title = st.services.ears ? "SenseVoice is ready (starts on first use)" : "SenseVoice not found";
  renderChatList();
  renderBusy();
}

function vramBit() {
  const v = S.state?.services?.vram;
  if (!v) return "";
  const gb = (b) => (b / 1073741824).toFixed(1);
  const tip = (v.card ? `${v.card}\n` : "") + v.parts.map((p) => `${p.name}: ${gb(p.bytes)} GB`).join("\n");
  const full = v.total && v.used / v.total >= 0.9;
  return ` · <span class="vram${full ? " gold" : ""}" title="${esc(tip)}">VRAM ${gb(v.used)}${v.total ? ` / ${Math.round(v.total / 1073741824)}` : ""} GB</span>`;
}

function renderBusy() {
  const st = S.state;
  const model = (st?.agent?.model || "").split("/").pop();
  $("#statusRight").innerHTML = `${esc(model)}${vramBit()} · ${S.busy ? `<span class="gold">GPU busy · ${esc(S.status || "working")}</span>` : "GPU idle"} · tool calls format-locked ✓` +
    (S.busy ? ` <button class="stopall" data-action="stop">■ stop all</button>` : "");
  const bar = $(".inputbar");
  if (!bar) return;
  bar.classList.toggle("busy", S.busy);
  const ta = $("textarea", bar);
  if (ta) ta.placeholder = S.busy ? `${name()} is working… step ${S.steps} of max ${st?.max_steps || 11}` : (S.view === "newchat" ? `Message ${name()} to start a new chat…` : `Talk to ${name()}…`);
  const btn = $(".send, .stop", bar);
  if (btn) btn.outerHTML = S.busy ? `<button class="stop" data-action="stop"><i></i>Stop <span class="kbd">Esc</span></button>` : `<button class="send" data-action="send">Send</button>`;
}

function renderChatList() {
  const st = S.state;
  const cur = S.chat?.id || st.current;
  const all = st.chats.filter((c) => c.events > 0 || c.id === cur);

  const archived = all.filter((c) => c.archived);
  const chats = all.filter((c) => !c.archived);
  const openArchived = archived.some((c) => c.id === cur);
  const pinned = chats.filter((c) => c.pinned);
  const recent = chats.filter((c) => !c.pinned);
  const row = (c) => {
    const ic = c.source === "discord" || c.id.startsWith("discord-") ? icon("discord") : c.source === "avatar" ? icon("mic", "var(--cyan)") : icon("chat");
    const on = c.id === cur && (S.view === "chat" || S.view === "newchat");
    return `<button class="chat-row${on ? " on" : ""}${c.unread ? " unread" : ""}" data-chat="${esc(c.id)}">${ic}<span class="t">${esc(c.events ? c.title : "New chat")}</span>` +
      `<span class="when">${esc(ago(c.updated))}${c.unread ? '<span class="udot"></span>' : ""}</span><span class="more" data-chat-menu="${esc(c.id)}">⋯</span></button>`;
  };
  let html = "";
  if (pinned.length) html += `<div class="list-label">${icon("pin")}PINNED</div>` + pinned.map(row).join("");
  if (recent.length) {

    const TOP = 3;
    const shown = S.showAll ? recent : recent.filter((c, i) => i < TOP || c.id === cur);
    const hidden = recent.length - shown.length;
    html += `<div class="list-label toggle" data-action="toggle-recent">RECENT ${S.recentOpen ? "▾" : "▸"}</div>`;
    if (S.recentOpen) {
      html += shown.map(row).join("");
      if (S.showAll && recent.length > TOP) html += `<button class="show-all" data-action="show-all">▴ Show fewer</button>`;
      else if (hidden > 0) html += `<button class="show-all" data-action="show-all">▾ ${hidden} more</button>`;
    }
  }

  if (archived.length) {
    const open = S.archiveOpen || openArchived;
    html += `<div class="list-label toggle" data-action="toggle-archive">${icon("archive")}ARCHIVED (${archived.length}) ${open ? "▾" : "▸"}</div>`;
    if (open) html += archived.map(row).join("");
  }
  $("#chatLists").innerHTML = html;
  $$("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.view === S.view));
}

function showView(v) {
  S.view = v;
  $(".main").classList.toggle("wide", v === "brain");
  closeOverlay();
  const c = $("#center");
  if (v === "chat") renderChat();
  else if (v === "newchat") renderNewChat();
  else if (v === "brain") renderBrain();
  else if (v === "know") renderKnow();
  else if (v === "skills") renderSkills();
  else if (v === "settings") renderSettings();
  else if (v === "dreams") renderDreams();
  else if (v === "images") renderImages();
  else if (v === "heartbeat") renderHeartbeat();
  else if (v === "calendar") renderCalendar();
  else { S.view = "chat"; return showView(S.chat ? "chat" : "newchat"); }
  if (S.state) renderChatList();
}

async function openChat(id, keepView) {
  try {
    const c = await api(`/api/chat?id=${encodeURIComponent(id)}`);
    S.chat = c;
    if (!keepView || S.view === "chat" || S.view === "newchat") showView(c.events.length ? "chat" : "newchat");
    refreshState();
  } catch (e) { toast(e.message, true); }
}

async function newChat() {
  if (S.busy) return toast(`${name()} is still working; stop it or wait.`, true);
  try {
    const r = await api("/api/chat/new", {});
    S.chat = { id: r.id, title: "New chat", events: [] };
    showView("newchat");
    refreshState();
  } catch (e) { toast(e.message, true); }
}

function renderChat() {
  const now = new Date();
  $("#center").innerHTML = `
    <div class="chat-head"><button class="icon-btn term-btn${Term.open ? " on" : ""}" data-action="term" title="Terminal (Ctrl+\`)">${icon("terminal")}</button><h1>${esc(name())}<span> · ${esc(S.chat?.title || "")}</span></h1><span class="residue" id="residueBadge" hidden></span>
      <div class="dim small">${now.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" })} · ${now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</div></div>
    <div class="messages" id="messages"></div>
    <div class="term" id="term" ${Term.open ? "" : "hidden"}></div>
    ${S.chat?.id === "heartbeat" ? heartbeatLogNote() : composerHTML()}`;
  renderMessages();
  Term.render();
  wireComposer();
  renderBusy();
}

function chipFor(step, res, auto) {
  const ok = res ? res.ok : null;
  const text = res?.text || "";
  const k = step.step;
  const short = (p) => String(p || "").replace(/^system\//, "");
  let label = "", sub = "";
  if (k === "memory_add") { label = ok === false ? "Didn't save" : "Saved to memory"; sub = `${short(step.file)} · + ${String(step.text).replace(/^\s*-?\s*\d{4}-\d{2}-\d{2}:?\s*/, "")}`; }
  else if (k === "memory_replace") { label = ok === false ? "Didn't change" : "Changed memory"; sub = `${short(step.file)} · ${step.old} → ${step.new}`; }
  else if (k === "memory_remove") { label = ok === false ? "Didn't remove" : "Removed from memory"; sub = `${short(step.file)} · − ${step.line}`; }
  else if (k === "memory_create") { label = ok === false ? "Didn't create" : "New note"; sub = step.path; }
  else if (k === "memory_delete") { label = ok === false ? "Didn't delete" : "Deleted note"; sub = step.file; }
  else if (k === "read_file") { label = "Read"; sub = step.path; }
  else if (k === "read_skill") { label = "Opened skill"; sub = step.skill; }
  else if (k === "skill") { label = ok === null ? `Using skill: ${step.skill}` : `${ok ? "Used" : "Failed"} skill: ${step.skill}`; sub = [step.command, ...(step.args || [])].filter(Boolean).join(" "); }
  else if (k === "journal") { label = ok === null ? "Writing in its journal" : ok ? "Wrote in its journal" : "Didn't write in its journal"; sub = step.about || ""; }
  else if (k === "set_mood") { label = ok === false ? "Mood unchanged" : `Chose its mood: ${step.mood || ""}`; sub = step.why || ""; }
  else if (k === "recall") { label = "Searched its memories"; sub = step.query || ""; }
  else if (k === "webcam" || k === "look") {
    label = "Looked through your webcam"; sub = step.about || ""; }
  else if (k === "look_back") { label = "Looked back through its memory's history"; sub = step.about || ""; }
  else if (k === "read_chat") { label = "Read a chat"; sub = step.which || ""; }
  else if (k === "wake_me") { label = ok === false ? "Didn't set a wake-up" : "Set a wake-up for itself"; sub = `${step.at || ""} · ${step.note || ""}`; }
  else if (k === "gallery") { label = step.show ? `Looked at picture ${step.show}` : "Looked through its gallery"; sub = ""; }
  else if (k === "make_image") { label = ok === false ? "Didn't start a picture" : "Making a picture"; sub = `${step.shape || ""} · ${step.prompt || ""}`; }
  else if (k === "make_video") { label = ok === false ? "Didn't start a video" : "Making a video"; sub = `${step.from_picture ? `from picture ${step.from_picture} · ` : ""}${step.prompt || ""}`; }
  else if (k === "save_research") {

    const topic = (text.match(/^(?:Saved in|Already in|Started a new topic,) ([\w-]+)/) || [])[1] || "";
    const take = (text.match(/^\s*my take: - [\d-]+: (.+)$/m) || [])[1];
    const note = (text.match(/^\s*note: - [\d-]+: (.+)$/m) || [])[1];
    label = ok === null ? "Saving to its research" : ok ? (/^Already in/.test(text) ? "Already in its research" : "Saved to its research")
      : /^Read first:/.test(text) ? "Read the Drop box file first" : "Didn't save to its research";
    sub = ok ? [topic.replace(/-/g, " "), take ? "my take: " + take : note || ""].filter(Boolean).join(" · ") : ok === false ? text.split("\n")[0] : "";
    if (auto) sub += ` · Aether took this step (it chose ${auto})`;
  }
  else { label = "Step"; sub = k; }
  if (ok && k !== "save_research" && /^(Already in|Nothing to change)/.test(text)) label = "Already in memory";

  const repeat = ok === false && /^You already took exactly this step/.test(text);
  if (repeat) label = "Skipped a repeat";

  const steer = ok === false && /^(Not opened: .{1,60}? asked about (?:his|her|their) Library|Read first:)/.test(text);
  if (steer && k === "read_file") label = "Pointed to the research skill";
  const commit = (text.match(/\(commit ([0-9a-f]{5,})\)/) || [])[1];
  const cls = ok === null ? "run" : ok ? "" : repeat || steer ? "quiet" : "fail";
  const mark = ok === null ? '<span class="spin"></span>' : `<span class="mark">${ok ? "✓" : repeat ? "↺" : steer ? "↪" : "✕"}</span>`;

  const firstOut = text.split("\n").find((l) => l.trim() && !/^[{[]/.test(l.trim())) || "";
  return `<div class="chip ${cls}">${mark}<details><summary><span class="label">${esc(label)}</span> <span class="sub">${esc(sub)}${k === "skill" && firstOut ? " · " + esc(firstOut.slice(0, 90)) : ""}</span></summary>${text ? `<pre>${esc(text)}</pre>` : ""}</details>` +
    (commit ? `<button class="rw" data-rewind="${commit}">↶ rewind</button>` : "") + `</div>`;
}

function mindChip(e, i) {
  const items = e.remembered || [];
  if (items.length) {
    const rows = items.map((m, j) => `<div class="mind-row"><pre>${esc(`${m.when ? m.when + " · " : ""}${m.kind === "chat" ? "chat “" + m.where + "”" : m.where}\n${m.text}`)}</pre>` +
      `<button class="rw" data-forget="${i}:${j}" title="This memory is wrong or outdated: it won't come up again">✗ wrong</button></div>`).join("");
    return `<div class="chip quiet"><span class="mark">🧠</span><details><summary><span class="label">Came to mind: ${items.length}</span> ` +
      `<span class="sub">${esc(items.map((m) => m.when || m.where).join(" · ").slice(0, 90))}</span></summary>${rows}</details></div>`;
  }
  if ((e.memories || "").startsWith("[Nothing from your time")) {
    return `<div class="chip quiet"><span class="mark">🧠</span><span class="label">Nothing came to mind</span><span class="sub">told it to say it doesn't remember</span></div>`;
  }
  return "";
}

const FENCED = /```([\w+-]*)[^\n]*\n?([\s\S]*?)(?:```|$)/g;
function richText(text) {
  const t = String(text ?? "");
  let html = "", last = 0;
  for (const m of t.matchAll(FENCED)) {
    if (!m[0]) break;
    html += esc(t.slice(last, m.index).replace(/[ \t]*\n$/, "")) + codeBox(m[2].replace(/\n$/, ""), m[1]);
    last = m.index + m[0].length;
  }
  return html + esc(t.slice(last).replace(/^[ \t]*\n/, ""));
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {  }
  const ta = Object.assign(document.createElement("textarea"), { value: text });
  ta.style.cssText = "position:fixed;top:0;left:0;opacity:0";
  document.body.appendChild(ta);
  ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  return ok;
}

function trackId(code) {
  let h = 0x811c9dc5;
  for (const b of new TextEncoder().encode(code.trim())) h = Math.imul(h ^ b, 0x01000193) >>> 0;
  return h.toString(16).padStart(8, "0");
}
function codeBox(code, lang) {
  return `<div class="codebox"><div class="codebar"><span class="lang">${esc(lang || "code")}</span>` +
    `<button class="code-btn" data-copy-code title="Copy the code">⧉ Copy</button></div><pre><code>${esc(code)}</code></pre></div>`;
}

function songAudio(path) {
  return `<audio class="att made song-audio" controls preload="none" src="/api/attachment?t=${TOKEN}&p=${encodeURIComponent(path)}"></audio>`;
}
function rateButtons(key) {
  const rated = (S.ratings || {})[trackId(key)];
  return ["up", "down"].map((r) => `<button class="code-btn rate${rated === r ? " on" : ""}" data-rate="${r}" data-key="${esc(key)}" ` +
    `title="${r === "up" ? "I like this one" : "Not for me"}: it sees this the next time it makes a song">${r === "up" ? "👍" : "👎"}</button>`).join("");
}
async function loadRatings() {
  try { S.ratings = await api("/api/music/ratings"); } catch { S.ratings = S.ratings || {}; }
}

function renderMessages() {
  const box = $("#messages");
  if (!box || !S.chat) return;
  const showWork = S.state?.settings?.show_work !== false;
  const ev = S.chat.events;
  const failed = S.busy ? -1 : unanswered(ev);
  let html = "";

  const cut = ev.findLastIndex((e) => e.kind === "compact");
  const folded = cut >= 0 && !S.unfolded.has(S.chat.id);
  if (cut >= 0) {
    const n = ev.slice(0, cut).filter((e) => e.kind === "user" || e.kind === "reply" || e.kind === "reach_out").length;
    html += `<button class="show-all fold" data-action="fold-compact">${folded ? `▸ ${n} earlier messages · ${esc(name())} remembers them through its note` : "▴ Fold the earlier messages away"}</button>`;
  }
  for (let i = folded ? cut : 0; i < ev.length; i++) {
    const e = ev[i];
    if (e.kind === "user") {
      const via = (e.place && !/aether/i.test(e.place) ? ` · <span class="cyan">via ${esc(e.place)}</span>` : "") +
        (e.voice ? ` · <span class="pink">🎤 voice${e.tone ? " · " + esc(e.tone) : ""}</span>` : "");
      const imgs = (e.images || []).map((p) => { const src = `/api/attachment?t=${TOKEN}&p=${encodeURIComponent(p)}`; return `<img class="att" data-lightbox="${src}" src="${src}" alt="">`; }).join("");
      const retry = i === failed ? `<div class="retry"><span>${esc(name())} didn't answer this</span><button class="btn" data-action="retry">↻ Retry</button></div>` : "";
      html += `<div class="msg me"><div class="meta">${esc(userName())} · ${e.ts ? clock(e.ts) : ""}${via}</div><div class="bubble">${esc(e.text)}${imgs}</div>${retry}</div>`;
      html += mindChip(e, i);
    } else if (e.kind === "step") {
      const res = ev[i + 1]?.kind === "result" ? ev[i + 1] : null;
      if (res) i++;

      if (showWork || e.step.step.startsWith("memory_") || e.step.step === "save_research") html += chipFor(e.step, res, e.auto);
    } else if (e.kind === "wake") {
      const what = (e.place || "").replace(/^reminder: /, "");
      html += `<div class="chip wake"><span class="mark">${e.place === "heartbeat" ? "☾" : "⏰"}</span><span class="label">${e.place === "heartbeat" ? "Woke up on its own" : "Reminder: " + esc(what)}</span><span class="sub">${e.ts ? clock(e.ts) : ""}</span></div>`;
    } else if (e.kind === "reach_out") {
      html += `<div class="msg"><div class="meta">${esc(name())} · ${e.ts ? clock(e.ts) : ""} · <span class="pink">messaged you on its own</span> <button class="say" data-say="${i}" title="Say it out loud">▶</button></div><div class="bubble">${richText(e.text)}</div></div>`;
    } else if (e.kind === "made_image") {

      const imgs = (e.images || []).map((p) => { const src = `/api/attachment?t=${TOKEN}&p=${encodeURIComponent(p)}`; return `<img class="att made" data-lightbox="${src}" src="${src}" alt="" title="${esc(e.prompt || "")}">`; }).join("");
      html += `<div class="msg"><div class="meta">${esc(name())} · ${e.ts ? clock(e.ts) : ""} · <span class="pink">made you a picture</span></div><div class="bubble">${esc(e.caption || "")}${imgs}</div></div>`;
    } else if (e.kind === "made_song") {

      html += `<div class="msg"><div class="meta">${esc(name())} · ${e.ts ? clock(e.ts) : ""} · <span class="pink">made you a song</span></div><div class="bubble"><b>♪ ${esc(e.title || "")}</b> ${esc(e.caption || "")}${e.audio ? songAudio(e.audio) : ""}</div></div>`;
    } else if (e.kind === "made_video") {

      const url = (p) => `/api/attachment?t=${TOKEN}&p=${encodeURIComponent(p)}`;
      const vid = e.video ? `<video class="att made" controls loop preload="metadata" src="${url(e.video)}"${(e.images || [])[0] ? ` poster="${url(e.images[0])}"` : ""} title="${esc(e.prompt || "")}"></video>` : "";
      html += `<div class="msg"><div class="meta">${esc(name())} · ${e.ts ? clock(e.ts) : ""} · <span class="pink">made you a video</span></div><div class="bubble">${esc(e.caption || "")}${vid}</div></div>`;
    } else if (e.kind === "result") {
      if (e.of === "engine") html += `<div class="chip fail"><span class="mark">!</span><span class="sub">${esc(e.text)}</span></div>`;
    } else if (e.kind === "reply") {
      html += `<div class="msg"><div class="meta">${esc(name())} · ${e.ts ? clock(e.ts) : ""}${e.live ? "" : ` <button class="say" data-say="${i}" title="Say it out loud">▶</button>`}</div><div class="bubble"${e.live ? ' id="liveBubble"' : ""}>${richText(e.text)}${e.stopped ? '<span class="stopped">[stopped]</span>' : ""}</div></div>`;
    } else if (e.kind === "compact") {

      const note = ev.slice(0, i).reverse().find((x) => x.kind === "summary");
      html += `<div class="compact-mark"><div class="line">Compacted${e.ts ? " · " + clock(e.ts) : ""} · it remembers everything above through its own note</div>` +
        (note ? `<details${i === ev.length - 1 ? " open" : ""}><summary>Its note</summary><div class="note">${esc(note.text)}</div></details>` : "") + `</div>`;
    } else if (e.kind === "proposal") {

      const ans = ev.slice(i + 1).find((x) => x.kind === "proposal_answer" && x.pid === e.pid);
      const later = ans && ans.answer === "later";

      const review = e.type === "review";
      const said = { yes: review ? "done" : "yes", no: review ? "sent it back" : "no", later: "later" };
      html += `<div class="ask proposal"><div class="meta">${esc(name())} · ${e.ts ? clock(e.ts) : ""} · <span class="pink">${review ? "📋 review: every step ticked" : `💡 ${esc(e.type || "idea")}: needs your yes`}</span></div>` +
        `<div><b>${esc(e.title || "")}</b></div><div class="pre">${esc(e.why || "")}</div><div class="dim">${review ? "" : "Plan: "}${esc(e.plan || "")}${e.brief ? ` · brief: ${esc(e.brief)}` : ""}</div>` +
        ((e.after_outside || []).length ? `<div class="gold small">Made after reading: ${esc(e.after_outside.join(", "))}</div>` : "") +
        `<div class="btns">${ans && !later ? `<span class="dim">You said ${esc(said[ans.answer] || ans.answer)}</span>` :
          `<button class="btn primary" data-proposal="${esc(e.pid)}" data-reply="yes">${review ? "Done" : "Yes"}</button><button class="btn" data-proposal="${esc(e.pid)}" data-reply="no"${review ? ' data-note="1"' : ""}>${review ? "Send back" : "No"}</button>` +
          (later ? `<span class="dim">You said later</span>` : `<button class="btn" data-proposal="${esc(e.pid)}" data-reply="later">Later</button>`)}</div></div>`;
    } else if (e.kind === "proposal_answer") {
      html += `<div class="chip wake"><span class="mark">💡</span><span class="label">You answered “${esc(e.title || "")}”: ${esc(e.answer || "")}</span><span class="sub">${e.ts ? clock(e.ts) : ""}</span></div>`;
    } else if (e.kind === "ask") {
      html += `<div class="ask">🔒 ${esc(e.question)}<div class="btns">${e.answered ? `<span class="dim">${esc(e.answered)}</span>` :
        `<button class="btn primary" data-answer="${e.qid}" data-allow="1">Allow</button><button class="btn" data-answer="${e.qid}" data-allow="0">Don't</button>`}</div></div>`;
    }
  }
  html += workHTML();
  box.innerHTML = html;
  box.scrollTop = box.scrollHeight;
}

const WORK_STATUS = { thinking: "thinking…", replying: "writing its reply…", stopped: "stopping…" };
function workStart(chat) { S.work = { chat, status: "thinking", steps: [], t0: Date.now() }; }
function workWhere(w) {
  if (!w || (S.chat && w.chat === S.chat.id)) return "";
  if (w.chat === "heartbeat") return "woke up on its own";
  if (String(w.chat).startsWith("studio-")) return "is looking at a picture it made";
  if (String(w.chat).startsWith("note-")) return "is writing its note about a chat";
  if (String(w.chat).startsWith("discord-")) return "is answering on Discord";
  const c = (S.state?.chats || []).find((x) => x.id === w.chat);
  return `is busy in another chat${c?.title ? ` (${c.title})` : ""}`;
}
const secs = (t0) => { const s = Math.max(0, Math.round((Date.now() - t0) / 1000)); return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`; };
function workHTML() {
  if (!S.busy) return "";
  const w = S.work || { chat: S.chat?.id, status: S.status || "working", steps: [], t0: Date.now() };
  const where = workWhere(w);
  const last = S.chat?.events[S.chat.events.length - 1];
  if (!where && last?.kind === "reply" && last.live) return "";
  const st = String(w.status || "working");
  const doing = WORK_STATUS[st] || (st.startsWith("running") ? st + "…" : st.startsWith("error") ? st : "working…");
  const max = S.state?.max_steps || 11;
  const steps = where ? w.steps.map((s) => chipFor(s.step, s.res)).join("") : "";
  return `<div class="work" id="workPanel"><div class="work-head"><span class="spin"></span>` +
    `<span><b>${esc(name())}</b> ${where ? `${esc(where)} · ` : ""}${esc(doing)}</span>` +
    `<span class="work-meta">${w.steps.length ? `step ${w.steps.length} of max ${max} · ` : ""}<span id="workTime">${secs(w.t0)}</span></span>` +
    `<button class="btn work-stop" data-action="stop">■ Stop</button></div>` +
    (steps ? `<div class="work-steps">${steps}</div>` : "") + `</div>`;
}

function renderWork() {
  if (S.view !== "chat") return;
  const box = $("#messages");
  if (!box) return;
  const html = workHTML(), el = $("#workPanel");
  if (el && html) el.outerHTML = html;
  else if (el) el.remove();
  else if (html) {
    const near = box.scrollHeight - box.scrollTop - box.clientHeight < 200;
    box.insertAdjacentHTML("beforeend", html);
    if (near) box.scrollTop = box.scrollHeight;
  }
}
setInterval(() => { const t = $("#workTime"); if (t && S.work) t.textContent = secs(S.work.t0); }, 1000);

function unanswered(ev) {
  for (let i = ev.length - 1; i >= 0; i--) {
    const e = ev[i];
    if (((e.kind === "reply" || e.kind === "reach_out") && (e.text || "").trim()) || e.kind === "made_image" || e.kind === "made_video" || e.kind === "made_song") return -1;
    if (e.kind === "user") return i;
  }
  return -1;
}
async function retry() {
  const ev = S.chat?.events || [];
  const i = unanswered(ev);
  if (i < 0 || S.busy) return;

  ev.splice(i);
  S.busy = true; renderMessages(); renderBusy();
  try { await api("/api/retry", { id: S.chat.id }); }
  catch (e) { S.busy = false; renderBusy(); toast(e.message, true); openChat(S.chat.id, true); }
}

function renderLive(reply) {
  const b = $("#liveBubble");
  if (reply && b) {
    b.innerHTML = richText(reply.text);
    const box = $("#messages");
    if (box.scrollHeight - box.scrollTop - box.clientHeight < 200) box.scrollTop = box.scrollHeight;
  } else renderMessages();
}

function heartbeatLogNote() {
  return `<div class="composer"><div class="dim small" style="padding:12px 16px;line-height:1.5">${icon("heartpulse")} This is ${esc(name())}'s heartbeat log: what it did and thought each time it woke up on its own. Its last line each time is a note to itself, unless it chose to message you; those go to your chats (Heartbeat &amp; schedules → Its messages go to).</div></div>`;
}

function composerHTML() {
  return `<div class="composer"><div class="attach-row" id="attachRow"></div>
    <div class="inputbar"><button class="plus" data-action="plus" title="Add">+</button>
      <textarea id="input" rows="1" placeholder="Talk to ${esc(name())}…"></textarea>
      <button class="mic${Mic.on ? " rec" : ""}" data-action="mic" title="Mic is off · click to talk">${icon("mic")}</button>
      <button class="send" data-action="send">Send</button></div></div>`;
}
function wireComposer() {
  const ta = $("#input");
  if (!ta) return;
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  ta.addEventListener("input", () => {
    ta.style.height = "auto"; ta.style.height = Math.min(200, ta.scrollHeight) + "px";
    typingPing();
  });

  ta.addEventListener("paste", (e) => {
    const files = [...(e.clipboardData?.files || [])].filter(attachable);
    if (files.length) { e.preventDefault(); addImages(files); }
  });
  const bar = ta.closest(".composer");
  bar.addEventListener("dragover", (e) => { e.preventDefault(); bar.classList.add("drop"); });
  bar.addEventListener("dragleave", () => bar.classList.remove("drop"));
  bar.addEventListener("drop", (e) => {
    e.preventDefault(); bar.classList.remove("drop");
    addImages([...(e.dataTransfer?.files || [])].filter(attachable));
  });
  renderAttach();
  ta.focus();
}

let lastTypingPing = 0;
function typingPing() {
  if (Date.now() - lastTypingPing < 10000) return;
  lastTypingPing = Date.now();
  api("/api/typing", {}).catch(() => {});
}

const attachable = (f) => f.type.startsWith("image/") || f.type === "application/pdf" || /\.pdf$/i.test(f.name || "");
async function addImages(files) {
  const room = 4 - S.attach.length;
  if (files.length > room) toast(`Up to 4 files per message`, true);
  for (const f of files.slice(0, Math.max(0, room))) {
    if (f.size > 12e6) { toast(`${f.name} is over 12 MB`, true); continue; }
    const ext = (f.type.split("/")[1] || "png").replace("jpeg", "jpg");
    const name = /\.\w+$/.test(f.name || "") ? f.name : `pasted.${ext}`;
    S.attach.push({ name, data: await readFile(f) });
  }
  renderAttach();
}
function renderAttach() {
  const row = $("#attachRow");
  if (!row) return;
  row.innerHTML = S.attach.map((a, i) => (/\.pdf$/i.test(a.name)
    ? `<div class="a pdf" title="${esc(a.name)}"><span>📄</span><em>${esc(a.name)}</em><button data-unattach="${i}">✕</button></div>`
    : `<div class="a"><img src="${a.data}" alt=""><button data-unattach="${i}">✕</button></div>`)).join("");
}
async function send(text, opts = {}) {
  const ta = $("#input");
  const typed = text === undefined;
  text = text ?? ta?.value ?? "";
  if (!opts.voice || S.busy) VoiceClock.cancel();
  if (S.busy) return;
  if (!text.trim() && !S.attach.length) return;
  if (typed && /^\/compact$/i.test(text.trim())) {
    if (ta) { ta.value = ""; ta.style.height = "auto"; }
    return S.chat ? compactChat(S.chat.id) : toast("Nothing to sum up yet: this chat is empty", true);
  }
  if (!S.chat) { await newChat(); }
  const images = S.attach;
  try {
    S.busy = true; S.steps = 0;
    await api("/api/send", { id: S.chat.id, text, images, voice: !!opts.voice, tone: opts.tone || "", speaker: opts.speaker || "" });
    if (ta && typed) { ta.value = ""; ta.style.height = "auto"; }
    S.attach = []; renderAttach();
    if (S.view !== "chat") showView("chat");
    renderBusy();
  } catch (e) { VoiceClock.cancel(); S.busy = false; renderBusy(); toast(e.message, true); }
}
const stop = () => { VoiceClock.cancel(); Player.clear(); return api("/api/stop", {}).catch(() => {}); };

async function compactChat(id) {
  if (S.busy) return toast(`${name()} is still working; stop it or wait.`, true);
  try {
    await api("/api/chat/compact", { id });
    S.busy = true; S.steps = 0; S.status = "summing up this chat";
    workStart(id); S.work.status = "summing up this chat…";
    renderBusy(); renderWork();
  } catch (e) { toast(e.message, true); }
}

function readFile(file) {
  return new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = bad; r.readAsDataURL(file); });
}
function pickFiles(accept, multiple) {
  return new Promise((ok) => {
    const inp = $("#filePick");
    inp.value = ""; inp.accept = accept || ""; inp.multiple = !!multiple;
    inp.onchange = () => ok([...inp.files]);
    inp.click();
  });
}

async function renderNewChat() {
  $("#center").innerHTML = `<div class="newchat"><div class="inner">
      <img class="portrait" src="${picUrl()}" alt="">
      <div class="greet loading" id="greet">…</div>
      <div class="under">New chat · it still remembers everything from your other chats</div>
      ${composerHTML()}
      <div class="chips"><span style="color:var(--green)">● Local · ${esc((S.state?.agent?.model || "").split("/").pop())}</span>
        <span style="color:var(--cyan)">◈ Level ${appLevel()} · ${esc(levelName(appLevel()))}</span><span class="faint">Named after the first message</span></div>
      <div class="suggest" id="suggest"></div></div></div>`;
  wireComposer();
  renderBusy();
  try {
    const g = await api("/api/greeting");
    if (S.view !== "newchat") return;
    $("#greet").textContent = g.greeting; $("#greet").classList.remove("loading");
    const glyph = { continue: "▶", dream: "☾", check: "◷", project: "✦", fun: "♥" };
    $("#suggest").innerHTML = (g.suggestions || []).length ? `<div class="eyebrow">FROM ITS MEMORY</div>` +
      g.suggestions.map((s) => `<button class="row" data-suggest="${esc(s.text)}"><span class="g">${glyph[s.kind] || "✦"}</span>${esc(s.text)}</button>`).join("") : "";
  } catch (e) { $("#greet").textContent = "Back already? What are we getting into?"; }
}

async function renderDreams() {
  $("#center").innerHTML = `<div class="page"><h1>Dreams</h1><p class="lead">Each night, while you sleep, ${esc(name())} turns bits of the day into a dream, the Jung way: symbols, not a summary. What's left of it (the residue) can color one thing it says the next day.</p>
    <div><button class="btn primary" data-life="dream">☾ Dream now</button></div><div id="dreamList" class="dim" style="margin-top:20px">Loading…</div></div>`;
  try {
    const L = await api("/api/life");
    if (L.dream_unseen) api("/api/life/dreams-seen", {}).then(refreshState);
    if (S.view !== "dreams") return;
    $("#dreamList").outerHTML = L.dreams.length ? L.dreams.map((d) => `<div class="dream"><div class="eyebrow">${esc(d.date)}</div><div class="dream-text">${esc(d.dream)}</div>
      <div class="symbols">${d.symbols.map((x) => `<span><b>${esc(x.image)}</b> · ${esc(x.meaning)}</span>`).join("")}</div>
      ${d.residue ? `<div class="gold small" style="margin-top:10px">residue: “${esc(d.residue)}”</div>` : ""}</div>`).join("")
      : `<div class="dim">No dreams yet. The first comes at ${esc(S.state.settings.dream_time)} if Aether is open and you two talked that day.</div>`;
  } catch (e) { toast(e.message, true); }
}

async function renderImages() {
  let r, tracks;
  try {
    [r, tracks] = await Promise.all([api("/api/images"), api("/api/music/tracks").then((x) => x.songs || []).catch(() => [])]);
  } catch (e) { return toast(e.message, true); }
  if (!S.ratings) await loadRatings();
  if (S.view !== "images") return;
  S.gallery = r.gallery;
  const st = S.state?.settings || {};
  const tile = ([g, i]) => `<button class="img-tile ${esc(g.shape === "video" ? "landscape" : g.shape)}" data-img="${i}" title="${esc(g.prompt)}">
      <img src="/api/attachment?t=${TOKEN}&p=${encodeURIComponent(g.image)}" alt="" loading="lazy">
      ${g.kind === "video" ? `<span class="vid-badge" title="a video">▶</span>` : ""}
      <span class="cap">${esc(g.title || g.caption || "untitled")}</span><span class="when">${esc(ago(g.made))}</span></button>`;
  const all = r.gallery.map((g, i) => [g, i]);
  const pics = all.filter(([g]) => g.kind !== "video").map(tile).join(""), vids = all.filter(([g]) => g.kind === "video").map(tile).join("");
  const chats = Object.fromEntries((S.state?.chats || []).map((c) => [c.id, c.title]));

  const track = (t) => `<div class="track song"><div class="track-head"><span class="track-title">♪ ${esc(t.title)}</span><span class="when">${esc(ago(t.when))}</span></div>
      <div class="track-about">${esc(t.style)} · ${esc(t.length || "")}</div>
      ${songAudio(t.file)}
      ${t.lyrics ? `<details class="track-more"><summary>${t.instrumental ? "Style" : "Lyrics and style"}</summary>
        ${t.caption ? `<div class="track-cap">“${esc(t.caption)}”</div>` : ""}
        <div class="track-style"><b>Style:</b> ${esc(t.style)}</div>
        ${t.instrumental ? `<div class="track-style dim">Instrumental: no singing.</div>` : `<pre class="track-lyrics">${esc(t.lyrics)}</pre>`}</details>` : ""}
      <div class="track-acts">${rateButtons(t.key)}${t.asked === "own time" ? `<span class="dim">on its own time</span>` : ""}
        <button class="btn" data-chat="${esc(t.chat)}" title="Open the chat it's in">in “${esc(chats[t.chat] || "a chat")}”</button></div></div>`;
  $("#center").innerHTML = `<div class="page"><h1>Creations</h1><p class="lead">What ${esc(name())} makes, all on this PC: pictures (Qwen-Image in ComfyUI, drawn in the background, never while you're gaming), songs (YuE2 in ComfyUI: its style and lyrics, a real track in a few minutes), and videos.</p>
    <div class="soon-list"><label><input type="checkbox" class="switch" id="imgOn" data-set="images_enabled" ${st.images_enabled ? "checked" : ""}> it can draw</label>
      · <label title="Short clips (Wan 2.2), only when you ask; never on its own. Slow on this card: about 10 minutes for 2 seconds."><input type="checkbox" class="switch" id="vidOn" data-set="videos_enabled" ${st.videos_enabled ? "checked" : ""}> it can make videos <span class="dim">(when you ask)</span></label>
      · <span id="imgToday"></span></div>
    <h3>WAITING</h3><div id="imgQueue"></div>
    <h3>PICTURES</h3>
    ${pics ? `<div class="img-grid">${pics}</div>` : `<div class="dim">Nothing yet. Ask it to draw you something, or it may surprise you.</div>`}
    <h3>MUSIC</h3>
    ${tracks.length ? `<div class="tracks">${tracks.map(track).join("")}</div>` : `<div class="dim">No songs yet. Ask it to make you one (drum & bass, trance, house, ambient...).</div>`}
    <h3>VIDEOS</h3>
    ${vids ? `<div class="img-grid">${vids}</div>` : `<div class="dim">None yet. ${st.videos_enabled ? "Ask it for a short clip (about 10 minutes for 2 seconds on this card)." : "Turn on \"it can make videos\" above, then ask it for one."}</div>`}</div>`;
  $("#imgOn").addEventListener("change", (e) => saveSetting(e.target));
  $("#vidOn").addEventListener("change", async (e) => { await saveSetting(e.target); renderImages(); });
  renderImageQueue(r.info);
}
function renderImageQueue(info) {
  info = info || S.state?.images;
  const q = $("#imgQueue");
  if (!q || !info) return;
  $("#imgToday").textContent = `${info.made_today} of ${info.cap} today` + (S.state?.settings?.videos_enabled ? ` · videos ${info.videos_today || 0} of ${info.video_cap}` : "");
  q.innerHTML = info.queue.length ? info.queue.map((j, i) => `<div class="fact"><span class="d">${esc(clock(j.asked))}</span>
      <span style="flex:1">${j.kind === "video" ? "▶ " : j.kind === "song" ? "♪ " : ""}${esc(j.caption || ({ video: "a video", song: "a song" })[j.kind] || "a picture")}${i === 0 && info.status ? ` · <span class="gold">${esc(info.status)}</span>` : i > 0 ? ' · <span class="dim">in line</span>' : ""}</span>
      <button class="btn" data-img-cancel="${esc(j.id)}">Cancel</button></div>`).join("")
    : `<div class="dim">Nothing waiting.</div>`;
}

function openLightbox(src) {
  $("#overlay").innerHTML = `<div class="lightbox" data-action="close" title="Click or Esc to close"><img src="${esc(src)}" alt=""></div>`;
}
function openImage(i) {
  const g = S.gallery?.[i];
  if (!g) return;
  const chat = (S.state?.chats || []).find((c) => c.id === g.chat);
  const src = `/api/attachment?t=${TOKEN}&p=${encodeURIComponent(g.image)}`;
  openModal(`<h2>${esc(g.title || g.caption || "untitled")}<button class="x" data-action="close">✕</button></h2>
    ${g.title && g.caption && g.caption !== g.title ? `<p class="img-words">“${esc(g.caption)}”</p>` : ""}
    ${g.kind === "video" && g.video
      ? `<video class="img-big" controls autoplay loop src="/api/attachment?t=${TOKEN}&p=${encodeURIComponent(g.video)}" poster="${src}"></video>`
      : `<img class="img-big" data-lightbox="${src}" src="${src}" alt="" title="Click for full size">`}
    <div class="dim small" style="margin-top:10px">${esc(new Date(g.made).toLocaleString())} · ${esc(g.shape)}${chat ? ` · in “${esc(chat.title)}”` : ""}</div>
    <div class="img-prompt"><span class="faint small">its prompt</span><br>${esc(g.prompt)}</div>
    <div style="display:flex;margin-top:14px">${chat ? `<button class="btn primary" data-img-chat="${esc(g.chat)}" style="margin-left:auto">Open the chat</button>` : ""}</div>`);
}

async function renderHeartbeat() {
  let L;
  try { L = await api("/api/life"); } catch (e) { return toast(e.message, true); }
  if (S.view !== "heartbeat") return;
  S.schedules = L.schedules || [];
  const st = S.state.settings;
  const nxt = L.wake_at ? new Date(L.wake_at) : L.next_heartbeat ? new Date(L.next_heartbeat) : null;

  const logRows = (L.log || []).slice().reverse().map((e) => `<div class="fact life-row" data-when="${esc(e.when)}" data-what="${esc(e.what)}"` +
    ` data-commits="${esc((e.commits || []).join(","))}"${e.commits ? ' data-exact="1"' : ""}><span class="d">${esc(e.when.slice(5, 16).replace("T", " "))}</span>` +
    `<span><b>${esc(e.what)}</b> · ${esc(e.detail)}</span><span class="go"></span></div>`).join("");
  const sched = (L.schedules || []).map((x) => `<div class="sched"><input type="checkbox" class="switch" data-sched="${esc(x.id)}" ${x.enabled ? "checked" : ""}>
      <div style="flex:1;min-width:0"><div><b>${esc(x.name)}</b> <span class="faint small" title="${esc(x.cron)}">${esc(cronHuman(x.cron))}</span>${x.speak ? ' <span class="pink small">speaks</span>' : ""}${x.voice ? ' <span class="pink small">voice clip</span>' : ""}${x.to ? ` <span class="cyan small">→ ${esc((REACH_TO.find(([k]) => k === x.to) || [0, x.to])[1])}</span>` : ""}</div>${(x.prompt || "").trim() ? `<div class="dim small ellip">${esc(x.prompt.split("\n").join(" "))}</div>` : '<div class="gold small">No note: it won\'t know what this is for. Edit it (✎) and give it one.</div>'}</div>
      <button class="btn" data-sched-edit="${esc(x.id)}" title="Edit">✎</button><button class="btn" data-sched-del="${esc(x.id)}" title="Delete">✕</button></div>`).join("");
  const ck = L.checkup;
  $("#center").innerHTML = `<div class="page"><h1>Heartbeat &amp; schedules</h1><p class="lead">${esc(name())}'s own clock. It only wakes up while Aether is open, never while you're typing or within ${st.heartbeat_idle_minutes} min of your last message. It messages you on its own only after ${st.message_idle_minutes ?? 30} quiet minutes, never during quiet hours, and at most ${st.reach_out_cap} times a day; in between, and while you sleep${st.sleep_work ? "" : " (off)"}, it works quietly. A message from you always comes first: whatever it's doing on its own stops for it.</p>
    <h3>${icon("heartpulse")}HEARTBEAT</h3>
    <div class="soon-list">${st.heartbeat_enabled ? `Every ${st.heartbeat_minutes} min · next: ${nxt ? nxt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "soon"}${L.gate ? ` · <span class="gold">waiting: ${esc(L.gate)}</span>` : ""}` : "Off (Settings → Life)"} · messages today: ${L.reach_outs} of ${L.cap}</div>
    <div class="soon-list" style="display:flex;align-items:center;gap:10px;margin-top:6px"><span style="white-space:nowrap">Its messages go to</span><span style="max-width:280px;flex:1">${reachSelect(st.reach_out_to)}</span></div>
    <div style="display:flex;gap:8px;margin-top:10px"><button class="btn primary" data-life="heartbeat">Wake it now</button><button class="btn" data-edit="life/heartbeat.md">✎ Edit what it does</button></div>
    <h3>${icon("alarm")}WAITING FOR YOUR YES</h3>
    ${(L.proposals || []).length ? L.proposals.map((x) => `<div class="sched"><div style="flex:1;min-width:0"><div><b>${esc(x.title)}</b> <span class="faint small">${esc(x.kind)}${x.status === "later" ? " · you said later" : ""}${x.delivered ? "" : " · not sent yet"}</span></div><div class="dim small">${esc(x.why)} Plan: ${esc(x.plan)}</div></div>
      <button class="btn primary" data-proposal="${esc(x.id)}" data-reply="yes">Yes</button><button class="btn" data-proposal="${esc(x.id)}" data-reply="no">No</button>${x.status === "later" ? "" : `<button class="btn" data-proposal="${esc(x.id)}" data-reply="later">Later</button>`}</div>`).join("")
      : `<div class="dim">Nothing right now. When one of its ideas needs your yes, it comes as a card in your chat and waits here too.</div>`}
    <h3>${icon("alarm")}ITS OWN WAKE-UPS</h3>
    ${(L.wakeups || []).length ? L.wakeups.map((w) => `<div class="sched"><div style="flex:1;min-width:0"><div><b>${esc(w.when)}</b></div><div class="dim small">“${esc(w.note)}”</div></div>
      <button class="btn" data-wake-cancel="${esc(w.id)}">Cancel</button></div>`).join("")
      : `<div class="dim">None set. It picks these itself: its own plans, or following up on something when it decides it matters.</div>`}
    <h3>${icon("bell")}REMINDERS</h3>
    ${sched || '<div class="dim">None yet.</div>'}
    <div style="display:flex;gap:8px;margin-top:10px"><button class="btn" data-action="add-sched">+ Add a reminder</button></div>
    <h3>${icon("moonstar")}NIGHTLY (at ${esc(st.dream_time)})</h3>
    <div style="display:flex;gap:8px"><button class="btn" data-life="reflect">Reflect now</button><button class="btn" data-life="checkup">Memory checkup now</button></div>
    <div style="margin-top:10px">${ck ? (ck.issues.length ? ck.issues.map((i) => `<div class="fact"><span class="d">${esc(i.kind)}</span><span>${esc(i.file)} · ${esc(i.detail)}</span></div>`).join("") : `<div class="dim">Last checkup ${esc(ck.when.slice(0, 16).replace("T", " "))}: memory looks healthy.</div>`) : '<div class="dim">No checkup yet.</div>'}</div>
    <h3>${icon("activity")}WHAT IT'S BEEN DOING</h3>${logRows || '<div class="dim">Nothing yet.</div>'}</div>`;
  $$("[data-sched]").forEach((el) => el.addEventListener("change", () => api("/api/life/schedule-update", { id: el.dataset.sched, enabled: el.checked }).then(() => toast("Saved")).catch((e) => toast(e.message, true))));
  $$('#center [data-set="reach_out_to"]').forEach((el) => el.addEventListener("change", () => saveSetting(el)));
  linkLifeRows();
}

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
function calDay(iso) { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); }
function calTime(hm) { if (!hm) return ""; const [h, m] = hm.split(":").map(Number); return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; }
function calLabel(iso, today) {
  const d = calDay(iso), t = calDay(today), days = Math.round((d - t) / 86400000);
  return days === 0 ? "Today" : days === 1 ? "Tomorrow" : d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}
function calIso(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }

function calNext(d, repeat) {
  if (repeat === "week" || repeat === "2 weeks") return new Date(d.getFullYear(), d.getMonth(), d.getDate() + (repeat === "week" ? 7 : 14));
  const y = repeat === "year" ? d.getFullYear() + 1 : d.getFullYear() + (d.getMonth() === 11 ? 1 : 0);
  const m = repeat === "year" ? d.getMonth() : (d.getMonth() + 1) % 12;
  return new Date(y, m, Math.min(d.getDate(), new Date(y, m + 1, 0).getDate()));
}
function calAt(at) { const [d, hm] = at.split(" "); return `${calDay(d).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })}, ${calTime(hm)}`; }

function calRow(e, today, on) {
  return `<div class="sched"><div style="flex:1;min-width:0"><div><b>${esc(calLabel(on || e.day, today))}${e.time ? `, ${esc(calTime(e.time))}` : ""}</b> · ${esc(e.what)} ${e.repeat ? `<span class="cyan small" title="the next time shows here; it moves on by itself">↻ every ${esc(e.repeat)}</span> ` : ""}<span class="faint small">${e.by === "user" ? "added by you" : e.by ? "added by " + esc(name()) : ""}</span></div>
      ${e.reminders.length ? `<div class="dim small">${icon("bell")} ${e.reminders.map((x) => x.done ? `<s>${esc(calAt(x.at))}</s>` : esc(calAt(x.at))).join(" · ")}</div>` : '<div class="faint small">noted, no reminder</div>'}</div>
      <button class="btn" data-cal-edit="${esc(e.id)}" title="Edit">✎</button><button class="btn" data-cal-del="${esc(e.id)}" title="Cancel it">✕</button></div>`;
}

function viewCalendarDay(day) {
  const es = (S.calByDay || {})[day] || [], open = day >= (S.calToday || "");
  if (!es.length) return open ? addCalendar(null, day) : undefined;
  openModal(`<h2>${esc(calDay(day).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }))}<button class="x" data-action="close">✕</button></h2>
    <div style="margin-top:10px">${es.map((e) => calRow(e, S.calToday, day)).join("")}</div>
    ${open ? `<div style="display:flex;margin-top:16px"><button class="btn primary" data-cal-add-on="${esc(day)}" style="margin-left:auto">+ Add on this day</button></div>` : ""}`);
}
async function renderCalendar() {
  let r;
  try { r = await api("/api/calendar"); } catch (e) { return toast(e.message, true); }
  if (S.view !== "calendar") return;
  S.cal = r.entries;
  S.calToday = r.today;
  const today = r.today, t0 = calDay(today);
  if (!S.calMonth) S.calMonth = [t0.getFullYear(), t0.getMonth()];
  const [y, mo] = S.calMonth;
  const first = new Date(y, mo, 1), lead = (first.getDay() + 6) % 7, n = new Date(y, mo + 1, 0).getDate();

  const byDay = {}, last = new Date(y, mo + 1, 0);
  r.entries.forEach((e) => {
    let d = calDay(e.day), n = 0;
    do {
      if (d >= first) (byDay[calIso(d)] = byDay[calIso(d)] || []).push(e);
      d = e.repeat ? calNext(d, e.repeat) : null;
    } while (d && d <= last && ++n < 400);
  });
  let cells = "";
  for (let i = 0; i < lead; i++) cells += `<div class="cal-cell off"></div>`;
  for (let d = 1; d <= n; d++) {
    const iso = `${y}-${String(mo + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`, es = byDay[iso] || [];
    cells += `<div class="cal-cell${iso === today ? " today" : ""}${iso < today ? " past" : ""}${es.length ? " has" : ""}" data-cal-day="${iso}" title="${esc(es.map((e) => (e.time ? calTime(e.time) + " " : "") + e.what).join("\n"))}">
      <span class="n">${d}</span>${es.slice(0, 2).map((e) => `<span class="cal-dot">${esc(e.what)}</span>`).join("")}${es.length > 2 ? `<span class="faint small">+${es.length - 2}</span>` : ""}</div>`;
  }
  S.calByDay = byDay;
  const row = (e) => calRow(e, today);
  const ahead = r.entries.filter((e) => e.day >= today), past = r.entries.filter((e) => e.day < today).reverse();
  $("#center").innerHTML = `<div class="page"><h1>Calendar</h1><p class="lead">Dates you two share. ${esc(name())} sees the next two weeks all the time, and can add, move or cancel things too (tell it in chat). A reminder goes off a week before and 4 hours before unless you pick otherwise; one missed while Aether was closed goes off when it's open again, if the day hasn't passed. Every change is a commit you can rewind on the Brain page.</p>
    ${S.state?.settings?.calendar_enabled === false ? '<div class="gold small">The calendar is off (Settings → Life).</div>' : ""}
    <div class="cal-head"><button class="btn" data-cal-month="-1">‹</button><b>${MONTH_NAMES[mo]} ${y}</b><button class="btn" data-cal-month="1">›</button>
      <button class="btn primary" data-action="add-cal" style="margin-left:auto">+ Add a date</button></div>
    <div class="cal-grid">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => `<div class="cal-dow">${d}</div>`).join("")}${cells}</div>
    <h3>${icon("calendar")}COMING UP</h3>${ahead.map(row).join("") || '<div class="dim">Nothing yet. Add a date, or tell it about one.</div>'}
    ${past.length ? `<h3 class="toggle" data-action="toggle-cal-past">${icon("archive")}PAST (${past.length}) ${S.calPast ? "▾" : "▸"}</h3>${S.calPast ? past.map(row).join("") : ""}` : ""}</div>`;
}

async function addCalendar(x, day) {
  const rem = x ? `<option value="keep" selected>${x.reminders.length ? "keep (they move with the date)" : "keep as is (none)"}</option>` : "";
  openModal(`<h2>${x ? "Edit date" : "New date"}<button class="x" data-action="close">✕</button></h2>
    <div class="form" style="margin-top:16px;grid-template-columns:120px 1fr"><label>What</label><input class="field" id="cWhat" placeholder="e.g. Haircut appointment" value="${esc(x ? x.what : "")}">
      <label>Day</label><input class="field" type="date" id="cDate" value="${esc(x ? x.day : day || S.calToday || "")}">
      <label>Time</label><div><input class="field" type="time" id="cTime" value="${esc(x ? x.time : "")}"> <span class="dim small">leave empty for all day</span></div>
      <label>Repeats</label><select class="field" id="cRepeat">${[["", "never"], ["week", "every week"], ["2 weeks", "every 2 weeks"], ["month", "every month"], ["year", "every year"]]
        .map(([v, l]) => `<option value="${v}" ${(x ? x.repeat || "" : "") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Remind</label><div><select class="field" id="cRemind">${rem}<option value="yes" ${x ? "" : "selected"}>a week before + 4 hours before (the evening before, if no time)</option>
        <option value="the day before">the evening before</option><option value="2 hours before">2 hours before</option><option value="no">no reminder, just noted</option><option value="custom">my own words…</option></select>
        <input class="field" id="cRemindWords" placeholder="e.g. 3 days before and the morning of" style="display:none;margin-top:6px"></div></div>
    <div style="display:flex;margin-top:18px"><button class="btn" data-action="close" style="margin-left:auto">Cancel</button><button class="btn primary" style="margin-left:10px" id="cSave">Save</button></div>`);
  $("#cRemind").onchange = () => ($("#cRemindWords").style.display = $("#cRemind").value === "custom" ? "" : "none");
  $("#cSave").onclick = async () => {
    const pick = $("#cRemind").value;
    const body = { id: x ? x.id : "", what: $("#cWhat").value.trim(), date: $("#cDate").value, time: $("#cTime").value,
      repeat: $("#cRepeat").value, remind: pick === "custom" ? $("#cRemindWords").value.trim() : pick };
    try {
      await api(`/api/life/calendar-${x ? "change" : "add"}`, body);
      closeOverlay(); toast("Saved"); renderCalendar();
    } catch (e) { toast(e.message, true); }
  };
}

async function linkLifeRows() {
  const rows = $$(".life-row");
  if (rows.some((r) => !r.dataset.exact)) {
    const commits = await api("/api/commits?n=80").catch(() => []);
    rows.filter((r) => !r.dataset.exact && /^(woke|dreamed|reflected|reminder)$/.test(r.dataset.what)).forEach((r) => {
      const end = new Date(r.dataset.when).getTime();
      r.dataset.commits = commits.filter((c) => c.author !== "user" && c.iso &&
        new Date(c.iso).getTime() >= end - 3 * 60000 && new Date(c.iso).getTime() <= end + 60000)
        .map((c) => c.hash).reverse().join(",");
    });
  }
  rows.forEach((r) => {
    const n = r.dataset.commits ? r.dataset.commits.split(",").length : 0;
    const go = n ? `${n} change${n > 1 ? "s" : ""} →` : r.dataset.what === "woke" ? "its notes →" : "";
    if (go) { r.classList.add("link"); $(".go", r).textContent = go; }
  });
}
function openLifeRow(r) {
  const hashes = (r.dataset.commits || "").split(",").filter(Boolean);
  if (hashes.length) { B.pending = hashes; return showView("brain"); }
  if (r.dataset.what === "woke") return openChat("heartbeat");
}

const DAYS = [[1, "Mon"], [2, "Tue"], [3, "Wed"], [4, "Thu"], [5, "Fri"], [6, "Sat"], [0, "Sun"]];

function parseCron(cron) {
  const m = String(cron).trim().split(/\s+/);
  if (m.length !== 5 || m[2] !== "*" || m[3] !== "*" || !/^\d+$/.test(m[0]) || !/^\d+$/.test(m[1])) return null;
  const days = new Set();
  for (const part of m[4].split(",")) {
    if (part === "*") [0, 1, 2, 3, 4, 5, 6].forEach((d) => days.add(d));
    else if (/^\d-\d$/.test(part)) { const [a, b] = part.split("-").map(Number); for (let d = a; d <= b; d++) days.add(d % 7); }
    else if (/^\d$/.test(part)) days.add(+part % 7);
    else return null;
  }
  return { min: +m[0], hour: +m[1], days };
}
function cronHuman(cron) {
  const c = parseCron(cron);
  if (!c) return cron;
  const t = `${c.hour % 12 || 12}:${String(c.min).padStart(2, "0")} ${c.hour < 12 ? "AM" : "PM"}`;
  const key = [...c.days].sort().join(",");
  const days = key === "0,1,2,3,4,5,6" ? "every day" : key === "1,2,3,4,5" ? "weekdays" : key === "0,6" ? "weekends"
    : DAYS.filter(([n]) => c.days.has(n)).map(([, l]) => l).join(", ");
  return `${t} · ${days}`;
}

async function addSchedule(x) {
  const c = x ? parseCron(x.cron) : { min: 30, hour: 20, days: new Set([1, 2, 3, 4, 5]) };
  const h12 = c ? c.hour % 12 || 12 : 8, pm = c ? c.hour >= 12 : true;
  const mins = Array.from({ length: 12 }, (_, i) => i * 5);
  if (c && !mins.includes(c.min)) mins.push(c.min), mins.sort((a, b) => a - b);
  const when = c ? `<label>Time</label><div class="when-row"><select class="field" id="sHour">${[12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map((h) => `<option value="${h}" ${h === h12 ? "selected" : ""}>${h}</option>`).join("")}</select>
        <span class="dim">:</span><select class="field" id="sMin">${mins.map((m) => `<option value="${m}" ${m === c.min ? "selected" : ""}>${String(m).padStart(2, "0")}</option>`).join("")}</select>
        <select class="field" id="sAmPm"><option ${pm ? "" : "selected"}>AM</option><option ${pm ? "selected" : ""}>PM</option></select></div>
      <label>Days</label><div><div class="day-row">${DAYS.map(([n, l]) => `<button type="button" class="day ${c.days.has(n) ? "on" : ""}" data-day="${n}">${l}</button>`).join("")}</div>
        <div class="day-quick"><button type="button" class="btn small-btn" data-days="0,1,2,3,4,5,6">Every day</button><button type="button" class="btn small-btn" data-days="1,2,3,4,5">Weekdays</button><button type="button" class="btn small-btn" data-days="0,6">Weekends</button></div></div>`
    : `<label>Time pattern</label><div><input class="field mono" id="sCron" value="${esc(x.cron)}"><div class="hint">minute hour day month weekday (cron)</div></div>`;
  openModal(`<h2>${x ? "Edit reminder" : "New reminder"}<button class="x" data-action="close">✕</button></h2>
    <div class="form" style="margin-top:16px;grid-template-columns:120px 1fr"><label>Name</label><input class="field" id="sName" placeholder="e.g. Plants" value="${esc(x ? x.name : "")}">
      ${when}
      <label>What it does</label><textarea class="field" id="sPrompt" rows="4" placeholder="e.g. Remind me to water the plants before work.">${esc(x ? x.prompt || "" : "")}</textarea>
      <label>Sends to</label><select class="field" id="sTo"><option value="">wherever its messages go (${esc((REACH_TO.find(([k]) => k === (S.state.settings.reach_out_to || "latest")) || [0, "your latest chat"])[1])})</option>${REACH_TO.map(([k, l]) => `<option value="${k}" ${x && x.to === k ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Voice</label><div class="voice-opts"><label><input type="checkbox" class="switch" id="sVoice" ${x && x.voice ? "checked" : ""}> voice clip on Discord <span class="dim small">(text plus a clip you can play on your phone)</span></label>
        <label><input type="checkbox" class="switch" id="sSpeak" ${x && x.speak ? "checked" : ""}> say it out loud on the PC</label></div></div>
    <div style="display:flex;margin-top:18px"><button class="btn" data-action="close" style="margin-left:auto">Cancel</button><button class="btn primary" style="margin-left:10px" id="sSave">Save</button></div>`);
  $$(".day-row .day").forEach((b) => (b.onclick = () => b.classList.toggle("on")));
  $$(".day-quick [data-days]").forEach((b) => (b.onclick = () => {
    const pick = b.dataset.days.split(",");
    $$(".day-row .day").forEach((d) => d.classList.toggle("on", pick.includes(d.dataset.day)));
  }));
  $("#sSave").onclick = async () => {
    let cron;
    if ($("#sCron")) cron = $("#sCron").value.trim();
    else {
      const days = $$(".day-row .day.on").map((d) => d.dataset.day);
      if (!days.length) return toast("Pick at least one day", true);
      const hour = (+$("#sHour").value % 12) + ($("#sAmPm").value === "PM" ? 12 : 0);
      cron = `${+$("#sMin").value} ${hour} * * ${days.length === 7 ? "*" : days.sort().join(",")}`;
    }

    if (!$("#sPrompt").value.trim()) { $("#sPrompt").focus(); return toast("Tell it what to do when it goes off (the grey text is only an example)", true); }
    const body = { name: $("#sName").value, cron, prompt: $("#sPrompt").value, to: $("#sTo").value, voice: $("#sVoice").checked, speak: $("#sSpeak").checked };
    try {
      await api(x ? "/api/life/schedule-update" : "/api/life/schedule-add", x ? { id: x.id, ...body } : body);
      closeOverlay(); showView("heartbeat"); if (x) toast("Saved");
    } catch (e) { toast(e.message, true); }
  };
}
function notify(title, body) {
  toast(`${title}: ${body.slice(0, 90)}`);
  try {
    if (document.hidden && "Notification" in window) {
      if (Notification.permission === "granted") new Notification(title, { body, icon: picUrl() });
      else if (Notification.permission !== "denied") Notification.requestPermission();
    }
  } catch (e) {  }
}

async function discordStatus() {
  const d = await api("/api/discord").catch(() => null);
  const el = $("#discordState");
  if (!d || !el) return;
  el.textContent = !d.enabled ? (d.has_token ? "off" : "off · no bot token yet (How to set up a Discord bot)") : d.connected ? `connected as ${d.bot}` : (d.error || "connecting…");
  if (d.enabled && !d.connected && S.view === "settings") setTimeout(discordStatus, 4000);
}

async function renderVault() {
  const el = $("#vaultList");
  if (!el) return;
  const items = await api("/api/vault").catch(() => []);
  el.innerHTML = items.length ? items.map((v) => `<div class="sched"><span class="mono">${esc(v.name)}</span><span class="dim small">${esc(v.hint)}${v.note ? " · " + esc(v.note) : ""}</span>
      <span style="margin-left:auto" class="small dim">${v.skills.length ? "used by " + esc(v.skills.join(", ")) : "no skill uses it"}</span>
      <button class="btn" data-vremove="${esc(v.name)}" title="Remove">✕</button></div>`).join("") : `<div class="dim">No secrets saved.</div>`;
  $$("[data-vremove]", el).forEach((b) => b.addEventListener("click", async () => {
    if (await confirmBox(`Remove ${b.dataset.vremove}?`, "Skills that use it stop getting it. This can't be undone from here (the old value isn't kept).")) {
      api("/api/vault/remove", { name: b.dataset.vremove }).then(renderVault).catch((e) => toast(e.message, true));
    }
  }));
}
async function backupNow() {
  toast("Backing up…");
  try { const r = await api("/api/backup", {}); toast(`Backed up: ${(r.size / 1e6).toFixed(1)} MB in Aether Backups`); if (S.view === "settings") renderSettings(); }
  catch (e) { toast(e.message, true); }
}
async function auditLog() {
  const rows = await api("/api/audit").catch(() => []);
  openModal(`<h2>Everything it did<button class="x" data-action="close">✕</button></h2>
    <p class="dim small">Every step, newest first (the last 300). Also in ~/.aether/logs/audit.jsonl.</p>
    <div style="max-height:60vh;overflow:auto">${rows.map((r) => `<div class="fact"><span class="d">${esc(r.ts.slice(5, 16).replace("T", " "))}</span>
      <span><b style="color:${r.ok ? "var(--green)" : "var(--red)"}">${r.ok ? "✓" : "✕"}</b> ${esc(r.step.step)} ${esc(r.step.skill || r.step.file || r.step.path || r.step.query || "")} ${esc([r.step.command, ...(r.step.args || [])].filter(Boolean).join(" "))}
      <span class="faint small"> · ${esc(r.place || "")}</span><div class="dim small">${esc((r.result || "").slice(0, 160))}</div></span></div>`).join("") || '<div class="dim">Nothing yet.</div>'}</div>`);
}

const KNOW = [
  ["system/human/facts.md", "THINGS YOU TOLD IT", "Nothing yet: it adds a dated line when you tell it something that lasts."],
  ["system/human.md", "ITS READ ON YOU", "Nothing yet: its own notes on what you're like and how to be with you."],
  ["system/persona.md", "PERSONALITY", "Empty: write who it is and how it talks."],
  ["system/rules.md", "RULES", "No house rules yet."],
];
async function renderKnow() {
  const c = $("#center");
  c.innerHTML = `<div class="page"><h1>What Aether knows about you</h1><p class="lead">Straight from its memory files. It keeps its facts about you up to date (old versions go to reference/facts-history.md). Its personality and rules are yours to set: it follows them but can't change them. Every edit is a change you can rewind on the Brain page.</p><div id="knowBody" class="dim">Loading…</div></div>`;
  const parts = [];
  for (const [path, title, empty] of KNOW) {
    try {
      const f = await api(`/api/file?path=${encodeURIComponent(path)}`);
      const body = f.text.replace(/^---\n[\s\S]*?\n---\n/, "");
      const lines = body.split("\n").filter((l) => l.trim() && !/^\*\*[^*]+:\*\*\s*$/.test(l.trim()));
      let inner;
      if (!lines.length) inner = `<div class="dim">${esc(empty)}</div>`;
      else if (path.endsWith("facts.md")) {
        inner = lines.map((l) => { const m = l.match(/^\s*-\s*(\d{4}-\d{2}-\d{2}):\s*(.*)$/); return m ? `<div class="fact"><span class="d">${m[1]}</span><span>${esc(m[2])}</span></div>` : `<div class="fact"><span>${esc(l)}</span></div>`; }).join("");
      } else inner = `<div class="prose">${esc(body.trim())}</div>`;
      parts.push(`<h3>${title} <button class="btn" style="margin-left:10px;padding:2px 10px" data-edit="${esc(path)}">✎ Edit</button></h3>${inner}`);
    } catch (e) { parts.push(`<h3>${title}</h3><div class="dim">${esc(path)} isn't in its memory yet (it comes with the starter memory, starter-memory/ in the project).</div>`); }
  }
  if (S.view === "know") $("#knowBody").outerHTML = parts.join("");
}

const BUILT_IN = [
  { step: "memory_*", title: "Memory", desc: "Add, change or remove lines in its memory files, or start a new note. Every change is its own git commit (rewind on the Brain page)." },
  { step: "recall", title: "Recall", desc: "Search everything you two ever said, in every chat, and all its memory, by meaning.", set: "recall_enabled" },
  { step: "read_chat", title: "Read a chat", desc: "Open one of its other chats with you (by part of its title, or the last one) and read what was actually said, like scrolling back.", note: "always on" },
  { step: "wake_me", title: "Its own wake-ups", desc: "Pick a time to wake up with a note to itself: its own plans, or following up on something when it decides it matters. One-time, up to 3, never during your sleep; they show on the Heartbeat page.", set: "wakeups_enabled", link: "heartbeat" },
  { step: "calendar", title: "Calendar", desc: "Add, move or cancel dates on the calendar you share, with or without a reminder. It writes your words for the day (\"tuesday at 10\"); Aether works out the date and it says it back so you can fix it.", set: "calendar_enabled", link: "calendar" },
  { step: "set_mood", title: "Moods", desc: "Choose its own mood when it genuinely feels different. It fades on its own (by half every 1.5 hours).", set: "mood_enabled" },
  { step: "make_image", title: "Pictures", desc: "Draw a picture on this PC (Qwen-Image in ComfyUI). It writes the prompt; it's drawn in the background, never while you game, and it looks at it before you see it.", set: "images_enabled", link: "images" },
  { step: "webcam", title: "Its eyes", desc: "One picture through your webcam when you ask it to look (\"how do I look?\", \"what am I holding?\"), and it says what it sees. Only in the app, never on Discord or on its own; the camera's light is on for the second or two it takes. Not kept as a picture of you: the frame is deleted once it's answered.", set: "eyes_enabled" },
  { step: "gallery", title: "Gallery", desc: "Look back at the pictures it's made, and really see one again.", note: "always on; empty until it draws", link: "images" },
  { step: "journal", title: "Journal", desc: "Its private scratchpad: feelings, brainstorms, questions it keeps turning over. It picks what it's about, then writes the entry fresh in a second pass (like a reply), and one that recycles its old sentences gets a second try. Saved by the journal skill's script.", note: "always on" },
  { step: "save_research", title: "Research notebook", desc: "Keeps what it reads in your Drop box: what the source says (with its file) and its own take, under one of its topics in reference/research/. It picks the step, then writes the topic, the point and its take in a second pass; Aether adds the file it actually read as the source, and the research skill's script saves it as one commit (rewind on the chip). When you ask it to save to its research and it goes to reply or journal instead, Aether takes the step for it first (the chip says so).", note: "on with the research skill" },
  { step: "make_video", title: "Videos", desc: "Make a short clip on this PC (Wan 2.2 in ComfyUI), or bring one of its pictures to life. Only when you ask; never on its own. Made in the background, never while you game, about 10 minutes for 2 seconds on this card. Off until better hardware or a faster model.", set: "videos_enabled", link: "images" },
  { step: "shell", title: "Command line", desc: "Run PowerShell commands on your PC, only as far as its level allows. Some commands always ask you first.", level: true },
];
function builtinCard(b) {
  const st = S.state?.settings || {};
  const lvl = appLevel();
  const ctl = b.set ? `<label class="small"><input type="checkbox" class="switch" data-set="${b.set}" ${st[b.set] ? "checked" : ""}> ${st[b.set] ? "on" : "off"}</label>`
    : b.level ? `<span class="small ${lvl ? "cyan" : "dim"}">level ${lvl} · ${esc(levelName(lvl))}</span> <button class="btn small-btn" data-view="settings">change</button>`
      : `<span class="dim small">${esc(b.note || "always on")}</span>`;
  return `<div class="scard builtin"><h4>${esc(b.title)}<span class="tag">built in</span></h4><p>${esc(b.desc)}</p>
    <div class="builtin-row"><span class="mono">step: ${esc(b.step)}</span><span style="margin-left:auto">${ctl}</span>${b.link ? ` <button class="btn small-btn" data-view="${b.link}">open</button>` : ""}</div></div>`;
}

async function renderSkills() {
  const c = $("#center");
  c.innerHTML = `<div class="page"><h1>Skills</h1><p class="lead">Built-in abilities live in Aether itself (they need things a script can't do, like finishing later or showing it a picture). Skills are folders you add: each has a SKILL.md with a name and a description, a script that runs, and a page that shows how to call it. Aether checks each one; only skills that pass are live. New ones show up here first, with what they can do.</p><div id="skillBody" class="dim">Loading…</div></div>`;
  try {
    const s = await api("/api/skills");
    S.skills = s;
    const card = (k) => `<div class="scard"><h4>${esc(k.name)}${k.ask_first.length ? `<span class="tag">asks first: ${esc(k.ask_first.join(", "))}</span>` : ""}</h4><p>${esc(k.description)}</p><div class="mono">${esc(k.scripts.join(" · "))}</div></div>`;
    const bad = (k) => `<div class="scard bad"><h4>${esc(k.name)} <span class="tag">left out</span></h4><p>${esc(k.problems.join("; "))}</p></div>`;

    const added = (k) => `<div class="scard added"><h4>${esc(k.name)}<span class="tag">new</span></h4><p>${esc(k.description)}</p>
      ${k.commands.length ? `<div class="cmds">${k.commands.map((x) => `<div class="mono" title="${esc(x.example)}">${x.command ? esc(x.command) : "(no command)"}<span class="faint"> · ${esc(x.example)}</span></div>`).join("")}</div>` : `<div class="mono">its page shows no step example</div>`}
      <div style="display:flex;margin-top:10px"><button class="btn small-btn" style="margin-left:auto" data-seen="${esc(k.name)}">Got it</button></div></div>`;
    const fresh = s.new || [];
    if (S.view === "skills") $("#skillBody").outerHTML = (fresh.length ? `<h3>WHAT GOT ADDED (${fresh.length})${fresh.length > 1 ? ` <button class="btn small-btn" style="margin-left:10px" data-seen="*">Got it, all</button>` : ""}</h3><div class="cards">${fresh.map(added).join("")}</div>` : "") +
      `<h3>BUILT IN (${BUILT_IN.length})</h3><div class="cards">${BUILT_IN.map(builtinCard).join("")}</div>` +
      `<h3>SKILLS: LIVE (${s.live.filter((k) => !k.builtin).length})</h3><div class="cards">${s.live.filter((k) => !k.builtin).sort((a, b) => a.name.localeCompare(b.name)).map(card).join("")}</div>` +
      (s.left_out.length ? `<h3>LEFT OUT (${s.left_out.length})</h3><div class="cards">${s.left_out.map(bad).join("")}</div>` : "");
    $$(".scard.builtin [data-set]").forEach((el) => el.addEventListener("change", async () => { await saveSetting(el); if (S.view === "skills") renderSkills(); }));
    $$("[data-seen]").forEach((b) => b.addEventListener("click", async () => {
      const names = b.dataset.seen === "*" ? fresh.map((k) => k.name) : [b.dataset.seen];
      try { await api("/api/skills/seen", { names }); S.skills = null; renderSkills(); } catch (e) { toast(e.message, true); }
    }));
  } catch (e) { toast(e.message, true); }
}

async function renderSettings() {
  const st = S.state.settings;
  const brain = await api("/api/models").catch(() => ({ models: [], state: {}, error: "Aether didn't answer" }));
  const scores = await api("/api/model-scores").catch(() => ({}));
  S.brainScores = scores;
  const later = (title, phase, items) => `<h3>${title} <span class="phase" style="margin:0 0 0 8px">${phase}</span></h3><div class="soon-list">${items}</div>`;
  $("#center").innerHTML = `<div class="page"><h1>Settings</h1><p class="lead">Changes save as you make them, into ~/.aether/aether.json.</p>
    <h3>${icon("gear")}GENERAL</h3><div class="form">
      <label>Your name</label><input class="field" data-set="user_name" value="${esc(st.user_name || "User")}">
      <div class="hint">what it calls you: it's in its instructions and on your messages</div>
      <label>Its name</label><input class="field" data-set="display_name" value="${esc(st.display_name)}">
      <label>Tagline</label><input class="field" data-set="tagline" value="${esc(st.tagline)}">
      <label>Theme</label><select class="field" data-set="theme">${THEMES.map(([v, l]) => `<option value="${v}" ${(st.theme || "astral") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Space intensity</label><input type="range" min="0" max="1" step="0.05" data-set="space_intensity" value="${st.space_intensity}">
      <label>Show its work</label><div><input type="checkbox" class="switch" data-set="show_work" ${st.show_work ? "checked" : ""}> <span class="dim small">skill runs and reads in the chat (memory saves always show)</span></div>
      <label>Drop box</label>${folderField("library", "library_dir", st.library_dir)}
      <div class="hint">the folder of things you give it to read (PDFs, notes, articles): its research skill reads it. Made when it's first opened</div>
    </div>
    <h3>${icon("brain")}BRAIN</h3><div class="form">
      <label>Brain</label><div id="brainBox">${brainList(brain)}</div>
      <div class="hint">the chat models you've downloaded in LM Studio · a swap unloads the old one first (one graphics card) · run its test after</div>
      <label>Talking creativity</label><input class="field" type="number" min="0" max="2" step="0.05" data-set="temperature_talk" value="${st.temperature_talk}">
      <div class="hint">its replies; higher is looser (1.0 is a good start)</div>
      <label>Tool-choice creativity</label><input class="field" type="number" min="0" max="2" step="0.05" data-set="temperature_tools" value="${st.temperature_tools}">
      <div class="hint">picking steps; low = steady</div>
      <label>Steps per reply</label><input class="field" type="number" min="1" max="30" data-set="max_steps" value="${st.max_steps}">
      <label>Chat kept in view</label><input class="field" type="number" min="4000" step="1000" data-set="history_chars" value="${st.history_chars}">
      <div class="hint">characters of the chat it sees (~4 per token); older turns drop off</div>
      <label>Reply length limit</label><input class="field" type="number" min="100" step="50" data-set="reply_max_tokens" value="${st.reply_max_tokens}">
      <label>Skill time limit</label><input class="field" type="number" min="5" data-set="skill_timeout" value="${st.skill_timeout}">
    </div>
    <h3>${icon("shieldcheck")}PERMISSIONS</h3><div class="form"><label>Levels</label><div><button class="btn" data-action="permissions">App ${st.permission_levels.app} · Discord ${st.permission_levels.discord} · Avatar ${st.permission_levels.avatar} · Own time ${st.permission_levels.own || 0} · change…</button></div>
      <label>Workspace</label>${folderField("workspace", "workspace_dir", st.workspace_dir)}<div class="hint">its own folder: level 2 works only inside it. Made when it's first opened</div></div>
    <h3>${icon("cpu")}MEMORY</h3><div class="soon-list">Memory folder: <span class="mono">${S.state.agent.memory_mode === "home" ? "~/.aether/memory (its home)" : esc(S.state.agent.memory_mode)}</span>. Every change is a git commit you can rewind on the Brain page.</div>
    <div class="form" style="margin-top:12px">
      <label>Its eyes</label><div><input type="checkbox" class="switch" data-set="eyes_enabled" ${st.eyes_enabled ? "checked" : ""}> <span class="dim small">its look step: one webcam picture when you ask it to look, in the app only (off = its eyes closed)</span></div>
      <label>Search by meaning</label><div><input type="checkbox" class="switch" data-set="recall_enabled" ${st.recall_enabled ? "checked" : ""}> <span class="dim small">its recall step + "≈ by meaning" in search (nomic in LM Studio)</span></div>
      <label>Sharper search</label><div><input type="checkbox" class="switch" data-set="recall_hybrid" ${st.recall_hybrid ? "checked" : ""}> <span class="dim small">when it searches, exact names too, and your own words, not just its own (only when it chooses to look)</span></div>
      <label>Connect the dots</label><div><input type="checkbox" class="switch" data-set="recall_links" ${st.recall_links ? "checked" : ""}> <span class="dim small">its best search results bring along what's linked to them: the message right next to it in that chat, and other pieces with the same name</span></div>
      <label>Backups</label><div><button class="btn" id="backupBtn">⤓ Back up now</button> <span class="dim small" id="backupInfo"></span></div>
    </div>
    <div class="soon-list" style="margin-top:14px">The memory layers: each has a switch; every Keeper change can be rewound.</div>
    <div class="form" style="margin-top:8px">
      <label>What comes to mind</label><div><input type="checkbox" class="switch" data-set="cue_enabled" ${st.cue_enabled ? "checked" : ""}> <span class="dim small">before it answers you, up to ${st.cue_max} memories that fit (the 🧠 chip; ✗ wrong keeps one away)</span></div>
      <label>Whole messages in search</label><div><input type="checkbox" class="switch" data-set="recall_full_text" ${st.recall_full_text ? "checked" : ""}> <span class="dim small">long messages searchable to the end (goes with the above)</span></div>
      <label>Journal in its head</label><input class="field" type="number" min="0" data-set="prompt_journal_days" value="${st.prompt_journal_days}">
      <div class="hint">days of its journal it holds every reply (0 = all); older entries still come to mind</div>
      <label>…at most</label><input class="field" type="number" min="0" step="500" data-set="prompt_journal_chars" value="${st.prompt_journal_chars}">
      <div class="hint">characters of it (0 = no cap)</div>
      <label>Key rules again at the end</label><div><input type="checkbox" class="switch" data-set="prompt_recap" ${st.prompt_recap ? "checked" : ""}> <span class="dim small">where a small model weighs them most</span></div>
      <label>The Keeper</label><div><input type="checkbox" class="switch" data-set="keeper_enabled" ${st.keeper_enabled ? "checked" : ""}> <span class="dim small">each afternoon, its notebook from your chats: a dated timeline, what's coming up for you, its takes</span></div>
      <label>…and the board check</label><div><input type="checkbox" class="switch" data-set="keeper_board_check" ${st.keeper_board_check ? "checked" : ""}> <span class="dim small">board lines the timeline says are out of date, which it then fixes itself (off by default: it was often wrong in testing)</span></div>
      <label>Timeline in its head</label><input class="field" type="number" min="0" data-set="prompt_timeline_days" value="${st.prompt_timeline_days}">
      <div class="hint">days of the timeline it holds every reply (0 = all)</div>
      <label>…at most</label><input class="field" type="number" min="0" step="500" data-set="prompt_timeline_chars" value="${st.prompt_timeline_chars}">
      <div class="hint">characters of it (0 = no cap)</div>
      <label>Check-ins</label><div><input type="checkbox" class="switch" data-set="nudge_enabled" ${st.nudge_enabled ? "checked" : ""}> <span class="dim small">after something on your calendar (an appointment, a plan) it may check in; never in quiet hours</span></div>
    </div>
    <h3>${icon("image")}AVATAR</h3><div class="form">
      <label>Show an avatar</label><div><input type="checkbox" class="switch" data-set="avatar_enabled" ${st.avatar_enabled ? "checked" : ""}> <span class="dim small">a Live2D model in the right panel and in pet mode (Cubism 3/4; the Live2D runtime goes in aether/vendor, see the README)</span></div>
      <label>Avatars</label><div id="avList" class="dim small">…</div>
      <label>Add one</label><div><div style="display:flex;gap:8px;flex-wrap:wrap">
        <input class="field mono" id="avPath" placeholder="a folder or .zip with a .model3.json" style="flex:1;min-width:240px">
        <input class="field" id="avName" placeholder="name (optional)" style="width:160px"><button class="btn primary" id="avAdd">Add</button></div>
        <div class="dim small">copied into your data folder (not the project); checked first: every file the model needs, nothing unpacked outside its folder, 300 MB at most. Only models you have the right to use.</div></div>
      <label>Preview</label><div id="avPreview" class="dim small">…</div>
    </div>
    <h3>${icon("mic")}VOICE &amp; EARS</h3>
    <div class="soon-list" style="margin-bottom:10px">Its voice comes from a <b>voice server</b>: a speech program running on this PC that turns its replies into sound. Aether talks to it at the address below. Nothing is sent off this PC; with no voice server its replies are text only.</div>
    <div class="form">
      <label>Speak replies</label><select class="field" data-set="speak_replies">${[["when_i_talk", "when I talk to it out loud"], ["always", "always"], ["never", "never"]].map(([v, l]) => `<option value="${v}" ${st.speak_replies === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Voice</label><select class="field" data-set="voice_engine">${[["kokoro", "a voice server on this PC"], ["breeze", "Breeze (copies a voice from a clip; needs voice-engine/)"]].map(([v, l]) => `<option value="${v}" ${st.voice_engine === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <div class="hint">${st.voice_engine === "breeze" ? esc(voiceLine(S.state.services.voice || {})) + " Its mood colors how it says each sentence." : "any speech program on this PC that speaks the common /v1/audio/speech format (Kokoro-FastAPI and many others); local only, no cloud voices"}</div>
      ${st.voice_engine === "breeze" ? `<label>Breeze voice</label><input class="field mono" data-set="breeze_voice" value="${esc(st.breeze_voice)}">
      <div class="hint">a clip's name in voice-engine/voices/ (its words on a line in voices/prompt_text); applies from its next sentence</div>` : ""}
      ${st.voice_engine === "kokoro" ? `<label>Server address</label><input class="field mono" data-set="tts_url" value="${esc(st.tts_url)}" placeholder="http://127.0.0.1:8880">
      <div class="hint">on this PC only: http://127.0.0.1:&lt;port&gt; · empty = no voice server yet (text only)</div>
      <label>Model</label><div id="ttsModelBox">${voicePick("tts_model", st.tts_model, null)}</div>
      <label>Voice</label><div id="ttsVoiceBox">${voicePick("voice", st.voice, null)}</div>
      <div class="hint" id="voiceListNote">the server's own names; Kokoro blends two voices with + (af_sky+af_bella)</div>
      <label>Speed</label><input class="field" type="number" min="0.5" max="2" step="0.05" data-set="voice_speed" value="${st.voice_speed}">` : ""}
      <label>Hear your tone</label><div><input type="checkbox" class="switch" data-set="hear_tone" ${st.hear_tone ? "checked" : ""}> <span class="dim small">it's told when you laugh or sound upset (SenseVoice)</span></div>
      <label>Microphone</label><div><div class="mic-row"><select class="field" id="micSel" data-set="mic_device"><option value="">Windows default</option></select>
        <button class="btn" id="micTest">Test</button><span class="mic-meter" id="micMeter"><i id="micLevel"></i></span></div>
        <div class="mic-hint dim small">Bluetooth earbuds drop to call-quality, mono sound whenever their own mic is on. Pick any other mic and they stay in stereo.</div></div>
      <label>Your voice</label><div><div class="mic-row"><button class="btn" id="voiceTeach" ${S.state.services.speaker_model ? "" : "disabled"}>${S.state.services.his_voice ? "Teach it again" : "Teach it your voice"}</button>
        ${S.state.services.his_voice ? `<button class="btn" id="voiceForget">Forget it</button>` : ""}<span class="mic-meter" id="teachMeter"><i id="teachLevel"></i></span></div>
        <div class="mic-hint dim small" id="voiceInfo">${hisVoiceLine()}</div></div>
      <label>Try its voice</label><div><button class="btn" id="voiceTry">▶ Say something</button></div>
    </div>
    <div id="voiceGuide"></div>
    ${S.state.services.ears ? "" : EARS_GUIDE}
    <h3>${icon("heartpulse")}LIFE</h3><div class="form">
      <label>Moods</label><div><input type="checkbox" class="switch" data-set="mood_enabled" ${st.mood_enabled ? "checked" : ""}> <span class="dim small">it can set its own, and it fades back to steady</span></div>
      <label>Calendar</label><div><input type="checkbox" class="switch" data-set="calendar_enabled" ${st.calendar_enabled ? "checked" : ""}> <span class="dim small">the dates you share: it sees the next two weeks, adds and moves dates, and its reminders go off</span></div>
      <label>Heartbeat</label><div><input type="checkbox" class="switch" data-set="heartbeat_enabled" ${st.heartbeat_enabled ? "checked" : ""}> <span class="dim small">it wakes up on its own while Aether is open</span></div>
      <label>Every (minutes)</label><input class="field" type="number" min="5" data-set="heartbeat_minutes" value="${st.heartbeat_minutes}">
      <label>Quiet first (minutes)</label><div><input class="field" type="number" min="1" max="240" data-set="heartbeat_idle_minutes" value="${st.heartbeat_idle_minutes}" style="width:100px"> <span class="dim small">it won't wake this soon after your last message (or while you type)</span></div>
      <label>Before it messages you</label><div><input class="field" type="number" min="1" max="600" data-set="message_idle_minutes" value="${st.message_idle_minutes ?? 30}" style="width:100px"> <span class="dim small">minutes after your last message before anything it does on its own can message you (in between it works quietly)</span></div>
      <label>Quiet hours</label><div style="display:flex;gap:8px;align-items:center"><input class="field" data-set="quiet_start" value="${esc(st.quiet_start)}" style="width:100px"> to <input class="field" data-set="quiet_end" value="${esc(st.quiet_end)}" style="width:100px"></div>
      <label>Work while you sleep</label><div><input type="checkbox" class="switch" data-set="sleep_work" ${st.sleep_work ? "checked" : ""}> every <input class="field" type="number" min="30" max="600" data-set="sleep_work_minutes" value="${st.sleep_work_minutes ?? 90}" style="width:80px;display:inline-block"> min <span class="dim small">during quiet hours it still wakes to work, silently (never around its dream and the nightly jobs)</span></div>
      <label>Thinks on its own time</label><div><input type="checkbox" class="switch" data-set="own_thinking" ${st.own_thinking ? "checked" : ""}> <span class="dim small">its own wake-ups think before each step (slower, more careful; off while you game). Chat stays fast either way</span></div>
      <label>Saved examples</label><div><input type="checkbox" class="switch" data-set="examples_collect" ${st.examples_collect ? "checked" : ""}> collect <input type="checkbox" class="switch" data-set="examples_enabled" ${st.examples_enabled ? "checked" : ""}> show to it <span class="dim small">steps that worked, kept for messages like them. Collecting runs in the background while it's idle; showing is off until a test says it helps</span></div>
      <label>Messages on its own per day</label><input class="field" type="number" min="0" max="50" data-set="reach_out_cap" value="${st.reach_out_cap}">
      <label>Its messages go to</label>${reachSelect(st.reach_out_to)}
      <div class="hint">its heartbeat, its own wake-ups, pictures it makes on its own, and your reminders. Discord needs Discord on; if it's offline they go to your latest chat</div>
      <label>Archive quiet chats</label><div><input class="field" type="number" min="0" max="365" data-set="archive_after_days" value="${st.archive_after_days ?? 7}" style="width:100px"> <span class="dim small">days with no messages before a chat moves to Archived (0 = never). Pinned, unread and open chats stay; a new message brings one back; nothing is deleted</span></div>
      <label>Dreams</label><div><input type="checkbox" class="switch" data-set="dreams_enabled" ${st.dreams_enabled ? "checked" : ""}> at <input class="field" data-set="dream_time" value="${esc(st.dream_time)}" style="width:100px;display:inline-block"> <span class="dim small">(reflection and checkup follow)</span></div>
      <label>Nightly reflection</label><div><input type="checkbox" class="switch" data-set="reflect_enabled" ${st.reflect_enabled ? "checked" : ""}> <span class="dim small">one locked step: memory fixes + lessons</span></div>
      <label>Pictures</label><div><input type="checkbox" class="switch" data-set="images_enabled" ${st.images_enabled ? "checked" : ""}> <span class="dim small">it can draw (Qwen-Image in ComfyUI, on this PC; waits while you game) · ${esc(imagesLine())}</span></div>
    </div>
    <h3>${icon("lock")}VAULT</h3><div class="soon-list" style="margin-bottom:10px">Secrets (API keys, tokens, passwords) locked to your Windows login. A secret goes only to the skills you name (as AETHER_SECRET_NAME), never into its chat, memory or logs; if one shows up in text anyway it's masked as ••••. Values are never shown here.</div>
    <div class="form">
      <label>Name</label><input class="field mono" id="vName" placeholder="NAME_LIKE_THIS">
      <label>Value</label><input class="field" id="vValue" type="password" placeholder="the secret itself" autocomplete="off">
      <label>Skills that may use it</label><input class="field" id="vSkills" placeholder="optional, e.g. email, notes">
      <div class="hint">empty = no skill gets it (Aether's own connections still can: DISCORD_BOT_TOKEN for Discord). Saving a name that's already there replaces it</div>
      <label></label><div><button class="btn primary" id="vAdd">Save</button></div>
    </div>
    <div id="vaultList" style="margin-top:12px"></div>
    <h3>${icon("discord")}DISCORD</h3>
    <div class="soon-list" style="margin-bottom:10px">Its own Discord bot, so you can talk to it from your phone. Only you can DM it; in server channels it answers when @mentioned. Anyone else gets talk-only mode, and nothing about you is shared with them.</div>
    <div class="form">
      <label>Connected</label><div><input type="checkbox" class="switch" data-set="discord_enabled" ${st.discord_enabled ? "checked" : ""}> <span class="dim small" id="discordState">…</span></div>
      <label>Setup</label><div><button class="btn" id="discordGuide">How to set up a Discord bot</button></div>
      <label>Your Discord id(s)</label><input class="field mono" data-set="discord_owner_ids" value="${esc((st.discord_owner_ids || []).join(", "))}" placeholder="100000000000000001">
      <label>Channels it answers in</label><input class="field mono" data-set="discord_channels" value="${esc((st.discord_channels || []).join(", "))}" placeholder="channel ids">
      <label>DMs</label><select class="field" data-set="discord_dm_policy">${[["allowlist", "only you"], ["open", "anyone (strangers get talk-only)"]].map(([v, l]) => `<option value="${v}" ${st.discord_dm_policy === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Mirror to your DMs</label><div><input type="checkbox" class="switch" data-set="discord_mirror" ${st.discord_mirror ? "checked" : ""}> <span class="dim small">its own messages and reminders also reach your phone</span></div>
    </div>
    <h3>${icon("terminal")}ADVANCED</h3><div class="soon-list">Logs: <span class="mono">~/.aether/logs/aether.log</span>. Telemetry: none. Aether talks only to LM Studio on this PC.</div>
    <div style="margin-top:10px"><button class="btn" id="auditBtn">Audit log: everything it did</button></div>
  </div>`;
  $$("[data-set]").forEach((el) => el.addEventListener("change", () => saveSetting(el)));
  $('[data-set="space_intensity"]').addEventListener("input", (e) => document.documentElement.style.setProperty("--space", e.target.value));
  wireBrain();
  $("#voiceTry").addEventListener("click", () => api("/api/speak", { text: `Hey, it's ${name()}. This is how I sound right now.` }).catch((e) => toast(e.message, true)));
  fillMics();
  navigator.mediaDevices.ondevicechange = () => fillMics();
  $("#micTest").addEventListener("click", testMic);
  $("#voiceTeach")?.addEventListener("click", teachVoice);
  $("#voiceForget")?.addEventListener("click", async () => {
    if (!confirm(`Forget your voice? ${name()} stops checking who's talking. The voiceprint goes to the Recycle Bin.`)) return;
    try { await api("/api/voice/forget", {}); await refreshState(); showView("settings"); } catch (e) { toast(e.message, true); }
  });
  renderAvatars();
  $("#backupBtn").addEventListener("click", backupNow);
  $("#discordGuide").addEventListener("click", discordGuide);
  discordStatus();
  $("#auditBtn").addEventListener("click", auditLog);
  $("#vAdd").addEventListener("click", async () => {
    try {
      await api("/api/vault/set", { name: $("#vName").value, value: $("#vValue").value, skills: $("#vSkills").value.split(/[\s,]+/).filter(Boolean) });
      $("#vName").value = ""; $("#vValue").value = ""; $("#vSkills").value = ""; toast("Locked in the vault"); renderVault();
    } catch (e) { toast(e.message, true); }
  });
  $$("[data-pick]").forEach((b) => b.addEventListener("click", () => pickFolder(b)));
  fillVoiceOptions();
  renderVault();
  api("/api/backups").then((b) => { const el = $("#backupInfo"); if (el) el.textContent = b.last ? `last: ${b.last.when.slice(0, 16).replace("T", " ")} · ${(b.last.size / 1e6).toFixed(1)} MB · ${b.items.length} kept in ${b.folder}` : `none yet · saved to ${b.folder}`; }).catch(() => {});
}

function folderField(which, key, value) {
  return `<div style="display:flex;gap:8px;min-width:0"><input class="field mono" data-set="${key}" value="${esc(value || "")}" style="flex:1;min-width:0"><button class="btn" data-pick="${which}" style="white-space:nowrap">Choose folder…</button></div>`;
}
async function pickFolder(btn) {
  btn.disabled = true;
  toast("The folder picker is open (it may be behind this window)");
  try {
    const r = await api("/api/pick-folder", { which: btn.dataset.pick });
    if (r.ok) {
      const key = btn.dataset.pick === "library" ? "library_dir" : "workspace_dir";
      S.state.settings[key] = r.path;
      const input = btn.parentElement.querySelector("input");
      if (input) input.value = r.path;
      toast("Saved: " + r.path);
    }
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; }
}

function voicePick(key, value, list) {
  if (!list || !list.length) return `<input class="field mono" data-set="${key}" value="${esc(value || "")}" placeholder="${key === "voice" ? "e.g. af_heart" : "e.g. kokoro"}">`;
  const opts = list.includes(value) || !value ? list : [value, ...list];
  return `<select class="field mono" data-set="${key}">${value ? "" : `<option value="" selected>pick one</option>`}${opts.map((v) => `<option value="${esc(v)}" ${v === value ? "selected" : ""}>${esc(v)}</option>`).join("")}<option value="__type__">type it…</option></select>`;
}
const VOICE_GUIDE = `<div class="guide"><b>How to get a voice server</b> (free, and it runs on this PC)
  <ol>
    <li>Install <b>Docker Desktop</b> (docker.com), start it, and wait until it says it's running.</li>
    <li>Open PowerShell and run:<br><code>docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest</code><br>
      With an NVIDIA graphics card, the faster one instead:<br><code>docker run --gpus all -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-gpu:latest</code><br>
      The first start downloads it (a few GB) and takes a few minutes. Keep that window open while you use its voice.</li>
    <li>Here, put <code>http://127.0.0.1:8880</code> in <b>Server address</b>.</li>
    <li>Pick the model <code>kokoro</code> and a voice from the list (af_heart, af_sky, ...; join two with + to blend them).</li>
    <li>Press <b>▶ Say something</b> under Try its voice.</li>
  </ol>
  Any other speech program on this PC that speaks the OpenAI-style <code>/v1/audio/speech</code> format works the same way: put its address in Server address. Local only: Aether never sends its words to a voice in the cloud.</div>`;

const EARS_GUIDE = `<div class="guide"><b>How to set up its ears</b> (so it can hear you talk; free, and it runs on this PC)
  <ol>
    <li>Open PowerShell in the Aether folder and make its ears' Python environment:<br><code>python -m venv .venv</code><br><code>.venv\\Scripts\\pip install sherpa-onnx==1.10.46 "numpy&lt;2"</code></li>
    <li>Download the SenseVoice model (about 160 MB) from the sherpa-onnx releases on GitHub:<br><code>sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2</code> (under <b>asr-models</b>)</li>
    <li>Unpack it into the <code>models</code> folder:<br><code>mkdir models; tar -xf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2 -C models</code><br>
      so that <code>models\\sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17\\model.int8.onnx</code> is there.</li>
    <li>Optional, for <b>Teach it your voice</b>: put <code>3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx</code> (under <b>speaker-recongition-models</b>, spelled that way) in <code>models</code> too.</li>
    <li>Close Aether and open it again. <b>Ears</b> at the bottom turns green; then click the mic and talk.</li>
  </ol>
  Everything it hears stays on this PC.</div>`;
async function fillVoiceOptions() {
  const guide = $("#voiceGuide");
  if (!guide) return;
  const st = S.state.settings;
  if (st.voice_engine !== "kokoro") { guide.innerHTML = ""; return; }
  const o = st.tts_url ? await api("/api/voice/options").catch((e) => ({ ok: false, error: e.message, models: [], voices: [] })) : { ok: false, models: [], voices: [] };
  if (!$("#voiceGuide")) return;
  guide.innerHTML = o.ok ? "" : (st.tts_url ? `<div class="dim small" style="margin:6px 0">The voice server at ${esc(st.tts_url)} isn't answering${o.error ? ` (${esc(o.error)})` : ""}. Is it running?</div>` : "") + VOICE_GUIDE;
  for (const [box, key, list] of [["#ttsModelBox", "tts_model", o.models], ["#ttsVoiceBox", "voice", o.voices]]) {
    const el = $(box);
    if (!el) continue;
    el.innerHTML = voicePick(key, st[key], o.ok ? list : null);
    const f = el.querySelector("[data-set]");
    f.addEventListener("change", () => {
      if (f.value === "__type__") { el.innerHTML = voicePick(key, st[key], null); const i = el.querySelector("input"); i.addEventListener("change", () => saveSetting(i)); i.focus(); return; }
      saveSetting(f);
    });
  }
  const note = $("#voiceListNote");
  if (note) note.textContent = o.ok && (o.models.length || o.voices.length) ? "from the voice server's own lists; \"type it…\" for one it doesn't list (Kokoro blends with +: af_sky+af_bella)"
    : "the server's own names; Kokoro blends two voices with + (af_sky+af_bella)";
}

function discordGuide() {
  openModal(`<h2>How to set up a Discord bot<button class="x" data-action="close">✕</button></h2>
    <div class="guide" style="max-height:62vh;overflow:auto"><ol>
      <li>Open the <b>Discord Developer Portal</b> (discord.com/developers/applications) and sign in.</li>
      <li><b>New Application</b>: name it ${esc(name())}, then <b>Create</b>.</li>
      <li><b>Bot</b> (left menu): <b>Reset Token</b>, confirm, then <b>Copy</b>. That token is the bot's password: don't share it.</li>
      <li>Same page, under Privileged Gateway Intents: turn on <b>Message Content Intent</b>, then <b>Save Changes</b>.</li>
      <li><b>OAuth2</b> → <b>URL Generator</b>: under Scopes tick <b>bot</b>; under Bot Permissions tick <b>Send Messages</b> and <b>Read Message History</b> (and Attach Files, for its pictures and voice clips). Copy the URL at the bottom.</li>
      <li>Open that URL in your browser, pick your server, and <b>Authorize</b>: the bot joins your server.</li>
      <li>Back here, in <b>Settings → Vault</b>: Name <code>DISCORD_BOT_TOKEN</code> (exactly that), Value = the token from step 3, skills empty, then <b>Save</b>.</li>
      <li>Your Discord user id: in Discord, <b>Settings → Advanced → Developer Mode</b> on; then right-click your own name → <b>Copy User ID</b>. Paste it in <b>Your Discord id(s)</b>.</li>
      <li>Tick <b>Connected</b>. The note next to it says when it's online. DM the bot to talk to it; for a server channel, put its id in Channels it answers in, and @mention it there.</li>
    </ol></div>
    <div style="display:flex;margin-top:14px"><button class="btn primary" data-action="close" style="margin-left:auto">Done</button></div>`);
}

async function fillMics() {
  const sel = $("#micSel");
  if (!sel) return;
  try {
    let mics = await MicPick.list();
    if (mics.length && !mics.some((m) => m.label)) {
      (await navigator.mediaDevices.getUserMedia({ audio: true })).getTracks().forEach((t) => t.stop());
      mics = await MicPick.list();
    }
    const saved = S.state.settings.mic_device || "";
    const names = mics.map((m) => m.label).filter(Boolean);
    const opts = [["", "Windows default"], ...names.map((n) => [n, n])];
    if (saved && !names.includes(saved)) opts.push([saved, saved + " (not plugged in)"]);
    sel.innerHTML = opts.map(([v, l]) => `<option value="${esc(v)}" ${v === saved ? "selected" : ""}>${esc(l)}</option>`).join("");
  } catch (e) { sel.title = "Couldn't list the mics: " + e.message; }
}

async function testMic() {
  const btn = $("#micTest"), bar = $("#micLevel");
  if (!btn || btn.disabled) return;
  btn.disabled = true; btn.textContent = "Talk…";
  $("#micMeter")?.classList.add("on");
  let stream, ctx;
  try {
    stream = await MicPick.open($("#micSel").value, { channelCount: 1 });
    ctx = new AudioContext();
    const an = ctx.createAnalyser(), buf = new Float32Array(1024);
    an.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(an);
    const end = Date.now() + 5000;
    await new Promise((done) => {
      const tick = () => {
        an.getFloatTimeDomainData(buf);
        let s = 0;
        for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
        if (bar) bar.style.width = Math.min(100, Math.sqrt(s / buf.length) * 600) + "%";
        if (Date.now() < end && $("#micTest")) requestAnimationFrame(tick); else done();
      };
      tick();
    });
  } catch (e) { toast("That mic didn't open: " + e.message, true); }
  finally {
    stream?.getTracks().forEach((t) => t.stop()); ctx?.close();
    if (bar) bar.style.width = "0%";
    $("#micMeter")?.classList.remove("on");
    btn.disabled = false; btn.textContent = "Test";
  }
}

function hisVoiceLine() {
  const sv = S.state.services, v = sv.his_voice;
  if (!sv.speaker_model) return "the speaker model isn't in models/, so it can't check voices";
  if (!v) return `not learned yet: click, then talk normally for 20 s (about anything, or read something out loud). After that it's told when a voice doesn't sound like yours`;
  return `${name()} knows your voice (learned ${v.made.slice(0, 10)}, from ${Math.round(v.speech)} s of you talking). Messages of 2 s or more are checked; it's told when a voice doesn't sound like you. A hint, never a lock`;
}
async function teachVoice() {
  const btn = $("#voiceTeach"), bar = $("#teachLevel"), info = $("#voiceInfo");
  if (!btn || btn.disabled) return;
  if (Mic.on) return toast("Stop the mic first", true);
  const SECS = 20;
  btn.disabled = true;
  $("#teachMeter")?.classList.add("on");
  let stream, ctx;
  try {
    stream = await MicPick.open(S.state.settings.mic_device, { channelCount: 1, echoCancellation: true, noiseSuppression: true });
    ctx = new AudioContext({ sampleRate: 16000 });
    const rate = ctx.sampleRate, node = ctx.createScriptProcessor(4096, 1, 1), chunks = [];
    let secs = 0;
    await new Promise((done) => {
      node.onaudioprocess = (e) => {
        const x = new Float32Array(e.inputBuffer.getChannelData(0));
        chunks.push(x);
        let s = 0;
        for (let i = 0; i < x.length; i++) s += x[i] * x[i];
        if (bar) bar.style.width = Math.min(100, Math.sqrt(s / x.length) * 600) + "%";
        secs += x.length / rate;
        btn.textContent = `Talk… ${Math.max(0, Math.ceil(SECS - secs))}`;
        if (secs >= SECS) done();
      };
      ctx.createMediaStreamSource(stream).connect(node); node.connect(ctx.destination);
    });
    node.disconnect();
    btn.textContent = "Learning…";
    const n = chunks.reduce((a, c) => a + c.length, 0);
    const r = await api("/api/voice/learn", { data: toWav(chunks, n, rate) });
    toast(`${name()} knows your voice now (from ${Math.round(r.speech)} s of you talking)`);
    await refreshState();
    showView("settings");
  } catch (e) {
    toast(e.message, true);
    if (info) info.textContent = hisVoiceLine();
    btn.disabled = false; btn.textContent = S.state.services.his_voice ? "Teach it again" : "Teach it your voice";
  } finally {
    stream?.getTracks().forEach((t) => t.stop()); ctx?.close();
    if (bar) bar.style.width = "0%";
    $("#teachMeter")?.classList.remove("on");
  }
}

const THEMES = [["astral", "Astral · deep space, violet and cyan"], ["holo", "Holo · deep navy, holo-blue, a faint grid"],
  ["void", "Void · true black, one violet spark"], ["terminal", "Terminal · green on black, all monospace"]];
function applyTheme(name) {
  document.documentElement.dataset.theme = name || "astral";
  redrawAll();
}
async function saveSetting(el) {
  const k = el.dataset.set;
  const v = el.type === "checkbox" ? el.checked : el.value;
  try {
    S.state.settings = await api("/api/settings", { [k]: v });
    if (k === "theme") applyTheme(v);
    toast(k !== "voice_engine" ? "Saved" : v === "breeze" ? "Breeze is loading (~15 s)"
      : "The voice server it is; Breeze let go of the graphics card");
    renderChrome();
    if (k === "voice_engine") renderSettings();
    if (k === "tts_url") fillVoiceOptions();
  } catch (e) { toast(e.message, true); }
}

const B = { data: null, commits: [], sel: null, detail: null, file: null, view: null, find: null };

function seeded(str) {
  let h = 2166136261;
  for (const ch of str) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return () => { h = Math.imul(h ^ (h >>> 15), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909); return ((h ^= h >>> 16) >>> 0) / 4294967296; };
}

async function renderBrain() {
  if (B.view) { B.view.destroy(); B.view = null; }
  B.q = B.hits = null;
  $("#center").innerHTML = `<div class="brain">
    <div class="brain-map" id="brainMap"><div class="title"><b>Brain</b><span class="dim small" id="brainStats"></span>
      <span class="bstyle" title="How the brain map is drawn (the wallpaper follows at its next refresh)">${[["tree", "Tree"], ["constellation", "Constellation"], ["neuron", "Neuron web"]]
        .map(([v, l]) => `<button data-bstyle="${v}" class="${brainStyle() === v ? "on" : ""}">${l}</button>`).join("")}</span></div>
      <div class="legend" id="brainLegend"></div>
      <div class="zoom"><button data-zoom="1.15">+</button><button data-zoom="0.87">−</button><button data-action="brain-all" title="Reset the view: every region, straight on, normal size">◎</button></div></div>
    <div class="history"><div class="h">HISTORY<button class="tomap" data-action="brain-map">← Map</button></div>
      <input class="field bfind" id="brainFind" placeholder="Search its files…" spellcheck="false" autocomplete="off">
      <div id="history"></div></div>
    <div class="fileview" id="fileview"><div class="dim">Click a star or a spark, or pick a change.</div></div></div>`;
  try {
    const [data, commits] = await Promise.all([api("/api/brain3d"), api("/api/commits?n=40")]);
    if (S.view !== "brain") return;
    B.data = data; B.commits = commits;
    const m = data.meta;
    $("#brainStats").textContent = `${m.files} files · ${m.memories} memories · ${m.chats ?? 0} chats · ${m.links} links · ${S.state?.agent?.stats?.commits ?? "?"} changes`;
    $("#brainLegend").innerHTML = Object.values(m.regions).map((r) => `<span><i style="background:${r.color}"></i>${esc(r.label)}</span>`).join("") +
      `<span class="faint">· drag to turn · scroll to zoom · click to open</span>`;
    B.view = mountBrain3D($("#brainMap"), data, {
      open: (path, find) => openFile(path, find),
      organ: (key, o) => openOrgan(key, o),
      chat: (id) => openChat(id),
      style: brainStyle(),
    });
    $$("[data-bstyle]").forEach((b) => b.addEventListener("click", () => setBrainStyle(b.dataset.bstyle)));

    B.group = B.pending ? new Set(B.pending) : null;
    const first = B.pending ? B.pending[0] : commits[0]?.hash;
    B.pending = null;
    $("#brainFind").addEventListener("input", (e) => { clearTimeout(B.findTimer); B.findTimer = setTimeout(() => findInBrain(e.target.value), 200); });
    $("#brainFind").addEventListener("keydown", (e) => { if (e.key === "Escape") { e.target.value = ""; findInBrain(""); } });
    renderHistory();
    if (first) selectCommit(first, true);
  } catch (e) { toast(e.message, true); }
}

async function findInBrain(q) {
  q = q.trim();
  if (q.length < 2) {
    B.q = B.hits = B.past = null;
    B.view?.setHot(B.detail ? B.detail.files.map((f) => f.path) : B.file ? [B.file] : []);
  } else {
    const r = await api(`/api/brain-search?q=${encodeURIComponent(q)}`).catch(() => ({ files: [], history: [] }));
    if ($("#brainFind")?.value.trim() !== q) return;
    B.q = q; B.hits = r.files; B.past = r.history;
    B.view?.setHot(r.files.map((f) => f.path));
  }
  renderHistory();
}

function reading(on) {
  $(".brain")?.classList.toggle("reading", on);
}

function aroundQ(text, q) {
  const t = text.trim(), i = t.toLowerCase().indexOf(q.toLowerCase());
  return i > 50 ? "…" + t.slice(t.lastIndexOf(" ", i - 30) + 1) : t;
}
function renderFound() {
  const shown = 6;
  const lines = B.hits.reduce((n, f) => n + f.count, 0);
  return `<div class="faint small found-sum">${lines ? `${lines} line${lines > 1 ? "s" : ""} in ${B.hits.length} file${B.hits.length > 1 ? "s" : ""}` : "Nothing found in its files."}</div>` +
    B.hits.map((f) => `<div class="found"><button class="found-file" data-findfile="${esc(f.path)}">${esc(f.path)} <span class="faint">${f.count}</span></button>` +
      f.hits.slice(0, shown).map((h) => `<button class="found-line" data-findfile="${esc(f.path)}" data-findn="${h.n}"><span class="n">${h.n}</span><span class="s">${markQ(aroundQ(h.text, B.q), B.q)}</span></button>`).join("") +
      (f.count > shown ? `<button class="found-more faint small" data-findfile="${esc(f.path)}" data-findn="${f.hits[shown].n}">+${f.count - shown} more in this file</button>` : "") +
      `</div>`).join("") + renderFoundPast();
}

function renderFoundPast() {
  const past = B.past || [];
  return `<div class="h found-h">IN ITS HISTORY</div>` + (past.length ? past.map((c) => `<button class="commit found-change${c.hash === B.sel ? " on" : ""}" data-commit="${c.hash}"><span class="c"></span>
    <div style="min-width:0"><div class="m">${esc(c.subject)}</div><div class="w">${esc(author(c.author))} · ${esc(c.when)}</div>` +
    c.lines.map(([s, t]) => `<div class="found-diff ${s === "+" ? "add" : "del"}">${s === "+" ? "+" : "−"} ${markQ(aroundQ(t, B.q), B.q)}</div>`).join("") +
    `</div></button>`).join("") + (past.length >= 20 ? `<div class="faint small found-sum">the newest 20 changes</div>` : "")
    : `<div class="faint small found-sum">No change ever had it.</div>`);
}

function renderHistory() {
  const h = $("#history");
  if (!h) return;
  if (B.hits) { h.innerHTML = renderFound(); return; }
  h.innerHTML = B.commits.map((c) => `<button class="commit${c.hash === B.sel ? " on" : ""}${B.group?.has(c.hash) ? " grp" : ""}" data-commit="${c.hash}"><span class="c"></span>
    <div style="min-width:0"><div class="m">${esc(c.subject)}</div><div class="w">${esc(author(c.author))} · ${esc(c.when)}</div></div></button>`).join("") +
    (B.commits.length >= 40 && B.commits.length % 40 === 0 ? `<button class="show-all" data-action="older">Show older</button>` : "");
}

async function renderAvatars() {
  const box = $("#avList"), pv = $("#avPreview");
  if (!box) return;
  let L, A;
  try { [L, A] = await Promise.all([api("/api/avatars"), api("/api/avatar")]); } catch (e) { box.textContent = e.message; return; }
  const row = (name, label, cur, extra) => `<div style="display:flex;gap:8px;align-items:center;margin:3px 0">
    <button class="btn ${cur ? "primary" : ""}" data-av="${esc(name)}" ${cur ? "disabled" : ""}>${cur ? "✓ in use" : "Use"}</button>
    <b>${esc(label)}</b>${extra || ""}</div>`;
  const about = { "orb": "a wireframe orb that morphs like liquid and ripples with its voice; no Live2D needed",
                  "logo-orb": "the Aether logo, alive: floats, pulses with its voice, glitches now and then" };
  const rows = (L.builtins || [{ name: "orb", label: "Orb (built in)" }]).map((b) =>
    row(b.name, b.label, L.current === b.name, ` <span class="dim">· ${esc(about[b.name] || "")}</span>`));
  if (L.default) rows.push(row("", `the default (${L.default})`, L.current === ""));
  L.list.forEach((a) => rows.push(row(a.name, a.name, L.current === a.name,
    a.warnings.length ? ` <span class="dim">· ${esc(a.warnings.join("; "))}</span>` : "")));
  box.innerHTML = rows.length ? rows.join("") : "none yet: add one below";
  $$("#avList [data-av]").forEach((b) => b.addEventListener("click", async () => {
    try { await api("/api/avatars/use", { name: b.dataset.av }); await Avatar.load(); renderAvatars(); }
    catch (e) { toast(e.message, true); }
  }));
  $("#avAdd").onclick = async () => {
    const path = $("#avPath").value.trim();
    if (!path) return;
    try {
      const r = await api("/api/avatars/add", { path, name: $("#avName").value.trim() });
      toast(`Added ${r.added.name}` + (r.added.warnings.length ? ": " + r.added.warnings.join("; ") : ""));
      $("#avPath").value = ""; $("#avName").value = "";
      renderAvatars();
    } catch (e) { toast(e.message, true); }
  };
  if (A.info && A.info.kind === "orb") { pv.textContent = "the orb follows the voice by itself: nothing to set"; return; }
  if (!A.runtime) { pv.textContent = "the Live2D runtime isn't installed (see the README)"; return; }
  if (!A.info) { pv.textContent = "pick or add an avatar first"; return; }
  const info = A.info;
  const opts = (sel) => `<option value="">its default look</option>` +
    info.expressions.map((e) => `<option ${sel === e ? "selected" : ""}>${esc(e)}</option>`).join("");
  pv.innerHTML = `<div class="dim small">each mood's face, shown on the right; pick another if one doesn't fit</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">${Object.keys(info.moods).map((m) =>
      `<div style="display:flex;gap:4px;align-items:center"><button class="btn" data-mood="${esc(m)}">${esc(m)}</button>
       <select class="field" data-moodpick="${esc(m)}" style="width:auto">${opts(info.moods[m])}</select></div>`).join("")}</div>
    <div style="display:flex;gap:14px;align-items:center;margin-top:10px">zoom
      <input type="range" id="avZoom" min="0.3" max="3" step="0.05" value="${info.framing.zoom}"> up / down
      <input type="range" id="avY" min="-1" max="1" step="0.02" value="${info.framing.y}"></div>
    ${info.warnings.length ? `<div class="dim small" style="margin-top:6px">${esc(info.warnings.join(" · "))}</div>` : ""}`;
  $$("#avPreview [data-mood]").forEach((b) => b.addEventListener("click", () => Avatar.view?.setMood(b.dataset.mood)));
  $$("#avPreview [data-moodpick]").forEach((s) => s.addEventListener("change", async () => {
    try {
      await api("/api/avatars/mood", { mood: s.dataset.moodpick, expression: s.value || null });
      await Avatar.load();
      Avatar.view?.setMood(s.dataset.moodpick);
    } catch (e) { toast(e.message, true); }
  }));
  const live = () => Avatar.view?.setFraming(+$("#avZoom").value, +$("#avY").value);
  const keep = () => api("/api/avatars/frame", { zoom: +$("#avZoom").value, y: +$("#avY").value }).catch((e) => toast(e.message, true));
  ["#avZoom", "#avY"].forEach((id) => { $(id).addEventListener("input", live); $(id).addEventListener("change", keep); });
}

function brainStyle() { return S.state?.settings?.brain_style || "tree"; }
async function setBrainStyle(v) {
  if (v === brainStyle()) return;
  try {
    S.state.settings = await api("/api/settings", { brain_style: v });
    toast(v === "tree" ? "The Timeline Tree" : v === "neuron" ? "The Neuron Web" : "The constellation");
    renderBrain();
  } catch (e) { toast(e.message, true); }
}

async function selectCommit(h, auto = false) {
  B.sel = h; B.find = null;
  if (!auto) reading(true);
  renderHistory();
  try {
    B.detail = await api(`/api/commit?h=${h}`);

    const has = (f) => B.q && f.lines.some((l) => (l.t === "add" || l.t === "del") && l.s.toLowerCase().includes(B.q.toLowerCase()));
    B.file = (B.detail.files.find(has) || B.detail.files[0])?.path || null;
    B.view?.setHot(B.detail.files.map((f) => f.path));
    renderFileview();
  } catch (e) { toast(e.message, true); }
}

const ORGAN_FILES = {
  user: ["system/human.md", "system/human/facts.md"], dreams: ["life/dreams.md"], heartbeat: ["life/heartbeat.md"],
  discord: ["system/channels.md"], voice: ["skills/voice/SKILL.md"], lmstudio: ["system/persona.md", "reference/lessons.md"],
  keeper: ["system/timeline.md", "system/threads.md", "reference/stances.md"], nudge: ["system/threads.md"],
};
const hasFile = (p) => (B.data?.nodes || []).some((n) => n.k === "file" && n.label === p);
function openOrgan(key, o) {
  const files = (ORGAN_FILES[key] || []).filter(hasFile);
  if (files.length && ["user", "dreams", "heartbeat", "discord"].includes(key)) return openFile(files[0]);
  B.sel = null; B.detail = null; B.file = null; B.find = null;
  reading(true);
  renderHistory();
  B.view?.setHot(files);
  const fv = $("#fileview");
  if (!fv || !o) return;
  const note = { dreams: "No dream yet: the first one happens at the dream time, while you sleep.",
    lmstudio: "Its thinking engine. Who it is lives in persona.md; lessons from its own mistakes in lessons.md.",
    ears: "Hears your voice on this PC (SenseVoice), and how you sound. Nothing is kept but the words.",
    avatar: "Its Live2D body, in the app and in pet mode.", voice: "Its voice: a speech program on this PC (Settings -> Voice & Ears).",
    pictures: "Its hands: it draws on this PC (Qwen-Image in ComfyUI), never while you game, and looks at each picture before you do. Each little gold star is one it's made.",
    cue: "Before each of your messages, Aether looks through everything you two ever said and its memory, and hands it the few things that came to mind. The blue spiral is your chats, oldest at the bottom.",
    keeper: "Once a day, when you've been quiet a few minutes, Aether reads your new chats and writes down what happened (the timeline), what's coming up for you (threads) and its own takes. The Notebook region is its work, one star per week.",
    nudge: "A couple of hours after something on your calendar (an appointment, a plan), it may check in on you, in its own words. Code decides when; it decides whether and what." }[key] || "";
  fv.innerHTML = `<div class="top"><span class="path">${esc(o.name)}</span><span class="tag">${esc(o.role)}</span></div>
    <div class="small" style="margin-top:4px;color:${o.state === "down" ? "var(--red)" : o.state === "off" ? "var(--faint)" : "var(--green)"}">● ${esc(o.state)}</div>
    ${note ? `<p class="dim" style="margin:12px 0 4px">${esc(note)}</p>` : ""}
    <div class="code" style="margin-top:10px">${(o.details || []).map(([a, b]) => `<div class="ln"><span class="n" style="width:130px;text-align:left">${esc(a)}</span><span class="s">${esc(b)}</span></div>`).join("") || '<div class="ln"><span class="s dim">nothing more to show</span></div>'}</div>
    ${files.length ? `<div class="acts">${files.map((f) => `<button data-file="${esc(f)}">Open ${esc(f)}</button>`).join("")}</div>` : ""}
    ${key === "pictures" ? `<div class="acts"><button data-view="images">Open Creations</button></div>` : ""}`;
}

async function openFile(path, find, n = 0) {
  B.sel = null; B.detail = null; B.file = path; B.find = find || null; B.findN = n;
  reading(true);
  renderHistory();
  B.view?.setHot(B.hits ? B.hits.map((f) => f.path) : [path]);
  try { const f = await api(`/api/file?path=${encodeURIComponent(path)}`); renderFileview(f); } catch (e) { toast(e.message, true); }
}
function renderFileview(file) {
  const fv = $("#fileview");
  if (!fv) return;
  if (file) {
    const lines = file.text.split("\n");
    fv.innerHTML = `<div class="top"><span class="path">${esc(file.path)}</span>${file.read_only ? '<span class="tag">read-only for it</span>' : ""}${file.owner ? `<span class="tag cyan">written by ${esc(file.owner)}</span>` : ""}</div>
      <div class="faint small" style="margin-top:4px">as it is now · ${lines.length} lines</div>
      <div class="acts"><button data-edit="${esc(file.path)}">✎ Edit file</button></div>
      <div class="code">${lines.map((l, i) => `<div class="ln${i < 4 && /^(---|description:|read_only:)/.test(l) ? " meta" : ""}${(B.findN ? i + 1 === B.findN : B.find && l.includes(B.find.slice(0, 40))) ? " hit" : ""}"><span class="n">${i + 1}</span><span class="s">${B.q ? markQ(l, B.q) : esc(l)}</span></div>`).join("")}</div>`;
    $(".ln.hit", fv)?.scrollIntoView({ block: "center" });
    return;
  }
  const d = B.detail;
  if (!d) { fv.innerHTML = `<div class="dim">Pick a change or a star.</div>`; return; }
  const f = d.files.find((x) => x.path === B.file) || d.files[0];
  const tabs = d.files.length > 1 ? `<div class="tabs" style="margin-top:10px">${d.files.map((x) => `<button class="tab${x === f ? " on" : ""}" data-difffile="${esc(x.path)}">${esc(x.path.split("/").pop())}</button>`).join("")}</div>` : "";
  fv.innerHTML = `<div class="top"><span class="path">${esc(f ? f.path : "(no file changes)")}</span><span class="hash">${esc(d.hash)}</span></div>
    <div class="faint small" style="margin-top:4px">${esc(author(d.author))} · ${esc(d.when)}${f ? ` · ${f.added} added${f.removed ? `, ${f.removed} removed` : ""}` : ""}</div>
    <div class="dim small" style="margin-top:6px">${esc(d.subject)}</div>${tabs}
    <div class="acts"><button class="v" data-rewind="${esc(d.hash)}">↶ Rewind this change</button>${f && B.data.nodes.some((n) => n.file === f.path) ? `<button data-edit="${esc(f.path)}">✎ Edit file</button>` : ""}</div>
    <div class="code">${f ? f.lines.map((l) => `<div class="ln ${l.t}"><span class="n"></span><span class="s">${l.t === "add" ? "+ " : l.t === "del" ? "− " : ""}${B.q ? markQ(l.s, B.q) : esc(l.s)}</span></div>`).join("") : ""}</div>`;
  $(".ln.add mark, .ln.del mark", fv)?.scrollIntoView({ block: "center" });
}

async function editFile(path) {
  let f;
  try { f = await api(`/api/file?path=${encodeURIComponent(path)}`); } catch (e) { return toast(e.message, true); }

  const desc = ((f.text.match(/^---\r?\n[\s\S]*?^description:\s*(.+)$/m) || [])[1] || "").trim().replace(/\.$/, "");
  openModal(`<h2>${esc(desc || `Edit ${path}`)}<button class="x" data-action="close">✕</button></h2>
    <p class="dim small">${desc ? `<span class="mono">${esc(path)}</span> · ` : ""}Saved as a commit by you. It sees the change on its next message.${f.read_only ? " It can't edit this file itself." : ""}</p>
    <div class="code" style="height:52vh;padding:12px 0"><textarea id="editText" spellcheck="false">${esc(f.text)}</textarea></div>
    <div style="display:flex;margin-top:16px"><button class="btn" data-action="close" style="margin-left:auto">Cancel</button><button class="btn primary" style="margin-left:10px" id="saveEdit">Save</button></div>`);
  $("#saveEdit").addEventListener("click", async () => {
    try {
      await api("/api/file", { path, text: $("#editText").value });
      closeOverlay(); toast("Saved");
      if (S.view === "brain") renderBrain(); else if (S.view === "know") renderKnow();
    } catch (e) { toast(e.message, true); }
  });
}

async function forgetMemory(ref) {
  const [i, j] = ref.split(":").map(Number);
  const m = (S.chat?.events[i]?.remembered || [])[j];
  if (!m) return;
  const ok = await confirmBox("Mark this memory as wrong?", "It won't come to mind again. If it's a line in its notebook (timeline, takes, threads), it's taken out as a change you can rewind.");
  if (!ok) return;
  try {
    const r = await api("/api/forget", { key: m.key || "", text: m.text || "" });
    toast(r.removed_from ? `Taken out of ${r.removed_from}` : `${name()} won't bring that one up again`);
  } catch (e) { toast(e.message, true); }
}

async function rewind(hash) {
  const ok = await confirmBox("Rewind this change?", "Aether adds a new commit that undoes it. Nothing is erased: you can rewind the rewind.");
  if (!ok) return;
  try {
    const r = await api("/api/rewind", { hash });
    toast(`Rewound (commit ${r.commit})`);
    if (S.view === "brain") renderBrain(); else if (S.chat) openChat(S.chat.id, true);
  } catch (e) { toast(e.message, true); }
}

function closeOverlay() { $("#overlay").innerHTML = ""; $$(".plus.on").forEach((b) => b.classList.remove("on")); }
function openModal(html) { $("#overlay").innerHTML = `<div class="modal-back" data-close-back><div class="modal">${html}</div></div>`; }
function openMenu(anchor, items, where = "below") {
  const r = anchor.getBoundingClientRect();
  const html = items.map((it) => it === "-" ? "<hr>" :
    `<button class="item${it.danger ? " danger" : ""}${it.disabled ? " disabled" : ""}" data-menu="${esc(it.id)}"${it.disabled ? ` title="${esc(it.disabled)}"` : ""}><span class="g">${it.g || ""}</span><span>${esc(it.label)}</span><span class="s">${esc(it.sub || "")}</span></button>`).join("");
  $("#overlay").innerHTML = `<div class="scrim" data-action="close"></div><div class="menu" id="menu">${html}</div>`;
  const m = $("#menu"), mr = m.getBoundingClientRect();
  let left = Math.min(r.left, window.innerWidth - mr.width - 12), top = where === "above" ? r.top - mr.height - 10 : r.bottom + 8;
  if (where === "right") { left = r.right + 8; top = r.top; }
  if (top + mr.height > window.innerHeight - 8) top = Math.max(8, r.top - mr.height - 10);
  m.style.left = `${Math.max(8, left)}px`; m.style.top = `${Math.max(8, top)}px`;
  return new Promise((ok) => { m.addEventListener("click", (e) => { const b = e.target.closest("[data-menu]"); if (b && !b.classList.contains("disabled")) { closeOverlay(); ok(b.dataset.menu); } }); });
}

const BRAIN_PHASE = { unloading: "Unloading", loading: "Loading", back: "That didn't load: putting the old one back" };
function brainList(b) {
  if (b.error && !b.models.length) return `<span class="dim small">LM Studio isn't answering (${esc(b.error)})</span>`;
  const sc = S.brainScores || {};
  const scoreOf = (key) => { const k = Object.keys(sc).find((x) => x.split("/").pop() === key); return k ? ` · test ${sc[k].passed}/${sc[k].total}` : ""; };
  const st = b.state || {};
  const swapping = ["unloading", "loading", "back"].includes(st.phase);
  const rows = b.models.map((m) => `<div class="brain-row${m.current ? " on" : ""}">
      <div><b>${esc(m.name)}</b> <span class="dim small">${esc(m.params)} · ${esc(m.quant)} · ${m.size_gb} GB · up to ${Number(m.max_context).toLocaleString()} tokens${m.vision ? " · sees pictures" : " · no pictures"}${m.tools ? " · tool-trained" : ""}${esc(scoreOf(m.key))}</span></div>
      <div>${m.current && m.loaded ? `<span class="pill pink">its brain now</span>` : `<button class="btn" data-brain="${esc(m.key)}" ${swapping ? "disabled" : ""}>Use this one</button>`}${m.loaded && !m.current ? ` <span class="dim small">loaded</span>` : ""}${m.current && !m.loaded ? ` <span class="dim small">not loaded: LM Studio loads it when it talks</span>` : ""}</div>
    </div>`).join("");
  const prev = b.previous && b.models.find((m) => m.key === b.previous);
  const back = prev && !swapping ? `<button class="btn" data-brain="${esc(prev.key)}">Back to ${esc(prev.name)}</button>` : "";
  const line = swapping ? `${BRAIN_PHASE[st.phase]} ${esc(st.phase === "unloading" ? st.frm : st.to)}… <span class="dim">(${Math.round(Date.now() / 1000 - st.started)} s)</span>`
    : st.phase === "done" ? `Now ${esc(st.to)}, loaded in ${st.took} s. Run its test below before trusting it.`
      : st.phase === "failed" ? `<span style="color:var(--pink)">${esc(st.error)}</span>` : "";
  return rows + `<div id="brainState" class="small" style="margin-top:6px">${line} ${back}</div>`;
}

const swapping = (b) => ["unloading", "loading", "back"].includes(b?.state?.phase);
async function updateBrainBar(b) {
  const bar = $("#brainBar");
  if (!bar) return;
  b = b || await api("/api/models").catch(() => null);
  if (!b) return;
  S.brain = b;
  const st = b.state || {}, cur = b.models.find((m) => m.current);
  bar.classList.toggle("loading", swapping(b));
  bar.innerHTML = swapping(b)
    ? `<span class="g">⏳</span><span>${esc(BRAIN_PHASE[st.phase])} ${esc(st.phase === "unloading" ? st.frm : st.to)}… ${Math.max(0, Math.round(Date.now() / 1000 - st.started))} s</span>`
    : b.error && !b.models.length ? `<span class="g">🧠</span><span class="dim">LM Studio isn't answering</span>`
      : `<span class="g">🧠</span><span>${esc(cur ? cur.name : (S.state?.settings?.model || "no brain"))}</span>${cur && !cur.loaded ? `<span class="dim small">not loaded</span>` : ""}<span class="chev">▾</span>`;
  clearTimeout(updateBrainBar.t);
  if (swapping(b)) updateBrainBar.t = setTimeout(() => updateBrainBar(), 1500);
}
async function brainMenu(btn) {
  const b = await api("/api/models").catch(() => null);
  if (!b) return toast("LM Studio isn't answering", true);
  updateBrainBar(b);
  if (swapping(b)) return toast("A brain is loading right now");
  const k = (n) => n >= 1000 ? `${Math.round(n / 1024)}k` : String(n);
  const items = b.models.map((m) => ({
    id: m.key, g: m.current ? "●" : "○", label: m.name,
    sub: `${m.params} · ${m.size_gb} GB · ${k(m.max_context)} tokens${m.vision ? " · pictures" : ""}${m.tools ? " · tools" : ""}${m.current ? " · in use now" : m.loaded ? " · loaded" : ""}`,
    disabled: m.refused || "",
  }));
  const id = await openMenu(btn, [...items, "-", { id: "__settings", g: "⚙", label: "Brain settings", sub: "its test, creativity, steps" }]);
  if (id === "__settings") return showView("settings");
  const m = b.models.find((x) => x.key === id);
  if (m && !(m.current && m.loaded)) useBrain(id);
}

function wireBrain() {
  $$("[data-brain]").forEach((btn) => btn.addEventListener("click", () => useBrain(btn.dataset.brain)));
}
async function refreshBrain() {
  const box = $("#brainBox");
  if (!box) return;
  const b = await api("/api/models").catch(() => null);
  if (!b || !$("#brainBox")) return;
  $("#brainBox").innerHTML = brainList(b);
  wireBrain();
  if (["unloading", "loading", "back"].includes(b.state?.phase)) setTimeout(refreshBrain, 2000);
  else if (b.state?.phase === "done" || b.state?.phase === "failed") refreshState();
}
async function useBrain(key) {
  let c;
  toast("Checking what it needs…");
  try { c = await api("/api/models/check", { key }); } catch (e) { return toast(e.message, true); }
  if (c.refused) return confirmBox("Can't be its brain", c.refused);
  const fit = c.needs_gb == null ? "" : `It needs about ${c.needs_gb.toFixed(1)} GB of graphics memory${c.free_gb == null ? "" : `; about ${c.free_gb.toFixed(1)} GB would be free`}. `;
  const warn = c.warnings.length ? `Heads up: ${c.warnings.join("; ")}. ` : "";
  const ok = await confirmBox(`Use ${c.model.name} as its brain?`, `${fit}${warn}The one it uses now is unloaded first; if the new one doesn't load, it goes straight back. Its messages wait while it loads (~15-60 s). Run its test after.`);
  if (!ok) return;
  try { await api("/api/models/load", { key }); } catch (e) { return toast(e.message, true); }
  setTimeout(() => { refreshBrain(); updateBrainBar(); }, 500);
}

function confirmBox(title, text) {
  return new Promise((ok) => {
    openModal(`<h2>${esc(title)}</h2><p class="dim">${esc(text)}</p><div style="display:flex;margin-top:18px"><button class="btn" id="cNo" style="margin-left:auto">Cancel</button><button class="btn primary" id="cYes" style="margin-left:10px">Yes</button></div>`);
    $("#cNo").onclick = () => { closeOverlay(); ok(false); };
    $("#cYes").onclick = () => { closeOverlay(); ok(true); };
  });
}
function askText(title, value) {
  return new Promise((ok) => {
    openModal(`<h2>${esc(title)}</h2><input class="field" id="askIn" style="margin-top:16px" value="${esc(value || "")}"><div style="display:flex;margin-top:18px"><button class="btn" id="aNo" style="margin-left:auto">Cancel</button><button class="btn primary" id="aYes" style="margin-left:10px">Save</button></div>`);
    const inp = $("#askIn"); inp.focus(); inp.select();
    const done = (v) => { closeOverlay(); ok(v); };
    $("#aNo").onclick = () => done(null);
    $("#aYes").onclick = () => done(inp.value.trim());
    inp.onkeydown = (e) => { if (e.key === "Enter") done(inp.value.trim()); };
  });
}

async function plusMenu(btn) {
  btn.classList.add("on");
  const where = S.view === "newchat" ? "below" : "above";
  const id = await openMenu(btn, [
    { id: "images", g: "▧", label: "Upload images or PDFs", sub: "it sees pictures, reads PDFs" },
    { id: "library", g: "▤", label: "Add files to the Drop box", sub: "PDFs, notes, spreadsheets for it to read" },
    { id: "glance", g: "◎", label: "Share a screen glance", sub: "one look at what you're doing" },
    { id: "voice", g: "◉", label: "Voice note", sub: "Phase 3", disabled: "Voice comes in Phase 3" },
    { id: "skill", g: "✦", label: "Use a skill…", sub: "the skills it has installed" },
  ], where);
  if (id === "images") {
    addImages(await pickFiles("image/*,application/pdf,.pdf", true));
  } else if (id === "library") {
    const files = await pickFiles("", true);
    for (const f of files) {
      try { await api("/api/library", { name: f.name, data: await readFile(f) }); toast(`${f.name} added to the Drop box`); } catch (e) { toast(e.message, true); }
    }
  } else if (id === "glance") {
    try { toast("Taking one look…"); const g = await api("/api/glance", {}); S.attach.push(g); renderAttach(); } catch (e) { toast(e.message, true); }
  } else if (id === "skill") {
    const s = S.skills || (S.skills = await api("/api/skills"));
    const pick = await openMenu(btn, s.live.filter((k) => !k.builtin).sort((a, b) => a.name.localeCompare(b.name)).map((k) => ({ id: k.name, g: "✦", label: k.name, sub: k.description.slice(0, 40) + (k.description.length > 40 ? "…" : "") })), where);
    const ta = $("#input");
    if (pick && ta) { ta.value = `Use your ${pick} skill: ` + ta.value; ta.focus(); }
  }
  btn.classList.remove("on");
}

async function agentMenu(btn) {
  const id = await openMenu(btn, [
    { id: "rename", g: "✎", label: "Rename" },
    { id: "picture", g: "◐", label: "Change picture", sub: "upload a picture" },
    { id: "permissions", g: "◈", label: "Permission level", sub: `app: ${levelName(S.state?.settings?.permission_levels?.app || 0)}` },
    { id: "backup", g: "⤓", label: "Back up now", sub: "Aether's memory + chats" },
    "-",
    { id: "delete", g: "✕", label: `Delete ${name()}`, sub: "not from here", danger: true, disabled: "Aether never deletes it" },
  ], "right");
  if (id === "rename") {
    const v = await askText("Name in Aether", name());
    if (v) { await api("/api/settings", { display_name: v }).then(refreshState).catch((e) => toast(e.message, true)); }
  } else if (id === "picture") changePicture();
  else if (id === "permissions") permissionsModal();
  else if (id === "backup") backupNow();
}

async function folderMenu(btn) {
  const id = await openMenu(btn, [
    { id: "library", g: "▤", label: "Drop box", sub: "things you give it to read" },
    { id: "workspace", g: "▣", label: "Workspace", sub: "its own folder (level 2)" },
  ], "above");
  if (!id) return;
  const [path, what] = id === "library" ? ["/api/open-library", "the Drop box"] : ["/api/open-workspace", "the Workspace"];
  api(path, {}).then((r) => toast(`Opened ${what}: ${r.path}`)).catch((e) => toast(e.message, true));
}
async function changePicture() {
  const [f] = await pickFiles("image/*");
  if (!f) return;
  try { await api("/api/picture", { data: await readFile(f) }); toast("Picture changed"); refreshState(); } catch (e) { toast(e.message, true); }
}

const LEVELS = [
  [0, "Skills only", "Only its installed skills. Recommended while it runs on Gemma 12B."],
  [1, "Look around", "+ read-only commands: list and read files, disk space, running programs, git status."],
  [2, "Its workspace", "+ create and change things inside its own folder (its Workspace, Settings). Outside that folder it asks you."],
  [3, "Full command line", "Anything on this PC. Still asks you before anything on the always-ask list."],
];
const levelName = (n) => (LEVELS[n] || LEVELS[0])[1].toLowerCase();

function imagesLine() {
  const im = S.state?.images;
  if (!im) return "";
  const now = im.status ? im.status : im.waiting ? `${im.waiting} waiting` : "nothing waiting";
  return `${now} · ${im.made_today} of ${im.cap} today`;
}

const REACH_TO = [["latest", "your latest chat"], ["discord", "your Discord DMs"], ["new", "a new chat each time"], ["own", "its own chat (one, pinned)"]];
const reachSelect = (v) => `<select class="field" data-set="reach_out_to">${REACH_TO.map(([k, l]) => `<option value="${k}" ${(v || "latest") === k ? "selected" : ""}>${l}</option>`).join("")}</select>`;
const appLevel = () => Number(S.state?.settings?.permission_levels?.app || 0);

function permissionsModal() {
  const cur = { own: 0, ...(S.state?.settings?.permission_levels || { app: 0, discord: 0, avatar: 0 }) };
  let tab = "app";
  const draw = () => {
    openModal(`<h2>Permission level<button class="x" data-action="close">✕</button></h2>
      <div class="dim" style="font-size:15px;margin-top:4px">How much ${esc(name())} can do on this PC. Each place it lives gets its own level.</div>
      <div class="tabs">${[["app", "App"], ["discord", "Discord"], ["avatar", "Avatar"], ["own", "Its own time"]].map(([k, l]) => `<button class="tab${tab === k ? " on" : ""}" data-ptab="${k}">${l} <span class="faint small">Level ${cur[k] || 0}</span></button>`).join("")}
        <span class="faint small" style="margin-left:auto">Discord strangers: always talk-only</span></div>
      ${tab === "own" ? `<div class="dim small" style="margin-top:12px">Its heartbeats, the wake-ups it sets and your reminders firing. Nobody's there to OK anything then, so whatever would ask you first just doesn't run: it tells you about it later.</div>` : ""}
      <div style="display:flex;flex-direction:column;gap:10px;margin-top:16px">${LEVELS.map(([n, t, d]) => `<button class="level${(cur[tab] || 0) === n ? " on" : ""}" data-plevel="${n}"><span class="radio"></span>
        <div style="flex:1"><div style="font-size:17px"><span class="cyan mono" style="font-size:14px">Level ${n}</span>  ${t}</div><div class="dim" style="font-size:14px;margin-top:2px">${d}</div></div>
        ${n === 0 ? '<span class="tag cyan">recommended now</span>' : n >= 2 ? '<span class="tag">bigger models</span>' : ""}</button>`).join("")}</div>
      <div class="dim small" style="margin-top:18px">Always asks you first, at every level:</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px">${["deleting files", "installing software", "system settings and the registry", "services and shutting down", "network settings", "downloads and web requests"].map((t) => `<span class="lock">🔒 ${t}</span>`).join("")}</div>
      <div class="dim small" style="margin-top:10px">Every command it runs shows in the terminal panel and the audit log.</div>
      <div style="display:flex;margin-top:22px"><button class="btn" data-action="close" style="margin-left:auto">Cancel</button><button class="btn primary" style="margin-left:10px" id="pSave">Save</button></div>`);
    $$("[data-ptab]").forEach((b) => (b.onclick = () => { tab = b.dataset.ptab; draw(); }));
    $$("[data-plevel]").forEach((b) => (b.onclick = () => { cur[tab] = +b.dataset.plevel; draw(); }));
    $("#pSave").onclick = async () => {
      if (Object.values(cur).some((n) => n >= 2) && !(await confirmBox("Give it a real command line?",
        "Level 2 and 3 let it change things on this PC. On Gemma 12B it can misread what you meant. The always-ask list still applies."))) return draw();
      try { await api("/api/settings", { permission_levels: cur }); closeOverlay(); toast("Saved"); refreshState(); }
      catch (e) { toast(e.message, true); }
    };
  };
  draw();
}

async function profileCard() {
  const L = S.state.agent;
  let grid = [];
  try { grid = await api("/api/activity"); } catch (e) {  }
  const max = Math.max(1, ...grid.flat());
  const born = L.born ? new Date(L.born + "T12:00").toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }) : "?";
  $("#overlay").innerHTML = `<div class="scrim" data-action="close"></div><div class="profile">
    <div class="pic"><img src="${picUrl()}" alt=""><span class="lbl">PROFILE</span><button class="chg" data-action="picture">✎ Change picture</button></div>
    <div class="body"><div style="display:flex;align-items:center;gap:10px"><span style="font-family:var(--display);font-size:30px">${esc(L.name)}</span>
      <button class="mono small dim" style="border:1px solid var(--line);border-radius:6px;padding:2px 7px" data-copy="${esc(L.id)}">ID ⧉</button></div>
      <div class="cyan" style="font-size:13px;letter-spacing:1px">${esc(L.full_name)}</div>
      <div class="dim" style="font-size:15px;margin-top:6px">${esc(L.tagline)}</div>
      <div class="faint" style="font-size:13px;margin-top:6px">Born ${esc(born)} · ${L.age_days ?? "?"} days old · ${esc(L.model.split("/").pop())} · ${esc(L.permission)}</div>
      <div class="tiles">${[[L.stats.core, "core"], [L.stats.other, "other files"], [L.stats.skills, "skills"], [L.stats.commits, "memory commits"]].map(([n, l]) => `<div class="tile"><b>${n}</b><span>${l}</span></div>`).join("")}</div>
      <div class="activity"><div class="eyebrow">ACTIVITY · ${grid.length} DAYS</div><div class="grid">${grid.map((day) => `<div class="col">${day.map((v) => `<i style="opacity:${(0.12 + 0.88 * (v / max)).toFixed(2)}"></i>`).join("")}</div>`).join("")}</div></div>
    </div></div>`;
}

let searchTimer;
function openSearch() {
  $("#overlay").innerHTML = `<div class="scrim" data-action="close"></div><div class="search"><input id="searchIn" placeholder="Search your chats and its memory…"><div class="res" id="searchRes"></div></div>`;
  const inp = $("#searchIn");
  inp.focus();
  inp.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => runSearch(inp.value), 200); });
}

const markQ = (s, q) => esc(s).replace(new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/&/g, "&amp;").replace(/</g, "&lt;"), "gi"), (m) => `<mark>${m}</mark>`);
async function runSearch(q) {
  const box = $("#searchRes");
  if (!box) return;
  if (q.trim().length < 2) { box.innerHTML = ""; return; }
  const hits = await api(`/api/search?q=${encodeURIComponent(q)}`).catch(() => []);
  const mark = (s) => markQ(s, q);
  const row = (h) => {
    if (h.type === "chat") return `<button class="r" data-chat="${esc(h.id)}"><div class="k">${icon("chat")} ${esc(h.title)} · ${esc(h.who)} · ${esc(ago(h.ts))}</div><div class="s">${mark(h.snippet)}</div></button>`;
    if (h.type === "memory" || h.line) return `<button class="r" data-file="${esc(h.path)}"><div class="k">${icon("brain")} ${esc(h.path)} · line ${h.line}</div><div class="s">${mark(h.snippet)}</div></button>`;
    return h.kind === "chat"
      ? `<button class="r" data-chat="${esc(h.id)}"><div class="k">≈ by meaning · ${esc(h.title)} · ${esc(ago(h.ts))}</div><div class="s">${esc(h.snippet)}</div></button>`
      : `<button class="r" data-file="${esc(h.path)}"><div class="k">≈ by meaning · ${esc(h.path)}</div><div class="s">${esc(h.snippet)}</div></button>`;
  };
  box.innerHTML = hits.length ? hits.map(row).join("") : `<div class="r dim">Nothing found.</div>`;
}

async function chatMenu(el, id) {
  const c = S.state.chats.find((x) => x.id === id);
  if (!c) return;
  const pick = await openMenu(el, [
    { id: "pin", g: "📌", label: c.pinned ? "Unpin" : "Pin", sub: c.archived ? "brings it back from the archive" : "" },
    { id: "rename", g: "✎", label: "Rename" },
    { id: "archive", g: "🗄", label: c.archived ? "Unarchive" : "Archive", sub: c.archived ? "back to your chats" : "out of the list, not deleted" },
    { id: "compact", g: "⇣", label: "Compact", sub: "it sums the chat up and carries on from its note (or type /compact)" },
    ...(c.compacted ? [{ id: "uncompact", g: "↶", label: "Undo compact", sub: "takes its latest note back; it sees the chat as before" }] : []),
    "-",
    { id: "delete", g: "✕", label: "Delete chat", sub: "set aside, not erased", danger: true },
  ], "right");
  try {
    if (pick === "pin") await api("/api/chat/pin", { id, pinned: !c.pinned });
    else if (pick === "archive") { await api("/api/chat/archive", { id, archived: !c.archived }); toast(c.archived ? "Back in your chats" : "Archived: out of the list, not deleted"); }
    else if (pick === "rename") { const t = await askText("Rename chat", c.title); if (t !== null) await api("/api/chat/rename", { id, title: t }); }
    else if (pick === "compact") { if (S.chat?.id !== id) await openChat(id); return compactChat(id); }
    else if (pick === "uncompact") {
      await api("/api/chat/uncompact", { id });
      toast(`Compact undone: ${name()} sees this chat as before`);
      if (S.chat?.id === id) return openChat(id, true);
    }
    else if (pick === "delete") {
      if (!(await confirmBox("Delete this chat?", "It's moved to ~/.aether/conversations/_trash, not erased. Its memory keeps anything it saved from it."))) return;
      await api("/api/chat/delete", { id });
      if (S.chat?.id === id) { S.chat = null; await refreshState(); return openChat(S.state.current); }
    }
    await refreshState();
    if (S.chat?.id === id && S.view === "chat") renderChat();
  } catch (e) { toast(e.message, true); }
}

document.addEventListener("click", async (e) => {
  const t = e.target;
  const el = (sel) => t.closest(sel);
  if (el("[data-chat-menu]")) { e.stopPropagation(); return chatMenu(el("[data-chat-menu]"), el("[data-chat-menu]").dataset.chatMenu); }
  if (el("[data-chat]")) { closeOverlay(); return openChat(el("[data-chat]").dataset.chat); }
  if (el(".life-row.link")) return openLifeRow(el(".life-row.link"));
  if (el("[data-file]")) {
    const p = el("[data-file]").dataset.file;
    closeOverlay();
    if (S.view === "brain" && $("#fileview")) return openFile(p);
    showView("brain"); setTimeout(() => openFile(p), 300); return;
  }
  if (el("[data-view]")) return showView(el("[data-view]").dataset.view);
  if (el("[data-suggest]")) return send(el("[data-suggest]").dataset.suggest);
  if (el("[data-answer]")) { const b = el("[data-answer]"); return api("/api/answer", { qid: b.dataset.answer, allow: b.dataset.allow === "1" }); }
  if (el("[data-proposal]")) {
    const b = el("[data-proposal]");
    let note = "";
    if (b.dataset.note) {
      note = window.prompt("Send it back with a note (what's missing or wrong):", "") || "";
      if (!note.trim()) return;
    }
    return api("/api/proposal", { id: b.dataset.proposal, answer: b.dataset.reply, note })
      .then(() => { toast(`You said ${b.dataset.reply}`); refreshState(); if (S.chat) openChat(S.chat.id, true); if (S.view === "heartbeat") showView("heartbeat"); })
      .catch((err) => toast(String(err.message || err), true));
  }
  if (el("[data-unattach]")) { S.attach.splice(+el("[data-unattach]").dataset.unattach, 1); return renderAttach(); }
  if (el("[data-rewind]")) return rewind(el("[data-rewind]").dataset.rewind);
  if (el("[data-forget]")) return forgetMemory(el("[data-forget]").dataset.forget);
  if (el("[data-edit]")) return editFile(el("[data-edit]").dataset.edit);
  if (el("[data-commit]")) return selectCommit(el("[data-commit]").dataset.commit);
  if (el("[data-findfile]")) { const b = el("[data-findfile]"); return openFile(b.dataset.findfile, null, +b.dataset.findn || 0); }
  if (el("[data-difffile]")) { B.file = el("[data-difffile]").dataset.difffile; return renderFileview(); }
  if (el("[data-zoom]")) { B.view?.zoomBy(+el("[data-zoom]").dataset.zoom); return; }
  if (el("[data-rate]")) {
    const b = el("[data-rate]"), code = b.dataset.key || "", box = b.parentElement;
    const rating = b.classList.contains("on") ? "none" : b.dataset.rate;
    try {
      const r = await api("/api/music/rate", { code, rating });
      S.ratings = { ...(S.ratings || {}) };
      if (rating === "none") delete S.ratings[r.id]; else S.ratings[r.id] = rating;
      box.querySelectorAll("[data-rate]").forEach((x) => x.classList.toggle("on", x.dataset.rate === rating));
      return toast(rating === "none" ? "Rating taken back" : `Told ${name()}: ${rating === "up" ? "👍" : "👎"}`);
    } catch (err) { return toast(String(err.message || err), true); }
  }
  if (el("[data-copy-code]")) {
    const code = el(".codebox")?.querySelector("code")?.textContent || "";
    return copyText(code).then((ok) => (ok ? toast("Code copied") : toast("Couldn't copy", true)));
  }
  if (el("[data-copy]")) { navigator.clipboard?.writeText(el("[data-copy]").dataset.copy); return toast("ID copied"); }
  if (el("[data-life]")) {
    const act = el("[data-life]").dataset.life;
    try {
      const r = await api(`/api/life/${act}`, {});
      toast(act === "checkup" ? `Checkup: ${r.issues.length} thing(s) to look at` : "Started; it shows up here when it's done");
      if (act === "checkup") showView("heartbeat");
    } catch (e) { toast(e.message, true); }
    return;
  }
  if (el("[data-wake-cancel]")) {
    await api("/api/life/wakeup-cancel", { id: el("[data-wake-cancel]").dataset.wakeCancel }).catch((err) => toast(err.message, true));
    return showView("heartbeat");
  }
  if (el("[data-cal-edit]")) {
    const x = (S.cal || []).find((c) => c.id === el("[data-cal-edit]").dataset.calEdit);
    return x ? addCalendar(x) : renderCalendar();
  }
  if (el("[data-cal-del]")) {
    if (await confirmBox("Cancel this date?", "It comes off the calendar and its reminders won't go off. It's a commit, so you can rewind it on the Brain page.")) {
      await api("/api/life/calendar-cancel", { id: el("[data-cal-del]").dataset.calDel }).catch((e) => toast(e.message, true));
      renderCalendar();
    }
    return;
  }
  if (el("[data-cal-month]")) {
    const [y, m] = S.calMonth, d = new Date(y, m + Number(el("[data-cal-month]").dataset.calMonth), 1);
    S.calMonth = [d.getFullYear(), d.getMonth()];
    return renderCalendar();
  }
  if (el("[data-cal-add-on]")) return addCalendar(null, el("[data-cal-add-on]").dataset.calAddOn);
  if (el("[data-cal-day]")) return viewCalendarDay(el("[data-cal-day]").dataset.calDay);
  if (el("[data-sched-edit]")) {
    const x = (S.schedules || []).find((s) => s.id === el("[data-sched-edit]").dataset.schedEdit);
    return x ? addSchedule(x) : toast("That reminder is gone; the page will refresh", true);
  }
  if (el("[data-sched-del]")) {
    if (await confirmBox("Delete this reminder?", "It stops firing. You can add it again any time.")) {
      await api("/api/life/schedule-update", { id: el("[data-sched-del]").dataset.schedDel, delete: true }).catch((e) => toast(e.message, true));
      showView("heartbeat");
    }
    return;
  }
  if (el("[data-lightbox]")) return openLightbox(el("[data-lightbox]").dataset.lightbox);
  if (el("[data-img]")) return openImage(+el("[data-img]").dataset.img);
  if (el("[data-img-chat]")) { const id = el("[data-img-chat]").dataset.imgChat; closeOverlay(); return openChat(id); }
  if (el("[data-img-cancel]")) {
    try { const r = await api("/api/images/cancel", { id: el("[data-img-cancel]").dataset.imgCancel }); renderImageQueue(r.images); toast("Cancelled"); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (el("[data-say]")) {
    const ev = S.chat?.events[+el("[data-say]").dataset.say];
    Player.clear();
    return ev && api("/api/speak", { text: ev.text, chat: S.chat.id }).catch((err) => toast(err.message, true));
  }
  if (t.matches("[data-close-back]")) return closeOverlay();
  const a = el("[data-action]");
  if (!a) return;
  switch (a.dataset.action) {
    case "send": return send();
    case "retry": return retry();
    case "library": return folderMenu(a);
    case "mic": return Mic.on ? Mic.stop() : Mic.start();
    case "stop": return stop();
    case "plus": return plusMenu(a);
    case "new-chat": return newChat();
    case "agent-menu": return agentMenu(a);
    case "profile": return profileCard();
    case "picture": closeOverlay(); return changePicture();
    case "permissions": return permissionsModal();
    case "search": return openSearch();
    case "term": return Term.toggle();
    case "term-stop": return api("/api/term/stop", {}).catch(() => {});
    case "pet":
      if (window.aetherDesktop) return window.aetherDesktop.togglePet();
      return toast("Pet mode needs the Aether app (the desktop icon), not a browser tab.");
    case "brain-all": B.view?.resetView(); return;
    case "add-sched": return addSchedule();
    case "add-cal": return addCalendar(null);
    case "toggle-cal-past": S.calPast = !S.calPast; return renderCalendar();
    case "close": return closeOverlay();
    case "toggle-recent": S.recentOpen = !S.recentOpen; return renderChatList();
    case "toggle-archive": S.archiveOpen = !S.archiveOpen; return renderChatList();
    case "fold-compact": {
      const id = S.chat?.id;
      if (id) { if (S.unfolded.has(id)) S.unfolded.delete(id); else S.unfolded.add(id); }
      return renderMessages();
    }
    case "show-all": S.showAll = !S.showAll; return renderChatList();
    case "brain-map": return reading(false);
    case "older": {
      const more = await api(`/api/commits?n=40&skip=${B.commits.length}`).catch(() => []);
      B.commits.push(...more); return renderHistory();
    }
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if ($("#overlay").innerHTML) return closeOverlay();
    if (Mic.on) { e.preventDefault(); return Mic.stop(true); }
    if (S.busy) { e.preventDefault(); return stop(); }
    if (Player.busy) { e.preventDefault(); Player.clear(); return api("/api/voice/stop", {}).catch(() => {}); }
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openSearch(); }
  if (e.ctrlKey && e.key === "`") { e.preventDefault(); Term.toggle(); }
});

function drawSpace(canvas, stars = 140, brain = { x: 0.7, y: 0.78, n: 170, a: 0.3 }) {
  const r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  canvas.width = r.width * dpr; canvas.height = r.height * dpr;
  const g = canvas.getContext("2d");
  g.scale(dpr, dpr);
  const w = r.width, h = r.height;
  const bg = (x, y, rad, c) => { const gr = g.createRadialGradient(x, y, 0, x, y, rad); gr.addColorStop(0, c); gr.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = gr; g.fillRect(0, 0, w, h); };
  const css = getComputedStyle(document.documentElement), v = (k) => css.getPropertyValue(k).trim();
  g.fillStyle = v("--space-bg"); g.fillRect(0, 0, w, h);
  bg(w * 0.5, h * 0.5, Math.max(w, h) * 0.75, v("--space-mid"));
  bg(w * 0.2, h * 0.15, Math.max(w, h) * 0.45, v("--space-neb1"));
  bg(w * 0.85, h * 0.8, Math.max(w, h) * 0.45, v("--space-neb2"));
  const rnd = seeded("aether-space");
  for (let i = 0; i < stars; i++) { g.globalAlpha = 0.2 + rnd() * 0.7; g.fillStyle = v("--star"); g.beginPath(); g.arc(rnd() * w, rnd() * h, rnd() * 1.2 + 0.2, 0, 7); g.fill(); }
  if (brain) {
    const bx = w * brain.x, by = h * brain.y;
    bg(bx, by, 150, `rgba(${v("--gold-rgb")},${0.55 * brain.a * 2})`);
    for (let i = 0; i < brain.n; i++) {
      const side = i % 2 ? 1 : -1, a = rnd() * Math.PI * 2, rr = Math.sqrt(rnd());
      g.globalAlpha = brain.a; g.fillStyle = side > 0 ? v("--cyan") : v("--violet");
      g.beginPath(); g.arc(bx + side * (14 + 62 * rr * Math.abs(Math.cos(a))), by + 48 * rr * Math.sin(a), 0.7 + rnd() * 1.1, 0, 7); g.fill();
    }
  }
  g.globalAlpha = 1;
}
function redrawAll() { drawSpace($("#sideSpace")); }
window.addEventListener("resize", () => { clearTimeout(redrawAll.t); redrawAll.t = setTimeout(redrawAll, 120); });

(async function start() {
  fillIcons();
  connect();
  await refreshState();
  await loadRatings();
  redrawAll();
  if (S.state) await openChat(S.state.current);
  $("#brainBar").addEventListener("click", (e) => brainMenu(e.currentTarget));
  updateBrainBar();
  setInterval(() => { if (!S.busy) refreshState(); }, 10000);
  setInterval(() => { if (!S.busy) updateBrainBar(); }, 60000);
})();
