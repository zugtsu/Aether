import json
import os
import shutil
import subprocess
import unittest

MENU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop", "menu.js")


def menu(**params):
    js = f"console.log(JSON.stringify(require({json.dumps(MENU)}).contextTemplate({json.dumps(params)})))"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8", timeout=30)
    if out.returncode:
        raise AssertionError(out.stderr)
    items = json.loads(out.stdout)
    return ["---" if i.get("type") == "separator" else i["label"] for i in items], items


@unittest.skipUnless(shutil.which("node"), "node isn't installed")
class RightClickTests(unittest.TestCase):
    def test_the_message_box(self):
        labels, items = menu(isEditable=True, selectionText="", editFlags={"canUndo": True, "canPaste": True})
        self.assertEqual(labels, ["Undo", "Redo", "---", "Cut", "Copy", "Paste", "Select all", "---", "Reload the page"])
        on = {i["label"]: i.get("enabled", True) for i in items if "label" in i}
        self.assertTrue(on["Undo"] and on["Paste"])
        self.assertFalse(on["Redo"] or on["Cut"] or on["Copy"])
        self.assertEqual([i.get("role") for i in items if i.get("role")], ["undo", "redo", "cut", "copy", "paste", "selectAll"])

    def test_a_misspelled_word_gets_its_fixes_first(self):
        labels, items = menu(isEditable=True, misspelledWord="tommorow", dictionarySuggestions=["tomorrow", "Tomorrow"],
                             editFlags={"canCut": True, "canCopy": True})
        self.assertEqual(labels[:4], ["tomorrow", "Tomorrow", 'Add "tommorow" to the dictionary', "---"])
        self.assertEqual((items[0]["action"], items[0]["arg"]), ("replace", "tomorrow"))
        self.assertEqual(items[2]["action"], "learn")
        none, _ = menu(isEditable=True, misspelledWord="lucyy", dictionarySuggestions=[])
        self.assertEqual(none[0], "No spelling suggestions")

    def test_selected_words_in_a_chat_can_be_copied(self):
        labels, items = menu(isEditable=False, selectionText="the lantern room")
        self.assertEqual(labels, ["Copy", "Select all", "---", "Reload the page"])
        self.assertTrue(items[0]["enabled"])
        _, nothing = menu(isEditable=False, selectionText="  ")
        self.assertFalse(nothing[0]["enabled"])

    def test_a_link_and_a_picture(self):
        labels, items = menu(isEditable=False, selectionText="", linkURL="https://example.com/a", mediaType="image", x=10, y=20)
        self.assertEqual(labels, ["Copy", "Select all", "---", "Copy link", "---", "Copy picture", "---", "Reload the page"])
        self.assertEqual(items[3]["arg"], "https://example.com/a")
        self.assertEqual(items[5]["arg"], [10, 20])
        odd, _ = menu(isEditable=False, linkURL="javascript:alert(1)")
        self.assertNotIn("Copy link", odd)


if __name__ == "__main__":
    unittest.main()
