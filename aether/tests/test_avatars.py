import json
import os
import tempfile
import unittest
import zipfile

from aether import avatars


def make_model(folder, name="Test Girl", exprs=("neutral", "Happy Smile", "angry", "love_blush", "sad"), lipsync=True,
               skip=()):
    os.makedirs(os.path.join(folder, "exp"), exist_ok=True)
    refs = {"Moc": f"{name}.moc3", "Textures": ["tex/texture_00.png"], "Physics": f"{name}.physics3.json",
            "Expressions": [{"Name": e, "File": f"exp/{e}.exp3.json"} for e in exprs]}
    groups = [{"Target": "Parameter", "Name": "EyeBlink", "Ids": ["ParamEyeLOpen"]}]
    if lipsync:
        groups.append({"Target": "Parameter", "Name": "LipSync", "Ids": ["ParamMouthOpen"]})
    with open(os.path.join(folder, f"{name}.model3.json"), "w", encoding="utf-8") as f:
        json.dump({"Version": 3, "FileReferences": refs, "Groups": groups}, f)
    files = [refs["Moc"], refs["Physics"], *refs["Textures"], *[e["File"] for e in refs["Expressions"]]]
    for rel in files:
        if rel in skip:
            continue
        p = os.path.join(folder, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").close()
    return os.path.join(folder, f"{name}.model3.json")


class AvatarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "avatars")

    def test_moods_map_to_expressions_by_name(self):
        info = avatars.inspect(make_model(os.path.join(self.tmp, "m")))
        self.assertEqual(info["moods"]["happy"], "Happy Smile")
        self.assertEqual(info["moods"]["annoyed"], "angry")
        self.assertEqual(info["moods"]["affectionate"], "love_blush")
        self.assertEqual(info["moods"]["worried"], "sad")
        self.assertIsNone(info["moods"]["dreamy"])
        self.assertIsNone(info["moods"]["steady"])
        self.assertEqual((info["mouth"], info["blink"]), ("ParamMouthOpen", True))
        self.assertEqual(info["warnings"], [])

    def test_a_model_with_no_faces_or_mouth_says_so(self):
        info = avatars.inspect(make_model(os.path.join(self.tmp, "m"), exprs=(), lipsync=False))
        self.assertEqual(info["mouth"], "ParamMouthOpenY")
        self.assertEqual(set(info["moods"].values()), {None})
        self.assertTrue(any("no expressions" in w for w in info["warnings"]))
        self.assertTrue(any("LipSync" in w for w in info["warnings"]))

    def test_add_a_folder_list_it_and_use_it(self):
        src = os.path.join(self.tmp, "Test Girl")
        make_model(src)
        info = avatars.add(src, self.root)
        self.assertEqual((info["name"], info["file"]), ("Test Girl", "Test Girl.model3.json"))
        self.assertEqual([a["name"] for a in avatars.listing(self.root)], ["Test Girl"])
        self.assertTrue(avatars.model_of(self.root, "Test Girl").endswith("Test Girl.model3.json"))
        with self.assertRaises(avatars.AvatarError):
            avatars.add(src, self.root)

    def test_a_model_missing_a_file_is_refused_and_put_aside(self):
        src = os.path.join(self.tmp, "broken")
        make_model(src, skip=("tex/texture_00.png",))
        with self.assertRaises(avatars.AvatarError) as e:
            avatars.add(src, self.root)
        self.assertIn("tex/texture_00.png", str(e.exception))
        self.assertEqual(avatars.listing(self.root), [])
        self.assertTrue(os.path.isdir(os.path.join(self.root, ".refused", "broken")))

    def test_a_zip_is_unpacked_and_one_that_escapes_is_refused(self):
        src = os.path.join(self.tmp, "zsrc")
        make_model(src)
        good = os.path.join(self.tmp, "Zip Girl.zip")
        with zipfile.ZipFile(good, "w") as z:
            for r, _, fs in os.walk(src):
                for f in fs:
                    p = os.path.join(r, f)
                    z.write(p, os.path.join("wrapped", os.path.relpath(p, src)))
        self.assertEqual(avatars.add(good, self.root)["name"], "Zip Girl")
        bad = os.path.join(self.tmp, "evil.zip")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("../../escaped.txt", "x")
        with self.assertRaises(avatars.AvatarError) as e:
            avatars.add(bad, self.root)
        self.assertIn("outside", str(e.exception))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escaped.txt")))

    def test_names_cant_reach_outside_the_avatars_folder(self):
        os.makedirs(self.root)
        for name in ("..", "../x", "a\\..\\..\\b", "", "x" * 80):
            self.assertIsNone(avatars.model_of(self.root, name), name)
        src = os.path.join(self.tmp, "ok")
        make_model(src)
        with self.assertRaises(avatars.AvatarError):
            avatars.add(src, self.root, name="../sneaky")
        with self.assertRaises(avatars.AvatarError):
            avatars.add(src, self.root, name="Orb")

    def test_a_mood_can_be_set_by_hand(self):
        model = make_model(os.path.join(self.tmp, "m"))
        avatars.save_mood(model, "happy", "love_blush")
        avatars.save_mood(model, "annoyed", None)
        moods = avatars.inspect(model)["moods"]
        self.assertEqual((moods["happy"], moods["annoyed"]), ("love_blush", None))
        with self.assertRaises(avatars.AvatarError):
            avatars.save_mood(model, "happy", "no such face")
        with self.assertRaises(avatars.AvatarError):
            avatars.save_mood(model, "no such mood", None)

    def test_framing_is_saved_with_the_model_and_kept_in_range(self):
        model = make_model(os.path.join(self.tmp, "m"))
        self.assertEqual(avatars.inspect(model)["framing"], {"zoom": 1.0, "y": 0.0})
        avatars.save_framing(model, 9, -5)
        self.assertEqual(avatars.inspect(model)["framing"], {"zoom": 3.0, "y": -1.0})


if __name__ == "__main__":
    unittest.main()
