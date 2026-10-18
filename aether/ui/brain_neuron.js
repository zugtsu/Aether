"use strict";

function BrainNeuron(DATA, rnd, gauss) {
  const N = DATA.nodes, R = DATA.meta.regions;
  const col = (r) => (R[r] ? R[r].color : "#8fb4ff");
  const SOUL = "#eaf2ff", AXON = "#7aa8ff";
  const somas = [], axons = [], dendrites = [], spine = [];
  const at = (p) => ({ x: p.x, y: p.y, z: p.z });

  function grow(from, dir, len, depth, r) {
    const pts = [at(from)];
    let p = at(from), d = { ...dir };
    for (let j = 0; j < 5; j++) {
      d = { x: d.x + gauss() * .35, y: d.y + gauss() * .35, z: d.z + gauss() * .35 };
      const m = Math.hypot(d.x, d.y, d.z) || 1;
      p = { x: p.x + d.x / m * len / 5, y: p.y + d.y / m * len / 5, z: p.z + d.z / m * len / 5 };
      pts.push(p);
    }
    dendrites.push({ pts, r, w: depth ? .6 : 1 });
    if (depth < 2) for (let k = 0; k < 2; k++) if (rnd() < .7) grow(pts[2 + k * 2], { x: d.x + gauss() * .8, y: d.y + gauss() * .8, z: d.z + gauss() * .8 }, len * .55, depth + 1, r);
  }

  function axon(a, b, r, w) {
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: (a.z + b.z) / 2 };
    const out = Math.hypot(mid.x, mid.y, mid.z) || 1, bow = .18 + rnd() * .14;
    axons.push({ a, b, c: { x: mid.x + mid.x / out * bow + gauss() * .05, y: mid.y + mid.y / out * bow + .08, z: mid.z + mid.z / out * bow + gauss() * .05 },
      r, w, ph: rnd(), speed: .12 + rnd() * .1 });
  }

  function place() {
    const files = {}, hubs = {}, core = N.find((n) => n.k === "core");
    N.forEach((n) => {
      if (n.k === "core") Object.assign(n, { x: 0, y: .05, z: 0 });
      else if (n.k === "region" && n.region !== "chats") {
        const c = R[n.region] ? R[n.region].center : [gauss() * .5, gauss() * .4, gauss() * .5];
        Object.assign(n, { x: c[0] * 1.05, y: c[1] * .95 + .05, z: c[2] * 1.05 });
        hubs[n.region] = n;
      }
    });
    N.forEach((n) => {
      if (n.k !== "file") return;
      const h = hubs[n.region] || { x: 0, y: 0, z: 0 }, out = Math.hypot(h.x, h.y, h.z) || 1;
      Object.assign(n, { x: h.x + h.x / out * .22 + gauss() * .17, y: h.y + gauss() * .15, z: h.z + h.z / out * .22 + gauss() * .17 });
      files[n.label] = n;
    });

    N.filter((n) => n.group).forEach((n, i) => { const h = hubs[n.region] || { x: 0, y: 0, z: 0 }; Object.assign(n, { x: h.x + (i - 2) * .09, y: h.y - .16, z: h.z }); });
    N.forEach((n) => {
      if (n.k !== "mem") return;
      const f = files[n.at || n.file] || hubs[n.region] || { x: 0, y: 0, z: 0 }, r = .05 + rnd() * .1;
      const th = rnd() * 6.283, ph = Math.acos(2 * rnd() - 1);
      Object.assign(n, { x: f.x + r * Math.sin(ph) * Math.cos(th), y: f.y + r * Math.cos(ph), z: f.z + r * Math.sin(ph) * Math.sin(th), ph: rnd() * 6.28 });
    });
    const ch = N.filter((n) => n.k === "chat"), base = -.45;
    ch.forEach((n, i) => {
      const u = ch.length > 1 ? i / (ch.length - 1) : 0, a = i * 2.39996;
      Object.assign(n, { x: Math.cos(a) * .07, y: base - 1.0 * (1 - u), z: Math.sin(a) * .07 });
      spine.push(n);
    });
    const cr = N.find((n) => n.k === "region" && n.region === "chats");
    if (cr) Object.assign(cr, { x: 0, y: base + .05, z: 0 });

    if (core) for (let k = 0; k < 7; k++) grow(core, { x: gauss(), y: gauss(), z: gauss() }, .32, 1, "core");
    Object.entries(hubs).forEach(([r, h]) => {
      somas.push({ r, n: h });
      const out = Math.hypot(h.x, h.y, h.z) || 1;
      for (let k = 0; k < 7; k++) grow(h, { x: h.x / out + gauss() * .8, y: h.y / out + gauss() * .8, z: h.z / out + gauss() * .8 }, .46, 0, r);
      if (core) axon(core, h, r, 1.5);
    });
    Object.values(files).forEach((f) => {
      const h = hubs[f.region];
      if (h) axon(h, f, f.region, .7);
      for (let k = 0; k < 2; k++) grow(f, { x: gauss(), y: gauss(), z: gauss() }, .09, 2, f.region);
    });
    if (core && cr) axon(core, cr, "chats", 1.2);
  }

  const bez = (a, c, b, u) => ({ x: (1 - u) * (1 - u) * a.x + 2 * (1 - u) * u * c.x + u * u * b.x,
    y: (1 - u) * (1 - u) * a.y + 2 * (1 - u) * u * c.y + u * u * b.y, z: (1 - u) * (1 - u) * a.z + 2 * (1 - u) * u * c.z + u * u * b.z });
  function line(g, pts, c, w, a) {
    const q = pts.map(g.P);
    [[w * 3.5, a * .16], [w, a]].forEach(([lw, al]) => {
      g.cx.strokeStyle = c; g.cx.globalAlpha = al; g.cx.lineWidth = lw; g.cx.beginPath();
      q.forEach((p, i) => (i ? g.cx.lineTo(p.x, p.y) : g.cx.moveTo(p.x, p.y))); g.cx.stroke();
    });
    g.cx.globalAlpha = 1;
  }
  function glow(g, q, c, s, a) { g.cx.globalAlpha = a; g.cx.drawImage(g.sprite(c), q.x - s, q.y - s, 2 * s, 2 * s); g.cx.globalAlpha = 1; }

  function draw(g) {
    const t = g.t, k = g.mini ? .6 : 1, hid = (r) => r !== "core" && g.hidden && g.hidden.has(r);
    g.cx.globalCompositeOperation = "lighter";
    dendrites.forEach((d) => { if (!hid(d.r)) line(g, d.pts, d.r === "core" ? SOUL : col(d.r), 1.3 * d.w * k, .62); });
    axons.forEach((x) => {
      if (hid(x.r)) return;
      const pts = Array.from({ length: 22 }, (_, j) => bez(x.a, x.c, x.b, j / 21));
      line(g, pts, x.r === "chats" ? AXON : col(x.r), 1.3 * x.w * k, .5);
      for (let j = 0; j < 2; j++) {
        const u = (t * x.speed + x.ph + j * .5) % 1, q = g.P(bez(x.a, x.c, x.b, u));
        glow(g, q, x.r === "chats" ? AXON : col(x.r), (5 + 4 * q.f) * k * (x.w > 1 ? 1.3 : .9), .95);
      }
    });
    if (spine.length > 1 && !hid("chats")) {
      line(g, spine.slice().sort((a, b) => a.y - b.y).map(at), AXON, 1.6 * k, .28);
      const u = (t * .15) % 1, n = spine[Math.floor(u * spine.length)];
      if (n) glow(g, g.P(n), AXON, 9 * k, .8);
    }
    somas.forEach((s) => {
      if (hid(s.r)) return;
      const q = g.P(s.n);
      glow(g, q, col(s.r), (34 + 16 * q.f) * k * (1 + .12 * Math.sin(t * 1.4 + s.n.x * 5)), .28);
    });
    glow(g, g.P({ x: 0, y: .05, z: 0 }), SOUL, 70 * k * (1 + .1 * Math.sin(t * 1.7)), .3);
  }

  function leaf(g, n, c) {

    const s = (1.1 + 1.4 * n.sf) * (g.mini ? .7 : 1), fl = .35 + .65 * Math.max(0, Math.sin(g.t * 2.3 + (n.ph || 0)));
    glow(g, { x: n.sx, y: n.sy }, c, s * 2.2 * fl, .5);
  }

  const keepLink = () => false;
  return { place, draw, leaf, keepLink };
}
