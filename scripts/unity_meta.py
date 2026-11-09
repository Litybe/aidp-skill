#!/usr/bin/env python3
"""Crée sans éditeur Unity les .meta manquants des fichiers ajoutés par une PR sous Assets/.

Usage : unity_meta.py --repo <checkout> --base <ref de base> [--head HEAD] [--sprite-mode single|multiple]
                      [--pivot X,Y] [--slice WxH] [--ppu 16] [--spec spec.json] [--dry-run]
Sortie : JSON {created, checked, skipped, errors}. Code 0 sans erreur, 2 sur erreur (dépôt illisible, aucun modèle).

Règles :
- Fichiers ajoutés = `git diff --diff-filter=A <base>...<head>` sous Assets/. Traités : .png, .aseprite, dossiers nouveaux
  (absents de la base). Les autres extensions sont listées dans `skipped`.
- Le .meta est une copie d'un .meta réel de la branche de base, même type, dossier le plus proche, avec un nouveau GUID.
  Un .meta déjà présent n'est jamais réécrit : il est seulement contrôlé (`checked`, avec ses écarts).
- PNG : réglages du projet imposés (16 pixels par unité, filtre Point, pas de mipmap, textureCompression 0 sur toutes les
  plateformes, bordure nulle, textureType 8), spriteMode et pivot selon la demande ou, à défaut, ceux du modèle.
- .aseprite : réglages d'import conservés du modèle (importer Aseprite), PPU, filtre et mipmap imposés ; les données propres
  à l'asset (sprites, calques, taille) sont vidées : Unity les recalcule au premier import. Ce point n'est pas vérifiable
  sans éditeur.
- spec.json : {"<glob de chemin>": {"spriteMode": "single|multiple", "pivot": [x, y], "slice": [w, h]}}, le premier glob
  qui correspond gagne ; les options de la ligne de commande servent de défaut.
Sans dépendance : texte pur, git en sous-processus.
"""
import argparse
import fnmatch
import json
import posixpath
import random
import re
import subprocess
import sys
import uuid

PPU = 16
PLATFORMS = ("Standalone", "Android", "iOS", "WebGL")
SPRITE_MODES = {"single": 1, "multiple": 2}
ALIGNMENTS = {(0.5, 0.5): 0, (0.0, 1.0): 1, (0.5, 1.0): 2, (1.0, 1.0): 3, (0.0, 0.5): 4, (1.0, 0.5): 5,
              (0.0, 0.0): 6, (0.5, 0.0): 7, (1.0, 0.0): 8}
CUSTOM_ALIGNMENT = 9
GENERATED_EXTENSIONS = (".png", ".aseprite")
FOLDER_META = "fileFormatVersion: 2\nguid: {guid}\nfolderAsset: yes\nDefaultImporter:\n  externalObjects: {{}}\n  userData: \n  assetBundleName: \n  assetBundleVariant: \n"
ASEPRITE_BLANKED = {"animatedSpriteImportData": "[]", "asepriteLayers": "[]", "spriteSheetImportData": "[]"}


class MetaError(Exception):
    pass


def git(repo, *args):
    done = subprocess.run(["git", "-C", repo] + list(args), capture_output=True)
    if done.returncode != 0:
        raise MetaError("git %s: %s" % (" ".join(args), done.stderr.decode("utf-8", "replace").strip()))
    return done.stdout.decode("utf-8", "replace")


def added_paths(repo, base, head):
    out = git(repo, "diff", "--name-only", "--diff-filter=A", "%s...%s" % (base, head), "--", "Assets")
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def base_tree(repo, base):
    return [p for p in git(repo, "ls-tree", "-r", "--name-only", base, "--", "Assets").splitlines() if p]


def base_dirs(paths):
    dirs = set()
    for path in paths:
        parent = posixpath.dirname(path)
        while parent and parent not in dirs:
            dirs.add(parent)
            parent = posixpath.dirname(parent)
    return dirs


def distance(target, candidate):
    """Plus petit = plus proche : dossier commun le plus profond, puis le moins de dossiers en plus."""
    a, b = posixpath.dirname(target).split("/"), posixpath.dirname(candidate).split("/")
    common = 0
    for left, right in zip(a, b):
        if left != right:
            break
        common += 1
    return (-common, (len(a) - common) + (len(b) - common), candidate)


def pick_model(repo, base, target, candidates, accept):
    """Premier .meta de la base, du plus proche au plus lointain, que `accept` valide."""
    for candidate in sorted(candidates, key=lambda c: distance(target, c)):
        text = git(repo, "show", "%s:%s" % (base, candidate))
        if accept(text):
            return candidate, text
    return None, None


def new_guid(used):
    while True:
        guid = uuid.uuid4().hex
        if guid not in used:
            used.add(guid)
            return guid


def set_guid(text, guid):
    return re.sub(r"(?m)^guid: [0-9a-f]+", "guid: " + guid, text, count=1)


def set_line(text, key, value, indent=None):
    """Remplace la valeur de toutes les lignes `key: ...` (à l'indentation donnée, sinon partout)."""
    margin = r"[ ]*" if indent is None else " " * indent
    return re.sub(r"(?m)^(%s%s:)[^\n]*" % (margin, re.escape(key)), lambda m: "%s %s" % (m.group(1), value), text)


def alignment_of(pivot):
    return ALIGNMENTS.get((float(pivot[0]), float(pivot[1])), CUSTOM_ALIGNMENT)


def fmt(number):
    return ("%g" % number)


def sprite_id(rng):
    return "%016x0800000000000000" % rng.getrandbits(64)


def sheet_block(mode, pivot, slice_size, size, name, rng):
    """Bloc `spriteSheet:` complet d'un PNG."""
    align = alignment_of(pivot)
    pivot_text = "{x: %s, y: %s}" % (fmt(pivot[0]), fmt(pivot[1]))
    head = "  spriteSheet:\n    serializedVersion: 2\n    sprites:"
    tail = ("    outline: []\n    customData: \n    physicsShape: []\n    bones: []\n    spriteID: %s\n    internalID: 0\n"
            "    vertices: []\n    indices: \n    edges: []\n    weights: []\n    secondaryTextures: []\n"
            "    spriteCustomMetadata:\n      entries: []\n    nameFileIdTable: %s\n")
    if mode != 2 or not slice_size or not size:
        return head + " []\n" + tail % (sprite_id(rng) if mode == 1 else "", "{}")
    cell_w, cell_h = slice_size
    cols, rows = size[0] // cell_w, size[1] // cell_h
    items, table = [], []
    index = 0
    for row in range(rows):
        for col in range(cols):
            internal = rng.getrandbits(63)
            sprite = "%s_%d" % (name, index)
            items.append(
                "    - serializedVersion: 2\n      name: %s\n      rect:\n        serializedVersion: 2\n        x: %d\n"
                "        y: %d\n        width: %d\n        height: %d\n      alignment: %d\n      pivot: %s\n"
                "      border: {x: 0, y: 0, z: 0, w: 0}\n      customData: \n      outline: []\n      physicsShape: []\n"
                "      tessellationDetail: -1\n      bones: []\n      spriteID: %s\n      internalID: %d\n"
                "      vertices: []\n      indices: \n      edges: []\n      weights: []\n"
                % (sprite, col * cell_w, size[1] - (row + 1) * cell_h, cell_w, cell_h, align, pivot_text,
                   sprite_id(rng), internal))
            table.append("      %s: %d\n" % (sprite, internal))
            index += 1
    return head + "\n" + "".join(items) + tail % ("", "\n" + "".join(table).rstrip("\n"))


def replace_between(text, start_pattern, end_pattern, block):
    start = re.search(start_pattern, text, re.M)
    end = re.search(end_pattern, text, re.M)
    if not start or not end or end.start() < start.start():
        raise MetaError("section %r introuvable dans le modèle" % start_pattern)
    return text[:start.start()] + block + text[end.start():]


def ensure_platforms(text):
    """Chaque plateforme du projet a son entrée platformSettings (copie de DefaultTexturePlatform)."""
    start = text.find("  platformSettings:\n")
    if start < 0:
        raise MetaError("platformSettings absent du modèle")
    end = text.find("\n  spriteSheet:", start)
    section = text[start:end + 1]
    blocks = re.split(r"(?m)^(?=  - serializedVersion)", section)
    head, entries = blocks[0], blocks[1:]
    default = next((e for e in entries if "buildTarget: DefaultTexturePlatform" in e), None)
    if default is None:
        raise MetaError("DefaultTexturePlatform absent du modèle")
    present = {re.search(r"buildTarget: (\S+)", e).group(1) for e in entries}
    for name in PLATFORMS:
        if name not in present:
            entries.append(default.replace("buildTarget: DefaultTexturePlatform", "buildTarget: " + name))
    return text[:start] + head + "".join(entries) + text[end + 1:]


def png_meta(model, guid, mode, pivot, slice_size, size, name, rng):
    if "TextureImporter:" not in model:
        raise MetaError("le modèle PNG n'est pas un TextureImporter")
    text = set_guid(model, guid)
    text = ensure_platforms(text)
    text = set_line(text, "enableMipMap", 0)
    text = set_line(text, "filterMode", 0)
    text = set_line(text, "spritePixelsToUnits", PPU)
    text = set_line(text, "spriteBorder", "{x: 0, y: 0, z: 0, w: 0}", indent=2)
    text = set_line(text, "textureCompression", 0)
    text = set_line(text, "textureType", 8)
    text = set_line(text, "spriteMode", mode, indent=2)
    text = set_line(text, "spritePivot", "{x: %s, y: %s}" % (fmt(pivot[0]), fmt(pivot[1])), indent=2)
    text = set_line(text, "alignment", alignment_of(pivot), indent=2)
    return replace_between(text, r"^  spriteSheet:$", r"^  mipmapLimitGroupName:", sheet_block(mode, pivot, slice_size, size, name, rng))


def blank_section(text, key, value):
    pattern = r"(?ms)^  %s:[^\n]*\n(?:(?:  - |    |  -$)[^\n]*\n?)*" % re.escape(key)
    return re.sub(pattern, "  %s: %s\n" % (key, value), text, count=1)


def aseprite_meta(model, guid):
    if "ScriptedImporter:" not in model:
        raise MetaError("le modèle .aseprite n'est pas un ScriptedImporter")
    text = set_guid(model, guid)
    for key in ("enableMipMap",):
        text = set_line(text, key, 0)
    text = set_line(text, "filterMode", 0)
    text = set_line(text, "spritePixelsToUnits", PPU)
    for key, value in ASEPRITE_BLANKED.items():
        text = blank_section(text, key, value)
    text = set_line(text, "previousTextureSize", "{x: 0, y: 0}", indent=2)
    text = set_line(text, "canvasSize", "{x: 0, y: 0}", indent=2)
    return text


def png_size(path):
    with open(path, "rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def check_png_meta(text, mode, pivot):
    """Écarts d'un .meta PNG existant avec les réglages du projet (jamais corrigés)."""
    issues = []

    def value(key, indent=None):
        margin = r"[ ]*" if indent is None else " " * indent
        found = re.findall(r"(?m)^%s%s: ([^\n]*)" % (margin, re.escape(key)), text)
        return found

    expectations = [("spritePixelsToUnits", None, str(PPU)), ("filterMode", None, "0"), ("enableMipMap", None, "0"),
                    ("textureType", None, "8")]
    for key, indent, expected in expectations:
        found = value(key, indent)
        if not found or any(v.strip() != expected for v in found):
            issues.append("%s=%s attendu %s" % (key, ",".join(found) or "absent", expected))
    compressions = value("textureCompression")
    if not compressions or any(v.strip() != "0" for v in compressions):
        issues.append("textureCompression=%s attendu 0 partout" % (",".join(compressions) or "absent"))
    targets = re.findall(r"buildTarget: (\S+)", text)
    for name in PLATFORMS:
        if name not in targets:
            issues.append("plateforme %s absente de platformSettings" % name)
    if mode:
        found = value("spriteMode", 2)
        if not found or found[0].strip() != str(mode):
            issues.append("spriteMode=%s attendu %s" % (found[0] if found else "absent", mode))
    if pivot:
        found = value("spritePivot", 2)
        expected = "{x: %s, y: %s}" % (fmt(pivot[0]), fmt(pivot[1]))
        if not found or found[0].strip() != expected:
            issues.append("spritePivot=%s attendu %s" % (found[0] if found else "absent", expected))
    return issues


def parse_pair(raw, label):
    try:
        parts = [float(p) for p in re.split(r"[,x]", raw)]
    except ValueError:
        parts = []
    if len(parts) != 2:
        raise MetaError("%s invalide : %r" % (label, raw))
    return parts


def settings_for(path, defaults, spec):
    result = dict(defaults)
    for pattern, rule in spec.items():
        if fnmatch.fnmatch(path, pattern):
            for key in ("spriteMode", "pivot", "slice"):
                if key in rule:
                    result[key] = rule[key]
            break
    return result


def run(repo, base, head, defaults, spec, dry_run, seed=None):
    rng = random.Random(seed)
    summary = {"created": [], "checked": [], "skipped": [], "errors": []}
    added = [p for p in added_paths(repo, base, head) if not p.endswith(".meta")]
    tree = base_tree(repo, base)
    known_dirs = base_dirs(tree)
    used_guids = set()
    targets = []
    for path in added:
        if path.endswith(GENERATED_EXTENSIONS):
            targets.append(path)
        else:
            summary["skipped"].append({"path": path, "reason": "type sans règle (ni .png ni .aseprite)"})
        parent = posixpath.dirname(path)
        while parent and parent != "Assets" and parent not in known_dirs:
            if parent not in targets:
                targets.append(parent)
            parent = posixpath.dirname(parent)
    metas = [p for p in tree if p.endswith(".meta")]
    for target in targets:
        meta_path = target + ".meta"
        full = posixpath.join(repo, meta_path)
        try:
            with open(full, encoding="utf-8", newline="") as handle:
                existing = handle.read()
        except FileNotFoundError:
            existing = None
        is_png = target.endswith(".png")
        cfg = settings_for(target, defaults, spec)
        mode = SPRITE_MODES[cfg["spriteMode"]] if cfg.get("spriteMode") else None
        if existing is not None:
            issues = check_png_meta(existing, mode, cfg.get("pivot")) if is_png else []
            summary["checked"].append({"path": meta_path, "issues": issues})
            continue
        try:
            if is_png:
                candidates = [m for m in metas if m.endswith(".png.meta")]
                model_path, model = pick_model(repo, base, target, candidates,
                                               lambda t: "TextureImporter:" in t and re.search(r"(?m)^  textureType: 8$", t))
            elif target.endswith(".aseprite"):
                candidates = [m for m in metas if m.endswith(".aseprite.meta")]
                model_path, model = pick_model(repo, base, target, candidates, lambda t: "ScriptedImporter:" in t)
            else:
                candidates = [m for m in metas if m[:-5] in known_dirs]
                model_path, model = pick_model(repo, base, target, candidates, lambda t: "folderAsset: yes" in t)
            guid = new_guid(used_guids)
            if is_png:
                if model is None:
                    raise MetaError("aucun .png.meta de sprite dans la base pour %s" % target)
                model_mode = mode or int(re.search(r"(?m)^  spriteMode: (\d+)", model).group(1))
                pivot = cfg.get("pivot") or [float(v) for v in re.search(
                    r"(?m)^  spritePivot: \{x: ([-\d.]+), y: ([-\d.]+)\}", model).groups()]
                size = png_size(posixpath.join(repo, target))
                text = png_meta(model, guid, model_mode, pivot, cfg.get("slice"), size,
                                posixpath.splitext(posixpath.basename(target))[0], rng)
            elif target.endswith(".aseprite"):
                if model is None:
                    raise MetaError("aucun .aseprite.meta dans la base pour %s" % target)
                text = aseprite_meta(model, guid)
            else:
                text = set_guid(model, guid) if model else FOLDER_META.format(guid=guid)
            if model and "\r\n" in model:
                text = text.replace("\r\n", "\n").replace("\n", "\r\n")
            if not dry_run:
                with open(full, "w", encoding="utf-8", newline="") as handle:
                    handle.write(text)
            summary["created"].append({"path": meta_path, "guid": guid, "model": model_path or "(gabarit dossier)"})
        except MetaError as error:
            summary["errors"].append({"path": target, "error": str(error)})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--sprite-mode", choices=sorted(SPRITE_MODES))
    parser.add_argument("--pivot")
    parser.add_argument("--slice")
    parser.add_argument("--spec")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        defaults = {"spriteMode": args.sprite_mode,
                    "pivot": parse_pair(args.pivot, "pivot") if args.pivot else None,
                    "slice": [int(v) for v in parse_pair(args.slice, "slice")] if args.slice else None}
        spec = json.load(open(args.spec, encoding="utf-8")) if args.spec else {}
        summary = run(args.repo, args.base, args.head, defaults, spec, args.dry_run)
    except (MetaError, OSError, ValueError) as error:
        print(json.dumps({"errors": [{"error": str(error)}]}))
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 2 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
