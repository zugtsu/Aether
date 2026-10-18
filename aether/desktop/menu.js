"use strict";

function contextTemplate(p) {
  const flags = p.editFlags || {};
  const items = [];
  const sep = () => { if (items.length && items[items.length - 1].type !== "separator") items.push({ type: "separator" }); };
  if (p.isEditable && p.misspelledWord) {
    const fixes = (p.dictionarySuggestions || []).slice(0, 5);
    for (const s of fixes) items.push({ label: s, action: "replace", arg: s });
    if (!fixes.length) items.push({ label: "No spelling suggestions", enabled: false });
    items.push({ label: `Add "${p.misspelledWord}" to the dictionary`, action: "learn", arg: p.misspelledWord });
    sep();
  }
  if (p.isEditable) {
    items.push({ role: "undo", label: "Undo", enabled: !!flags.canUndo }, { role: "redo", label: "Redo", enabled: !!flags.canRedo });
    sep();
    items.push({ role: "cut", label: "Cut", enabled: !!flags.canCut }, { role: "copy", label: "Copy", enabled: !!flags.canCopy },
               { role: "paste", label: "Paste", enabled: !!flags.canPaste }, { role: "selectAll", label: "Select all" });
  } else {
    items.push({ role: "copy", label: "Copy", enabled: !!(p.selectionText || "").trim() }, { role: "selectAll", label: "Select all" });
  }
  if (p.linkURL && /^https?:\/\//i.test(p.linkURL)) {
    sep();
    items.push({ label: "Copy link", action: "copyLink", arg: p.linkURL });
  }
  if (p.mediaType === "image") {
    sep();
    items.push({ label: "Copy picture", action: "copyImage", arg: [p.x, p.y] });
  }
  sep();
  items.push({ label: "Reload the page", action: "reload" });
  return items;
}

module.exports = { contextTemplate };
