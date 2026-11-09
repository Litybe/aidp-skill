#!/usr/bin/env python3
"""Tests de unity_meta.py : `python scripts/test_unity_meta.py`. Dépôt git temporaire, Pillow pour les PNG."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unity_meta  # noqa: E402

PLATFORM = ("  - serializedVersion: 4\n    buildTarget: %s\n    maxTextureSize: 2048\n    textureFormat: -1\n"
            "    textureCompression: %d\n    overridden: 0\n")
PNG_MODEL = """fileFormatVersion: 2
guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
TextureImporter:
  mipmaps:
    mipMapMode: 0
    enableMipMap: 1
  textureSettings:
    filterMode: 1
  spriteMode: 1
  alignment: 0
  spritePivot: {x: 0.5, y: 0.5}
  spritePixelsToUnits: 100
  spriteBorder: {x: 1, y: 1, z: 1, w: 1}
  textureType: 8
  platformSettings:
""" + PLATFORM % ("DefaultTexturePlatform", 1) + PLATFORM % ("Standalone", 1) + """  spriteSheet:
    serializedVersion: 2
    sprites: []
    spriteID: 0000000000000000
    nameFileIdTable: {}
  mipmapLimitGroupName: 
  userData: 
"""
ASE_MODEL = """fileFormatVersion: 2
guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
ScriptedImporter:
  textureImporterSettings:
    enableMipMap: 0
    filterMode: 0
    spritePixelsToUnits: 100
  singleSpriteImportData:
  - name: 
  animatedSpriteImportData:
  - name: modele
    rect:
      x: 4
  spriteSheetImportData: []
  asepriteLayers:
  - layerIndex: 0
    name: modele
  tileSets: []
  previousTextureSize: {x: 64, y: 64}
  canvasSize: {x: 32, y: 32}
"""
DIR_MODEL = "fileFormatVersion: 2\nguid: cccccccccccccccccccccccccccccccc\nfolderAsset: yes\nDefaultImporter:\n  userData: \n"


def run(*cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def write(root, path, text="x"):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def png(root, path, size=(32, 16)):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    Image.new("RGBA", size, (255, 0, 0, 255)).save(full)


class MetaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("git", "init", "-q", "-b", "main", cwd=self.root)
        run("git", "config", "user.email", "t@t", cwd=self.root)
        run("git", "config", "user.name", "t", cwd=self.root)
        png(self.root, "Assets/Sprites/Near/old.png")
        write(self.root, "Assets/Sprites/Near/old.png.meta", PNG_MODEL.replace("aaaa", "1111"))
        png(self.root, "Assets/Other/far.png")
        write(self.root, "Assets/Other/far.png.meta", PNG_MODEL.replace("aaaa", "2222").replace("filterMode: 1", "filterMode: 0"))
        write(self.root, "Assets/Sprites/Near/old.aseprite")
        write(self.root, "Assets/Sprites/Near/old.aseprite.meta", ASE_MODEL)
        write(self.root, "Assets/Sprites.meta", DIR_MODEL)
        write(self.root, "Assets/Sprites/Near.meta", DIR_MODEL)
        run("git", "add", "-A", cwd=self.root)
        run("git", "commit", "-qm", "base", cwd=self.root)
        run("git", "switch", "-qc", "feat", cwd=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def commit_changes(self):
        run("git", "add", "-A", cwd=self.root)
        run("git", "commit", "-qm", "pr", cwd=self.root)

    def read(self, path):
        with open(os.path.join(self.root, path), encoding="utf-8", newline="") as handle:
            return handle.read()

    def go(self, **defaults):
        base = {"spriteMode": None, "pivot": None, "slice": None}
        base.update(defaults)
        return unity_meta.run(self.root, "main", "HEAD", base, {}, False, seed=7)

    def test_png_gets_project_settings_and_new_guid(self):
        png(self.root, "Assets/Sprites/Near/new.png")
        self.commit_changes()
        summary = self.go()
        self.assertEqual(summary["errors"], [])
        self.assertEqual([c["path"] for c in summary["created"]], ["Assets/Sprites/Near/new.png.meta"])
        text = self.read("Assets/Sprites/Near/new.png.meta")
        self.assertEqual(summary["created"][0]["model"], "Assets/Sprites/Near/old.png.meta")
        self.assertNotIn("1111", text.split("\n")[1])
        self.assertRegex(text, r"(?m)^guid: [0-9a-f]{32}$")
        for expected in ("spritePixelsToUnits: 16", "filterMode: 0", "enableMipMap: 0", "textureType: 8",
                         "spriteBorder: {x: 0, y: 0, z: 0, w: 0}"):
            self.assertIn(expected, text)
        self.assertEqual(re.findall(r"textureCompression: (\d)", text), ["0"] * 5)
        for platform in unity_meta.PLATFORMS:
            self.assertIn("buildTarget: " + platform, text)

    def test_only_guid_and_wanted_settings_differ_from_model(self):
        png(self.root, "Assets/Sprites/Near/new.png")
        self.commit_changes()
        self.go()
        def before_sheet(raw):
            return raw.split("  spriteSheet:")[0].splitlines()

        model = before_sheet(self.read("Assets/Sprites/Near/old.png.meta"))
        text = before_sheet(self.read("Assets/Sprites/Near/new.png.meta"))
        changed = [line for line in text if line not in model]
        allowed = re.compile(r"guid:|enableMipMap|filterMode|spritePixelsToUnits|spriteBorder|textureCompression|buildTarget|"
                             r"serializedVersion|maxTextureSize|textureFormat|overridden|spriteID")
        self.assertTrue(all(allowed.search(line) for line in changed), changed)

    def test_sprite_mode_and_pivot_from_request(self):
        png(self.root, "Assets/Sprites/Near/new.png")
        self.commit_changes()
        self.go(spriteMode="single", pivot=[0.5, 0.0])
        text = self.read("Assets/Sprites/Near/new.png.meta")
        self.assertIn("spritePivot: {x: 0.5, y: 0}", text)
        self.assertIn("  alignment: 7", text)
        self.assertIn("  spriteMode: 1", text)

    def test_multiple_mode_slices_the_sheet(self):
        png(self.root, "Assets/Sprites/Near/sheet.png", size=(32, 16))
        self.commit_changes()
        self.go(spriteMode="multiple", pivot=[0.5, 0.5], slice=[16, 16])
        text = self.read("Assets/Sprites/Near/sheet.png.meta")
        self.assertIn("  spriteMode: 2", text)
        self.assertEqual(re.findall(r"(?m)^      name: (\S+)", text), ["sheet_0", "sheet_1"])
        self.assertIn("x: 16", text)
        self.assertEqual(len(re.findall(r"(?m)^      \S+_\d: \d+$", text)), 2)

    def test_existing_meta_is_checked_never_rewritten(self):
        png(self.root, "Assets/Sprites/Near/new.png")
        bad = PNG_MODEL.replace("aaaa", "9999")
        write(self.root, "Assets/Sprites/Near/new.png.meta", bad)
        self.commit_changes()
        summary = self.go()
        self.assertEqual(summary["created"], [])
        self.assertEqual(self.read("Assets/Sprites/Near/new.png.meta"), bad)
        issues = summary["checked"][0]["issues"]
        self.assertTrue(any("spritePixelsToUnits" in i for i in issues), issues)
        self.assertTrue(any("textureCompression" in i for i in issues), issues)

    def test_aseprite_copies_importer_and_blanks_asset_data(self):
        write(self.root, "Assets/Sprites/Near/new.aseprite")
        self.commit_changes()
        summary = self.go()
        text = self.read("Assets/Sprites/Near/new.aseprite.meta")
        self.assertEqual(summary["created"][0]["model"], "Assets/Sprites/Near/old.aseprite.meta")
        self.assertIn("animatedSpriteImportData: []", text)
        self.assertIn("asepriteLayers: []", text)
        self.assertNotIn("modele", text)
        self.assertIn("spritePixelsToUnits: 16", text)
        self.assertIn("  tileSets: []", text)
        self.assertIn("canvasSize: {x: 0, y: 0}", text)

    def test_new_folders_get_a_meta_and_known_ones_do_not(self):
        png(self.root, "Assets/Sprites/Near/Deep/Deeper/new.png")
        self.commit_changes()
        summary = self.go()
        paths = sorted(c["path"] for c in summary["created"])
        self.assertEqual(paths, ["Assets/Sprites/Near/Deep.meta", "Assets/Sprites/Near/Deep/Deeper.meta",
                                 "Assets/Sprites/Near/Deep/Deeper/new.png.meta"])
        self.assertIn("folderAsset: yes", self.read("Assets/Sprites/Near/Deep.meta"))
        self.assertFalse(os.path.exists(os.path.join(self.root, "Assets/Sprites/Near.meta.meta")))

    def test_unknown_types_are_skipped_and_guids_are_unique(self):
        write(self.root, "Assets/Sprites/Near/a.controller")
        png(self.root, "Assets/Sprites/Near/a.png")
        png(self.root, "Assets/Sprites/Near/b.png")
        self.commit_changes()
        summary = self.go()
        self.assertEqual([s["path"] for s in summary["skipped"]], ["Assets/Sprites/Near/a.controller"])
        guids = [c["guid"] for c in summary["created"]]
        self.assertEqual(len(guids), len(set(guids)))

    def test_second_run_creates_nothing(self):
        png(self.root, "Assets/Sprites/Near/new.png")
        self.commit_changes()
        self.go()
        again = self.go()
        self.assertEqual(again["created"], [])
        self.assertEqual(again["checked"][0]["issues"], [])

    def test_cli_exit_code_and_json(self):
        png(self.root, "Assets/Sprites/Near/new.png")
        self.commit_changes()
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unity_meta.py")
        done = subprocess.run([sys.executable, script, "--repo", self.root, "--base", "main", "--dry-run"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(json.loads(done.stdout)["created"]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "Assets/Sprites/Near/new.png.meta")))


if __name__ == "__main__":
    unittest.main()
