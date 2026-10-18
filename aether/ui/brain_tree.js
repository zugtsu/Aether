"use strict";

function BrainTree(DATA, rnd, gauss) {
  const N = DATA.nodes, R = DATA.meta.regions;
  const FAN = ["reference", "user", "projects", "notebook", "self", "journal", "skills"];
  const REG = FAN.filter((r) => R[r]).concat(Object.keys(R).filter((r) => !FAN.includes(r) && r !== "chats"));

  const BASE = -.98, CROWN = .1, TRUNK = "#9fe8d8", VEIN = "#7ff0ff", SOUL = "#ffe7b0";
  const counts = {};
  N.forEach((n) => { if (n.k === "mem") counts[n.region] = (counts[n.region] || 0) + 1; });
  const maxC = Math.max(1, ...REG.map((r) => counts[r] || 0));
  const hubs = {}, strands = [], clouds = [], crown = [], mist = [], roots = [], veins = [];
  const col = (r) => (R[r] ? R[r].color : "#46f09a");
  const strandPt = (st, s) => {
    const r = .03 + .26 * Math.pow(1 - s, 5) + .13 * Math.pow(s, 5), a = st.ph + s * 2.4 * Math.PI;
    return { x: Math.cos(a) * r, y: BASE + (CROWN - BASE) * s, z: Math.sin(a) * r };
  };
  const bez = (a, b, c, u) => ({ x: (1 - u) * (1 - u) * a.x + 2 * (1 - u) * u * b.x + u * u * c.x,
    y: (1 - u) * (1 - u) * a.y + 2 * (1 - u) * u * b.y + u * u * c.y, z: (1 - u) * (1 - u) * a.z + 2 * (1 - u) * u * b.z + u * u * c.z });

  function place() {
    REG.forEach((r, k) => {
      const az = k / REG.length * Math.PI * 2 + .4, big = Math.sqrt((counts[r] || 0) / maxC);
      const h = hubs[r] = { x: Math.cos(az) * (.62 + .2 * big), y: .48 + .2 * Math.sin(k * 1.9) + .12 * big, z: Math.sin(az) * (.55 + .18 * big) };
      for (let j = 0, ns = 2 + Math.round(big * 3); j < ns; j++)
        strands.push({ r, ph: (strands.length * 2.39996) % 6.283, end: { x: h.x + gauss() * .05, y: h.y + gauss() * .04, z: h.z + gauss() * .05 } });
      for (let j = 0; j < 4 + Math.round(big * 4); j++)
        clouds.push({ r, x: h.x + gauss() * .14, y: h.y + gauss() * .1, z: h.z + gauss() * .14, s: .55 + rnd() * .7, ph: rnd() * 6.28 });
    });
    const files = {}, nowhere = { x: 0, y: .5, z: 0 };
    N.forEach((n) => {
      if (n.k === "core") Object.assign(n, { x: 0, y: CROWN + .06, z: 0 });
      else if (n.k === "region") Object.assign(n, n.region === "chats" ? { x: 0, y: BASE - .06, z: 0 } : { ...(hubs[n.region] || nowhere) });
      else if (n.k === "file") {
        const h = hubs[n.region] || nowhere;
        Object.assign(n, { x: h.x + gauss() * .13, y: h.y + gauss() * .1 + .04, z: h.z + gauss() * .13 });
        files[n.label] = n;
      }
    });
    N.forEach((n) => {
      if (n.k !== "mem") return;
      const f = files[n.at || n.file], c = f || hubs[n.region] || nowhere, sp = f ? .075 : .14;
      Object.assign(n, { x: c.x + gauss() * sp, y: c.y + gauss() * sp * .8, z: c.z + gauss() * sp, rot: rnd() * 3.14, ph: rnd() * 6.28 });
    });
    const ch = N.filter((n) => n.k === "chat");
    ch.forEach((n, i) => {
      const ar = i / Math.max(1, ch.length) * Math.PI * 2 + rnd() * .05, L = .45 + .75 * Math.min(1, Math.max(0, (n.size - .9) / 1.3)), w = rnd() * 6.28, pts = [];
      for (let j = 0; j <= 14; j++) {
        const u = j / 14, rr = .08 + L * u, wig = Math.sin(u * 8 + w) * .035 * u;
        pts.push({ x: Math.cos(ar) * rr - Math.sin(ar) * wig, y: BASE - .02 - .18 * u * u + .05 * Math.sin(u * Math.PI), z: (Math.sin(ar) * rr + Math.cos(ar) * wig) * .9 });
      }
      roots.push({ n, pts });
      Object.assign(n, pts[14]);
    });
    for (let i = 0; i < 1100; i++) {
      let x, y, z, d;
      do { x = rnd() * 2 - 1; y = rnd() * 2 - 1; z = rnd() * 2 - 1; d = x * x + y * y + z * z; } while (d > 1 || d < .42 || y < -.55);
      const k = rnd();
      crown.push({ x: x * 1.02, y: .6 + y * .42, z: z * .88, rot: rnd() * 3.14, ph: rnd() * 6.28, s: .7 + rnd() * .6,
        c: k < .35 ? "#7b5cd6" : k < .6 ? "#9a6ae0" : k < .78 ? "#5b4fc8" : k < .93 ? "#b48cf0" : "#6fd8ff" });
    }
    for (let i = 0; i < 30; i++) {
      const a = rnd() * 6.283, k = rnd();
      mist.push({ x: Math.cos(a) * (.2 + rnd() * 1.2), y: -.95 + rnd() * 2, z: Math.sin(a) * (.2 + rnd() * 1.05), s: 90 + rnd() * 150,
        ph: rnd() * 6.28, c: k < .45 ? "#2f8f8a" : k < .8 ? "#3a5fb0" : "#6a4fa8" });
    }

    const vein = (p, d, len, depth) => {
      const pts = [p];
      for (let j = 0; j < 7; j++) {
        d = { x: d.x + gauss() * .25, y: d.y + gauss() * .2, z: d.z + gauss() * .25 };
        const m = Math.hypot(d.x, d.y, d.z) || 1, q = pts[pts.length - 1];
        pts.push({ x: q.x + d.x / m * len / 7, y: q.y + d.y / m * len / 7, z: q.z + d.z / m * len / 7 });
      }
      veins.push({ pts, w: depth ? .8 : 1.4, ph: rnd() * 6.28 });
      if (depth < 2) for (let k = 0; k < 2; k++) if (rnd() < .75) vein(pts[3 + k * 2], { x: d.x + gauss() * .7, y: d.y + rnd() * .4, z: d.z + gauss() * .7 }, len * .55, depth + 1);
    };
    for (let i = 0; i < 9; i++) { const a = i / 9 * 6.283; vein({ x: 0, y: CROWN + .08, z: 0 }, { x: Math.cos(a) * .8, y: .9, z: Math.sin(a) * .7 }, .85, 0); }
  }

  function neon(g, pts, c, w, a) {
    const q = pts.map(g.P);
    [[w * 4, a * .14], [w, a]].forEach(([lw, al]) => {
      g.cx.strokeStyle = c; g.cx.globalAlpha = al; g.cx.lineWidth = lw; g.cx.beginPath();
      q.forEach((p, i) => (i ? g.cx.lineTo(p.x, p.y) : g.cx.moveTo(p.x, p.y))); g.cx.stroke();
    });
    g.cx.globalAlpha = 1;
  }
  function glow(g, q, c, s, a) { g.cx.globalAlpha = a; g.cx.drawImage(g.sprite(c), q.x - s, q.y - s, 2 * s, 2 * s); g.cx.globalAlpha = 1; }
  function leafShape(g, x, y, c, s, rot, a) {
    const cx = g.cx; cx.save(); cx.translate(x, y); cx.rotate(rot); cx.globalAlpha = a; cx.fillStyle = c;
    cx.beginPath(); cx.ellipse(0, 0, s, s * .42, 0, 0, 7); cx.fill(); cx.restore(); cx.globalAlpha = 1;
  }

  function draw(g) {
    const t = g.t, cx = g.cx, hid = (r) => g.hidden && g.hidden.has(r), k = g.mini ? .55 : 1;
    cx.globalCompositeOperation = "lighter";
    mist.forEach((m) => { const q = g.P({ x: m.x + Math.sin(t * .1 + m.ph) * .05, y: m.y, z: m.z }); glow(g, q, m.c, m.s * q.f * k, .09 + .04 * Math.sin(t * .3 + m.ph)); });
    if (!hid("chats")) roots.forEach(({ n, pts }) => neon(g, pts, "#4fd6c8", .7 * k, n.old ? .22 : .45));
    strands.forEach((st) => {
      if (hid(st.r)) return;
      const trunk = Array.from({ length: 30 }, (_, j) => strandPt(st, j / 29)), top = trunk[29];
      const ctl = { x: top.x * .5 + st.end.x * .3, y: st.end.y + .08, z: top.z * .5 + st.end.z * .3 };
      neon(g, trunk, TRUNK, 1.2 * k, .75);
      neon(g, Array.from({ length: 18 }, (_, j) => bez(top, ctl, st.end, j / 17)), col(st.r), 1 * k, .7);
    });
    for (let j = 0; j < 10; j++) glow(g, g.P({ x: 0, y: BASE + (CROWN - BASE) * j / 9, z: 0 }), TRUNK, 26 * k * (1 - j / 12), .08);
    veins.forEach((v) => neon(g, v.pts, VEIN, 1.3 * v.w * k, .6 + .3 * Math.sin(t * 1.5 + v.ph)));
    cx.globalCompositeOperation = "source-over";
    crown.forEach((l) => {
      const q = g.P({ x: l.x, y: l.y + Math.sin(t * .4 + l.ph) * .006, z: l.z });
      leafShape(g, q.x, q.y, l.c, (4.2 + 4 * q.f) * l.s * k, l.rot + Math.sin(t * 1.1 + l.ph) * .3, .5 + .1 * Math.sin(t * .9 + l.ph));
    });
    cx.globalCompositeOperation = "lighter";
    clouds.forEach((c) => { if (hid(c.r)) return; const q = g.P({ x: c.x, y: c.y + Math.sin(t * .25 + c.ph) * .01, z: c.z }); glow(g, q, "#8a6ae6", 120 * c.s * q.f * k, .1); glow(g, q, col(c.r), 70 * c.s * q.f * k, .05); });
    if (!hid("chats")) roots.forEach(({ n, pts }) => {
      const q = g.P(pts[14]), m = (5 + 5 * q.f) * k * (n.old ? .8 : 1);
      glow(g, { x: q.x, y: q.y - m }, "#7affd8", m * 3.2, .25 + .1 * Math.sin(t * 1.2 + q.x));
      cx.globalCompositeOperation = "source-over";
      cx.fillStyle = "#d8f0e8"; cx.globalAlpha = .8; cx.fillRect(q.x - m * .15, q.y - m, m * .3, m);
      cx.fillStyle = n.old ? "#6a4fb0" : "#9a6ae0"; cx.beginPath(); cx.ellipse(q.x, q.y - m, m * .8, m * .45, 0, Math.PI, 0); cx.fill();
      cx.globalAlpha = 1; cx.globalCompositeOperation = "lighter";
    });
    const s = g.P({ x: 0, y: CROWN + .06, z: 0 });
    glow(g, s, SOUL, 60 * k * (1 + .1 * Math.sin(t * 1.6)), .35);
  }

  function leaf(g, n, c) {
    const s = (2 + 2.4 * n.sf) * (g.mini ? .7 : 1), mode = g.cx.globalCompositeOperation;
    glow(g, { x: n.sx, y: n.sy }, c, s * 1.5, .12);
    g.cx.globalCompositeOperation = "source-over";
    leafShape(g, n.sx, n.sy, c, s, (n.rot || 0) + Math.sin(g.t * 1.3 + (n.ph || 0)) * .3, .7);
    g.cx.globalCompositeOperation = mode;
  }

  function organAt(i, n, t) {
    const a = t * .12 + i / n * Math.PI * 2;

    return { x: Math.cos(a) * 1.32, y: .62 + .26 * Math.sin(a + .9) + .05 * Math.sin(t * .8 + i * 1.7), z: Math.sin(a) * 1.12 };
  }

  return { place, draw, leaf, organAt, dust: "#bfe9ff" };
}
