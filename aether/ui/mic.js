"use strict";

const MicPick = {

  async list() {
    const all = await navigator.mediaDevices.enumerateDevices();
    return all.filter((d) => d.kind === "audioinput" && !["default", "communications"].includes(d.deviceId));
  },

  async constraints(name, base) {
    if (!name) return base;
    try {
      const d = (await this.list()).find((m) => m.label === name);
      if (d) return { ...base, deviceId: { exact: d.deviceId } };
    } catch (e) {  }
    this.missing = name;
    return base;
  },
  async open(name, base) {
    this.missing = "";
    return navigator.mediaDevices.getUserMedia({ audio: await this.constraints(name, base) });
  },
  missing: "",
};
