"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("aetherDesktop", {
  togglePet: () => ipcRenderer.invoke("toggle-pet"),
  petMenu: () => ipcRenderer.invoke("pet-menu"),

  petMove: (x, y) => ipcRenderer.send("pet-move", x, y),
  petScale: (factor) => ipcRenderer.send("pet-scale", factor),

  attention: (n, png) => ipcRenderer.send("attention", n, png),
});
