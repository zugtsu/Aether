"use strict";

function mountBrain3D(box, DATA, cb) {
  const cv = document.createElement("canvas");
  cv.className = "b3d";
  box.appendChild(cv);
  const tip = document.createElement("div");
  tip.className = "b3d-tip";
  box.appendChild(tip);
  const cx = cv.getContext("2d");
  let W = 0, H = 0, DPR = 1, alive = true;
  function resize() {
    const r = box.getBoundingClientRect();
    DPR = Math.min(2, window.devicePixelRatio || 1); W = r.width; H = r.height;
    cv.width = W * DPR; cv.height = H * DPR; cx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  const ro = new ResizeObserver(resize); ro.observe(box); resize();

  const M = DATA.meta, R = M.regions;
  const col = (r) => r === "core" ? "#eafff4" : (R[r] ? R[r].color : "#46f09a");
  let seed = 1337; const rnd = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
  const gauss = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const SX = 1.25, SY = 0.92, SZ = 1.0;
  const N = DATA.nodes;

  const TREE = cb && cb.style === "neuron" && typeof BrainNeuron === "function" ? BrainNeuron(DATA, rnd, gauss)
    : cb && cb.style === "tree" && typeof BrainTree === "function" ? BrainTree(DATA, rnd, gauss) : null;
  if (TREE) TREE.place(); else placeConstellation();
  function placeConstellation() {
  N.forEach((n) => {
    if (n.k === "core") { n.x = n.y = n.z = 0; return; }
    const c = R[n.region] ? R[n.region].center : [0, 0, 0];
    if (n.k === "region") { n.x = c[0] * .72; n.y = c[1] * .72; n.z = c[2] * .72; }
  });
  N.forEach((n) => { if (n.k !== "file") return; const c = R[n.region].center; n.x = c[0] + gauss() * .16; n.y = c[1] + gauss() * .14; n.z = c[2] + gauss() * .16; });

  const WK = N.filter((n) => n.group).sort((a, b) => (a.label < b.label ? -1 : 1));
  WK.forEach((n, i) => { const c = R[n.region].center; n.x = c[0] + (i - (WK.length - 1) / 2) * .3; n.y = c[1] + Math.sin(i * 1.7) * .06; n.z = c[2] + Math.cos(i * 1.3) * .1; });
  const fileIdx = {}; N.forEach((n) => { if (n.k === "file") fileIdx[n.label] = n; });

  const CH = N.filter((n) => n.k === "chat");
  CH.forEach((n, i) => {
    const u = CH.length > 1 ? i / (CH.length - 1) : 0, a = u * Math.PI * 3 + 1.2;
    n.x = Math.cos(a) * .98; n.y = -.4 + u * .82; n.z = Math.sin(a) * .98 * .85;
  });
  N.forEach((n) => {
    if (n.k !== "mem") return; const f = fileIdx[n.at || n.file] || { x: 0, y: 0, z: 0 };
    const r = n.at ? .06 + rnd() * .2 : .08 + rnd() * .24, th = rnd() * Math.PI * 2, ph = Math.acos(2 * rnd() - 1);
    n.x = f.x + r * Math.sin(ph) * Math.cos(th); n.y = f.y + r * Math.cos(ph); n.z = f.z + r * Math.sin(ph) * Math.sin(th);
  });
  N.forEach((n) => { n.x *= SX; n.y *= SY; n.z *= SZ; });
  }
  const DUST = [];
  for (let i = 0; i < 2200; i++) {
    const side = i % 2 ? 1 : -1; let x, y, z, d;
    do { x = rnd() * 2 - 1; y = rnd() * 2 - 1; z = rnd() * 2 - 1; d = x * x + y * y / .8 + z * z / .95; } while (d > 1);
    const shell = Math.pow(rnd(), .35); x *= shell; y *= shell; z *= shell;
    x = side * (Math.abs(x) * .62 + .07); DUST.push({ x: x * SX * 1.12, y: y * SY * 1.05, z: z * SZ * 1.05, a: .15 + rnd() * .5, tw: rnd() * 6.28 });
  }
  const DL = [];
  for (let i = 0; i < 420; i++) {
    const a = DUST[(rnd() * DUST.length) | 0]; let best = null, bd = 1e9;
    for (let j = 0; j < 24; j++) { const b = DUST[(rnd() * DUST.length) | 0]; if (b === a) continue; const dd = (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2; if (dd < bd) { bd = dd; best = b; } }
    if (best && bd < .06) DL.push([a, best]);
  }
  const L = DATA.links.map(([a, b, t]) => ({ a: N[a], b: N[b], t }));

  const O = DATA.organs || {};
  const SCOL = { live: "#46f09a", ok: "#4fd6ff", down: "#ff5c6c", you: "#ff7a9c", busy: "#f5c86b", off: "#566079" };
  const SLAB = { live: "LIVE", ok: "OK", down: "DOWN", you: "YOU", busy: "THINKING", off: "LATER" };
  const ORBIT = { user: [180, .05], ears: [148, .42], voice: [118, .78], avatar: [212, .38], discord: [244, -.35],
    heartbeat: [322, -.62], dreams: [290, -.2], lmstudio: [0, .22], pictures: [62, -.48],
    cue: [30, .6], keeper: [266, .58], nudge: [198, -.62] };
  const ORG = [];
  Object.entries(ORBIT).forEach(([k, [a, h]]) => {
    if (!O[k]) return; const r = a * Math.PI / 180;
    ORG.push({ key: k, x: Math.cos(r) * 1.3 * SX * .95, y: h * SY, z: Math.sin(r) * 1.3 * .9, name: O[k].name.toUpperCase() });
  });
  const OK = {}; ORG.forEach((o) => (OK[o.key] = o));
  const REGN = {}; N.forEach((n) => { if (n.k === "region") REGN[n.region] = n; });
  const CORE = N.find((n) => n.k === "core");
  const NERVES = [["user", "ears"], ["ears", CORE], ["user", "discord"], ["discord", CORE], ["voice", CORE], ["avatar", "voice"],
    ["lmstudio", CORE], ["lmstudio", REGN.self], ["heartbeat", CORE], ["heartbeat", REGN.journal], ["dreams", REGN.journal], ["pictures", CORE],
    ["cue", REGN.chats], ["cue", CORE], ["keeper", REGN.chats], ["keeper", REGN.notebook], ["nudge", REGN.notebook], ["nudge", "user"]]
    .map(([a, b], i) => ({ a: OK[a], b: typeof b === "string" ? OK[b] : b, ka: a, kb: typeof b === "string" ? b : null, ph: (i * .37) % 1 }))
    .filter((e) => e.a && e.b);
  const st = (k) => (O[k] ? O[k].state : "down");

  const sprites = {};
  function sprite(c) {
    if (sprites[c]) return sprites[c];
    const s = document.createElement("canvas"); s.width = s.height = 64;
    const g = s.getContext("2d"), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, "#fff"); gr.addColorStop(.12, c); gr.addColorStop(.4, c + "55"); gr.addColorStop(1, c + "00");
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64); return (sprites[c] = s);
  }

  let rotY = 0, rotX = -.18, zoom = 1, auto = true, drag = null, hover = null, mx = -1, my = -1, hoverOrg = null;

  const SPIRITS = TREE && TREE.organAt;
  const hidden = new Set();
  let hot = new Set();
  const pos = (e) => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  cv.addEventListener("mousedown", (e) => { const [x, y] = pos(e); drag = { x, y, ry: rotY, rx: rotX, moved: false }; auto = false; });
  const up = (e) => {
    if (drag && !drag.moved && e.target === cv) click();
    drag = null; setTimeout(() => (auto = true), 5000);
  };
  const move = (e) => {
    const [x, y] = pos(e); mx = x; my = y;
    if (drag) {
      if (Math.abs(x - drag.x) + Math.abs(y - drag.y) > 4) drag.moved = true;
      rotY = drag.ry + (x - drag.x) * .006; rotX = Math.max(-1.2, Math.min(1.2, drag.rx + (y - drag.y) * .006));
    }
  };
  window.addEventListener("mouseup", up);
  window.addEventListener("mousemove", move);
  cv.addEventListener("mouseleave", () => { mx = my = -1; });
  cv.addEventListener("wheel", (e) => { e.preventDefault(); zoom = Math.max(.5, Math.min(3, zoom * (e.deltaY < 0 ? 1.08 : .93))); }, { passive: false });

  let best = null;
  function click() {
    if (!best) return;
    if (best.organ) return cb.organ && cb.organ(best.organ, O[best.organ]);
    if (best.k === "region") { if (hidden.size === Object.keys(R).length - 1 && !hidden.has(best.region)) hidden.clear(); else { hidden.clear(); Object.keys(R).forEach((k) => { if (k !== best.region) hidden.add(k); }); } return; }
    if (best.k === "core") return cb.open(best.file || "system/persona.md");
    if (best.k === "chat") return cb.chat && cb.chat(best.chat);
    if (best.file) cb.open(best.file, best.k === "mem" ? best.find : null);
  }

  function proj(p, cy, sy, cxr, sxr, sc) {
    const x = p.x * cy - p.z * sy, z = p.x * sy + p.z * cy, y = p.y;
    const y2 = y * cxr - z * sxr, z2 = y * sxr + z * cxr, f = 3.2 / (3.2 + z2);
    return { x: W / 2 + x * sc * f, y: H * .45 - y2 * sc * f, z: z2, f };
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function frame(ts) {
    if (!alive || !cv.isConnected) { destroy(); return; }

    if (!cv.offsetParent) { requestAnimationFrame(frame); return; }
    const t = ts / 1000; if (auto && !drag) rotY += .0016;
    const cy = Math.cos(rotY), sy = Math.sin(rotY), cxr = Math.cos(rotX), sxr = Math.sin(rotX),
      sc = Math.min(W / 3.7, H / 2.6) * zoom;
    cx.globalCompositeOperation = "source-over"; cx.fillStyle = "#04070a"; cx.fillRect(0, 0, W, H);
    if (TREE && TREE.backdrop) TREE.backdrop(cx, W, H);
    cx.strokeStyle = "rgba(70,240,154,.05)"; cx.lineWidth = 1;
    for (let i = -10; i <= 10 && !(TREE && TREE.backdrop); i++) {
      const a = proj({ x: i * .3, y: -1.25, z: -3 }, cy, sy, cxr, sxr, sc), b = proj({ x: i * .3, y: -1.25, z: 3 }, cy, sy, cxr, sxr, sc);
      cx.beginPath(); cx.moveTo(a.x, a.y); cx.lineTo(b.x, b.y); cx.stroke();
      const c = proj({ x: -3, y: -1.25, z: i * .3 }, cy, sy, cxr, sxr, sc), d = proj({ x: 3, y: -1.25, z: i * .3 }, cy, sy, cxr, sxr, sc);
      cx.beginPath(); cx.moveTo(c.x, c.y); cx.lineTo(d.x, d.y); cx.stroke();
    }
    cx.globalCompositeOperation = "lighter";
    cx.lineWidth = .6;
    DL.forEach(([a, b]) => { const A = proj(a, cy, sy, cxr, sxr, sc), B = proj(b, cy, sy, cxr, sxr, sc); cx.strokeStyle = `rgba(90,255,170,${.05 + .07 * (1 - (A.z + 1.5) / 3)})`; cx.beginPath(); cx.moveTo(A.x, A.y); cx.lineTo(B.x, B.y); cx.stroke(); });
    const dsp = sprite(TREE && TREE.dust || "#8fffd6");
    DUST.forEach((p) => { const q = proj(p, cy, sy, cxr, sxr, sc); const s = (2.2 + 2.4 * q.f) * (.6 + .4 * Math.sin(t * 1.3 + p.tw)); cx.globalAlpha = p.a * (.45 + .55 * (1 - (q.z + 1.5) / 3)); cx.drawImage(dsp, q.x - s, q.y - s, s * 2, s * 2); });
    cx.globalAlpha = 1;
    N.forEach((n) => { const q = proj(n, cy, sy, cxr, sxr, sc); n.sx = q.x; n.sy = q.y; n.sz = q.z; n.sf = q.f; n.vis = !hidden.has(n.region); });
    const tg = TREE && { cx, P: (p) => proj(p, cy, sy, cxr, sxr, sc), sprite, t, hidden, mini: false };
    if (TREE) TREE.draw(tg);
    L.forEach((l) => {
      if (!l.a.vis || !l.b.vis) return;
      if (TREE && (TREE.keepLink ? !TREE.keepLink(l) : !(l.t === "tree" && l.a.k === "region" && l.b.k === "file"))) return; const a = l.a, b = l.b, c = col(b.region === "core" ? a.region : b.region);
      const w = { spine: .34, tree: .22, leaf: .13, mention: .30, echo: .09 }[l.t]; const hl = hover && (hover === a || hover === b);
      cx.strokeStyle = c + (hl ? "ee" : Math.round(w * 255).toString(16).padStart(2, "0")); cx.lineWidth = hl ? 1.4 : (l.t === "echo" ? .5 : .8);
      cx.beginPath(); cx.moveTo(a.sx, a.sy);
      if (l.t === "echo" || l.t === "mention") cx.quadraticCurveTo((a.sx + b.sx) / 2, (a.sy + b.sy) / 2 - 18, b.sx, b.sy); else cx.lineTo(b.sx, b.sy);
      cx.stroke();
    });
    best = null; let bd = 14 * 14;
    N.filter((n) => n.vis).sort((a, b) => b.sz - a.sz).forEach((n) => {
      const c = col(n.region), pulse = n.k === "core" ? 1 + .12 * Math.sin(t * 2) : 1, s = n.size * (3.2 + 4 * n.sf) * pulse;
      if (TREE && n.k === "mem") TREE.leaf(tg, n, c);
      else { const z = TREE && n.k === "chat" ? s * .6 : s;
        cx.globalAlpha = n.old ? .5 : n.at ? .55 : n.k === "mem" ? .9 : 1; cx.drawImage(sprite(c), n.sx - z, n.sy - z, z * 2, z * 2); cx.globalAlpha = 1; }
      if (n.k === "file" && hot.has(n.label)) { cx.strokeStyle = "#43c3cb"; cx.lineWidth = 2; cx.beginPath(); cx.arc(n.sx, n.sy, 12 + 3 * Math.sin(t * 3), 0, 7); cx.stroke(); }
      const dd = (n.sx - mx) ** 2 + (n.sy - my) ** 2;
      if (dd < (n.k === "core" ? Math.max(bd, 26 * 26) : n.k === "region" ? Math.max(bd, 18 * 18) : bd)) { bd = dd; best = n; }
    });
    if (SPIRITS) ORG.forEach((o, i) => Object.assign(o, TREE.organAt(i, ORG.length, t)));
    ORG.forEach((o) => { const q = proj(o, cy, sy, cxr, sxr, sc); o.sx = q.x; o.sy = q.y; o.sz = q.z; o.sf = q.f; });
    NERVES.forEach((e) => {
      if (SPIRITS && (!hoverOrg || (hoverOrg !== e.ka && hoverOrg !== e.kb))) return;
      const A = e.a, B = e.b, sa = st(e.ka), sb = e.kb ? st(e.kb) : "ok";
      const on = !["down", "off"].includes(sa) && !["down", "off"].includes(sb);
      const c = on ? SCOL[sa] : sa === "off" || sb === "off" ? SCOL.off : "#ff5c6c";
      const mx2 = (A.sx + B.sx) / 2, my2 = (A.sy + B.sy) / 2 - 26 * A.sf;
      cx.strokeStyle = c + (on ? "66" : "40"); cx.lineWidth = on ? 1.2 : .9; cx.setLineDash(on ? [] : [4, 6]);
      cx.beginPath(); cx.moveTo(A.sx, A.sy); cx.quadraticCurveTo(mx2, my2, B.sx, B.sy); cx.stroke(); cx.setLineDash([]);
      if (on) for (let j = 0; j < 2; j++) {
        const u = (t * .2 + e.ph + j * .5) % 1, x = (1 - u) * (1 - u) * A.sx + 2 * (1 - u) * u * mx2 + u * u * B.sx, y = (1 - u) * (1 - u) * A.sy + 2 * (1 - u) * u * my2 + u * u * B.sy;
        cx.drawImage(sprite(c), x - 6, y - 6, 12, 12);
      }
    });
    if (SPIRITS) ORG.forEach((o, i) => {
      const c = SCOL[st(o.key)] || SCOL.ok;
      for (let k = 1; k <= 6; k++) {
        const q = proj(TREE.organAt(i, ORG.length, t - k * .09), cy, sy, cxr, sxr, sc), z = (9 - k) * (.7 + .4 * q.f);
        cx.globalAlpha = .4 - k * .055; cx.drawImage(sprite(c), q.x - z, q.y - z, z * 2, z * 2);
      }
      cx.globalAlpha = 1;
    });
    ORG.forEach((o) => {
      const s = st(o.key), c = SCOL[s], pul = s === "live" ? 1 + .1 * Math.sin(t * 2.4 + o.x * 3) : 1;
      const r = (o.key === "user" ? 16 : 13) * (.75 + .5 * o.sf) * pul * (s === "down" || s === "off" ? .75 : 1);
      cx.globalAlpha = s === "down" || s === "off" ? .6 : 1; cx.drawImage(sprite(c), o.sx - r * 2, o.sy - r * 2, r * 4, r * 4); cx.globalAlpha = 1;
      if (o.key === "pictures") {
        const n = Math.min(60, O.pictures.count || 0), gs = sprite("#f5c86b");
        for (let i = 0; i < n; i++) {
          const a = t * (.25 + (i % 3) * .07) + i * 2.39996, rr = (24 + (i % 5) * 6) * (.75 + .5 * o.sf), z = 3 + 1.5 * (i % 2);
          cx.drawImage(gs, o.sx + Math.cos(a) * rr - z, o.sy + Math.sin(a) * rr * .45 - z, z * 2, z * 2);
        }
      }
      const dd = (o.sx - mx) ** 2 + (o.sy - my) ** 2; if (dd < Math.max(bd, 22 * 22)) { bd = dd; best = { organ: o.key }; }
    });
    cx.globalCompositeOperation = "source-over"; cx.textAlign = "center";
    ORG.forEach((o) => {
      const s = st(o.key); cx.font = "11px Consolas,monospace"; cx.fillStyle = "#d6efe2"; cx.globalAlpha = .9; cx.fillText(o.name, o.sx, o.sy + 30);
      cx.font = "9.5px Consolas,monospace"; cx.fillStyle = SCOL[s]; cx.fillText(O[o.key].label || SLAB[s], o.sx, o.sy + 42);
    });
    cx.globalAlpha = 1;
    if (CORE) { cx.font = "600 11px Consolas,monospace"; cx.fillStyle = "#effff6"; cx.globalAlpha = .9; cx.fillText("SOUL", CORE.sx, CORE.sy + 30 * CORE.sf); }
    cx.font = "11px Consolas,monospace";
    N.forEach((n) => {
      if (!n.vis) return;
      if (n.k === "region") { cx.fillStyle = col(n.region); cx.globalAlpha = .85; cx.fillText(n.label.toUpperCase(), n.sx, n.sy - 14); }
      else if (n.k === "file" && (n.short || n.label.endsWith(".md")) && (zoom > 1.35 || hot.has(n.label))) { cx.fillStyle = hot.has(n.label) ? "#43c3cb" : "#a9c9b9"; cx.globalAlpha = .8; cx.fillText(n.short || n.label.split("/").pop(), n.sx, n.sy - 12); }
    });
    cx.globalAlpha = 1;
    hover = best && !best.organ ? best : null;
    hoverOrg = best && best.organ ? best.organ : null;
    cv.style.cursor = drag ? "grabbing" : best ? "pointer" : "grab";
    if (best && !drag) {
      let html;
      if (best.organ) { const o = O[best.organ]; html = `<div class="f" style="color:${SCOL[o.state]}">${esc(o.role)} · ${o.label || SLAB[o.state]}</div><b>${esc(o.name)}</b>${(o.details || []).map(([a, b]) => `<div><span class="k">${esc(a)}</span> ${esc(b)}</div>`).join("")}`; }
      else if (best.k === "core") html = `<div class="f" style="color:#effff6">its soul · persona.md · click to open</div>${esc(best.text || "Who it is.")}`;
      else if (best.k === "region") html = `<div class="f" style="color:${col(best.region)}">region · click to show only this</div>${esc(best.label)}`;
      else if (best.k === "chat") html = `<div class="f" style="color:${col(best.region)}">our chats · ${esc(best.text)}${cb.chat ? " · click to open" : ""}</div>${esc(best.label)}`;
      else if (best.group) html = `<div class="f" style="color:${col(best.region)}">notebook · timeline.md · click to open</div>${esc(best.text)}`;
      else { const where = best.k === "mem" ? best.file : "file"; html = `<div class="f" style="color:${col(best.region)}">${esc((R[best.region] || {}).label || "")} · ${esc(where)} · click to open</div>${best.k === "file" ? esc(best.label) + (best.text ? `<br><span class="d">${esc(best.text)}</span>` : "") : esc(best.text || best.label)}`; }
      tip.innerHTML = html; tip.style.display = "block";
      tip.style.left = Math.min(W - 370, mx + 16) + "px"; tip.style.top = Math.min(H - 150, my + 16) + "px";
    } else tip.style.display = "none";
    requestAnimationFrame(frame);
  }
  function destroy() {
    alive = false; ro.disconnect(); cv.remove(); tip.remove();
    window.removeEventListener("mouseup", up); window.removeEventListener("mousemove", move);
  }
  requestAnimationFrame(frame);
  return {
    setHot(paths) { hot = new Set(paths || []); },
    zoomBy(f) { zoom = Math.max(.5, Math.min(3, zoom * f)); },

    resetView() { hidden.clear(); zoom = 1; rotX = -.18; rotY = 0; auto = true; },
    destroy,
  };
}
