"use strict";
const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage, screen, session, dialog, shell, clipboard } = require("electron");
const { contextTemplate } = require("./menu");
const { spawn, execFile } = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");

const CFG = JSON.parse(fs.readFileSync(path.join(__dirname, "launch.json"), "utf-8"));
const BASE = `http://127.0.0.1:${CFG.port || 8850}/`;
const ICON = CFG.icon && fs.existsSync(CFG.icon) ? CFG.icon : undefined;

let server = null;
let win = null, pet = null, tray = null, quitting = false;
let stopping = false, engineStopped = false;
let reopen = false;

if (process.env.AETHER_HOME) app.setPath("userData", path.join(process.env.AETHER_HOME, "desktop"));
if (!app.requestSingleInstanceLock()) { app.quit(); }

app.on("second-instance", () => { if (quitting || stopping) reopen = true; else showMain(); });
app.on("will-quit", () => { if (reopen) app.relaunch(); });
app.setAppUserModelId("Aether");

function stampShortcuts() {
  const places = [path.join(app.getPath("desktop"), "Aether.lnk"),
    path.join(app.getPath("appData"), "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar", "Aether.lnk")];
  for (const p of places) {
    try {
      const l = shell.readShortcutLink(p);
      if (path.resolve(l.target).toLowerCase() !== process.execPath.toLowerCase() || l.appUserModelId === "Aether") continue;
      shell.writeShortcutLink(p, "update", { appUserModelId: "Aether", icon: ICON || l.icon, iconIndex: 0 });
    } catch (e) {  }
  }
}

function ping() {
  return new Promise((ok) => {
    const req = http.get(BASE + "ui/app.js", { timeout: 1500 }, (res) => {
      let body = "";
      res.on("data", (c) => { if (body.length < 4096) body += c; });
      res.on("end", () => ok(res.statusCode === 200 && body.includes("aether-token")));
    });
    req.on("error", () => ok(false));
    req.on("timeout", () => { req.destroy(); ok(false); });
  });
}
async function startEngine() {
  if (await ping()) return true;
  server = spawn(CFG.pythonw, ["-m", "aether", "app", "--no-window"], { cwd: CFG.project, windowsHide: true, stdio: "ignore" });
  server.on("exit", () => { server = null; });
  for (let i = 0; i < 120; i++) {
    if (await ping()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function stopEngine() {
  const s = server;
  if (!s || !s.pid) return;
  const gone = new Promise((ok) => { if (s.exitCode !== null || s.signalCode !== null) ok(); else s.once("exit", ok); });
  if (await ping()) {
    post("/api/quit");
    if (await Promise.race([gone.then(() => true), sleep(10000).then(() => false)])) return;
  }
  await new Promise((ok) => execFile("taskkill", ["/PID", String(s.pid), "/T", "/F"], { windowsHide: true }, () => ok()));
}
async function token() {
  return new Promise((ok) => {
    http.get(BASE, { timeout: 3000 }, (res) => { let b = ""; res.on("data", (c) => (b += c)); res.on("end", () => ok((b.match(/aether-token" content="([^"]+)"/) || [])[1])); })
      .on("error", () => ok(null))
      .on("timeout", function () { this.destroy(); ok(null); });
  });
}
async function post(pathname, body) {
  const t = await token();
  if (!t) return;
  const data = JSON.stringify(body || {});
  const req = http.request(BASE + pathname.replace(/^\//, ""), { method: "POST", headers: { "Content-Type": "application/json", "X-Aether-Token": t, "Content-Length": Buffer.byteLength(data) } });
  req.on("error", () => {});
  req.end(data);
}

const safe = { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true };

function lockDown(w) {

  w.webContents.on("will-navigate", (e, url) => { if (!url.startsWith(BASE)) e.preventDefault(); });

  w.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https:\/\/strudel\.cc\/(?:[?#]|$)/.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
}

function rightClickMenu(w) {
  w.webContents.on("context-menu", (_e, p) => {
    const wc = w.webContents;
    const run = { replace: (s) => wc.replaceMisspelling(s), learn: (s) => wc.session.addWordToSpellCheckerDictionary(s),
                  copyLink: (u) => clipboard.writeText(u), copyImage: ([x, y]) => wc.copyImageAt(x, y), reload: () => wc.reload() };
    const template = contextTemplate(p).map(({ action, arg, ...item }) => (action ? { ...item, click: () => run[action](arg) } : item));
    Menu.buildFromTemplate(template).popup({ window: w });
  });
}

function createMain() {
  win = new BrowserWindow({ width: 1600, height: 960, minWidth: 1000, minHeight: 640, backgroundColor: "#07080f", title: "Aether",
    icon: ICON, autoHideMenuBar: true, show: false, webPreferences: safe });
  lockDown(win);
  rightClickMenu(win);
  win.loadURL(BASE);
  win.once("ready-to-show", () => win.show());
  win.on("focus", clearAttention);

  win.on("close", () => { quitting = true; app.quit(); });
  win.on("closed", () => { win = null; });
}

function clearAttention() {
  if (!win || win.isDestroyed()) return;
  win.flashFrame(false);
  win.setOverlayIcon(null, "");
}
ipcMain.on("attention", (e, n, png) => {
  if (!win || BrowserWindow.fromWebContents(e.sender) !== win || !Number.isInteger(n) || n < 0) return;
  if (n === 0 || win.isFocused()) return clearAttention();
  win.flashFrame(true);
  const ok = typeof png === "string" && png.startsWith("data:image/png;base64,") && png.length < 50000;
  const img = ok ? nativeImage.createFromDataURL(png) : null;
  if (img && !img.isEmpty()) win.setOverlayIcon(img, `${n} new in Aether`);
});
function showMain() {
  if (!win || win.isDestroyed()) return;
  if (win.isMinimized()) win.restore();
  win.show(); win.focus();
}

const PET_FILE = path.join(app.getPath("userData"), "pet.json");
function defaultPetBounds() {
  const area = screen.getPrimaryDisplay().workArea;
  const W = 360, H = 610;
  return { width: W, height: H, x: area.x + area.width - W - 20, y: area.y + area.height - H };
}
function loadPetBounds() {
  try {
    const b = JSON.parse(fs.readFileSync(PET_FILE, "utf-8"));
    const d = screen.getDisplayMatching(b).workArea;
    if (b.width >= 160 && b.height >= 260 && b.x < d.x + d.width - 60 && b.x + b.width > d.x + 60 &&
        b.y < d.y + d.height - 60 && b.y + b.height > d.y + 60) return b;
  } catch (e) {  }
  return defaultPetBounds();
}
let petSaveTimer = null;
function savePetSoon() {
  clearTimeout(petSaveTimer);
  petSaveTimer = setTimeout(() => { if (pet) try { fs.writeFileSync(PET_FILE, JSON.stringify(pet.getBounds())); } catch (e) {  } }, 400);
}

function scalePet(factor) {
  if (!pet) return;
  const b = pet.getBounds();
  const area = screen.getDisplayMatching(b).workArea;
  const maxW = Math.min(1400, Math.floor(area.height * b.width / b.height));
  const w = Math.round(Math.min(maxW, Math.max(180, b.width * factor)));
  const h = Math.round(b.height * w / b.width);
  pet.setBounds({ x: Math.round(b.x + (b.width - w) / 2), y: b.y + b.height - h, width: w, height: h });
  savePetSoon();
}
function resetPet() { if (pet) { pet.setBounds(defaultPetBounds()); savePetSoon(); } }

function togglePet() {
  if (pet) { pet.close(); return; }
  pet = new BrowserWindow({ ...loadPetBounds(), transparent: true, frame: false, resizable: false, skipTaskbar: true,
    hasShadow: false, alwaysOnTop: true, title: "Aether pet", icon: ICON, webPreferences: safe });
  pet.setAlwaysOnTop(true, "screen-saver");
  lockDown(pet);
  pet.loadURL(BASE + "pet");
  pet.on("moved", savePetSoon);
  pet.on("closed", () => { pet = null; post("/api/pet", { open: false }); buildTray(); });
  buildTray();
}
const fromPet = (e) => pet && BrowserWindow.fromWebContents(e.sender) === pet;

ipcMain.on("pet-move", (e, x, y) => {
  if (!fromPet(e) || !Number.isFinite(x) || !Number.isFinite(y)) return;
  const b = pet.getBounds();
  pet.setBounds({ x: Math.round(x), y: Math.round(y), width: b.width, height: b.height });
  savePetSoon();
});
ipcMain.on("pet-scale", (e, factor) => { if (fromPet(e) && Number.isFinite(factor)) scalePet(Math.min(1.5, Math.max(0.66, factor))); });

function buildTray() {
  if (stopping) return;
  if (!tray) {
    tray = new Tray(ICON ? nativeImage.createFromPath(ICON) : nativeImage.createEmpty());
    tray.setToolTip("Aether");
    tray.on("click", showMain);
  }
  const login = app.getLoginItemSettings({ path: process.execPath, args: [__dirname] });
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open Aether", click: showMain },
    { label: "Pet mode", type: "checkbox", checked: !!pet, click: togglePet },
    { label: "Stop (voice, reply, skills)", click: () => post("/api/stop") },
    { type: "separator" },
    { label: "Start with Windows", type: "checkbox", checked: login.openAtLogin,
      click: (item) => app.setLoginItemSettings({ openAtLogin: item.checked, path: process.execPath, args: [__dirname] }) },
    { type: "separator" },
    { label: "Quit Aether", click: () => { quitting = true; app.quit(); } },
  ]));
}

ipcMain.handle("toggle-pet", () => togglePet());
ipcMain.handle("pet-menu", (e) => {
  Menu.buildFromTemplate([
    { label: "Open Aether", click: showMain },
    { label: "Stop", click: () => post("/api/stop") },
    { type: "separator" },
    { label: "Bigger", click: () => scalePet(1.15) },
    { label: "Smaller", click: () => scalePet(1 / 1.15) },
    { label: "Reset size and place", click: resetPet },
    { type: "separator" },
    { label: "Close pet mode", click: () => pet && pet.close() },
  ]).popup({ window: BrowserWindow.fromWebContents(e.sender) });
});

app.whenReady().then(async () => {

  session.defaultSession.setPermissionRequestHandler((wc, perm, cb) => cb(["media", "notifications", "clipboard-sanitized-write"].includes(perm)));
  buildTray();
  stampShortcuts();
  if (!(await startEngine())) {
    dialog.showErrorBox("Aether", "Aether's engine didn't start.\n\nIn the project folder, try:  python -m aether app\nto see the error.");
    quitting = true; app.quit(); return;
  }
  createMain();
  if (process.env.AETHER_SNAPSHOT_DIR) snapshots(process.env.AETHER_SNAPSHOT_DIR);
});

async function snapshots(dir) {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  await wait(9000);
  fs.writeFileSync(path.join(dir, "main.png"), (await win.webContents.capturePage()).toPNG());
  togglePet();
  await wait(9000);
  fs.writeFileSync(path.join(dir, "pet.png"), (await pet.webContents.capturePage()).toPNG());
  quitting = true; app.quit();
}

app.on("before-quit", (e) => {
  quitting = true;
  if (engineStopped || !server) return;
  e.preventDefault();
  if (stopping) return;
  stopping = true;
  for (const w of BrowserWindow.getAllWindows()) w.hide();
  if (tray) { tray.destroy(); tray = null; }
  stopEngine().finally(() => { engineStopped = true; app.quit(); });
});
app.on("window-all-closed", (e) => { if (!quitting) e.preventDefault(); });
