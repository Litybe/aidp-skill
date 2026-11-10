#!/usr/bin/env python3
"""Lance Unity en mode batch sur un worktree jetable pour creer ou modifier prefabs, scenes et .meta (jamais a la main).

Usage : unity_batch.py --project <worktree> --method <Classe.Methode> [--arg nom=valeur ...] [--log chemin]
                       [--timeout 1800] [--editor Unity.exe] [--no-seed] [--keep-lock-wait 900]
Sortie : JSON {ok, exit, seconds, log, errors, changed, bad_meta}. Code 0 si Unity sort a 0, sans erreur de compilation,
sans ligne "[CLI] FAIL" et sans .meta invalide ; 1 sinon ; 2 sur erreur d'usage ; 3 si le projet est un projet vivant.

Points d'entree du projet PixelHood (Assets/Scripts/Editor/Cli/) :
  Game.Cli.Editor.CliCommands.BuildScene   --arg builderType=Game.Playtest.EditorTools.PlaytestArenaBuilder [--arg builderMethod=Build]
  Game.Cli.Editor.CliCommands.CreatePrefab --arg recipe=<recette.json>
  Game.Cli.Editor.CliCommands.EditScene    --arg recipe=<recette.json>
  Game.Cli.Editor.CliCommands.Reimport     [--arg paths=Assets/A;Assets/B]   (genere aussi les .meta manquants)

Regles :
- Refuse tout projet sous un dossier vivant (AIDP_UNITY_LIVE, defaut C:/UNITY_PROJECT) : l'editeur ouvert n'est jamais touche.
- Un seul Unity batch a la fois (verrou D:/AIDP/cache/unity-batch.lock, attente bornee), pour la memoire et le CPU.
- Les paquets integres gitignores (Packages/com.*, ex. Animancer) sont copies depuis AIDP_UNITY_EMBEDDED
  (defaut C:/UNITY_PROJECT/PixelHood/Packages) quand ils manquent : sans eux rien ne compile dans un worktree.
- Library : copiee depuis le cache D:/AIDP/cache/unity-library-seed si absente (premier import evite) ; le cache est
  rempli par la premiere execution reussie.
- Seul le processus lance ici est tue (par PID) en cas de depassement de delai. La ligne de commande Unity n'est jamais affichee.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

DEFAULT_EDITOR = "C:/Unity_Install/6000.6.8f1/Editor/Unity.exe"
DEFAULT_LIVE = "C:/UNITY_PROJECT"
DEFAULT_EMBEDDED = "C:/UNITY_PROJECT/PixelHood/Packages"
SEED_DIR = "D:/AIDP/cache/unity-library-seed"
LOCK_FILE = "D:/AIDP/cache/unity-batch.lock"
DEFAULT_TIMEOUT = 1800
DEFAULT_LOCK_WAIT = 900
POLL_SECONDS = 2
ERROR_LINES_MAX = 20
GUID_RE = re.compile(r"^guid: [0-9a-f]{32}$", re.M)
COMPILE_ERROR_RE = re.compile(r"error CS\d+")
CLI_FAIL = "[CLI] FAIL"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def norm(path):
    return os.path.normcase(os.path.abspath(path)).replace("\\", "/")


def is_live(project):
    live = [p for p in os.environ.get("AIDP_UNITY_LIVE", DEFAULT_LIVE).split(";") if p]
    p = norm(project)
    return any(p == norm(x) or p.startswith(norm(x).rstrip("/") + "/") for x in live)


def pid_alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock(wait):
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    deadline = time.time() + wait
    while True:
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                owner = int(open(LOCK_FILE).read().strip() or 0)
            except (OSError, ValueError):
                owner = 0
            if owner and not pid_alive(owner):
                try:
                    os.remove(LOCK_FILE)
                except OSError:
                    pass
                continue
            if time.time() > deadline:
                return False
            time.sleep(POLL_SECONDS)


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


def robocopy(src, dst):
    # codes robocopy 0..7 = succes
    r = subprocess.run(["robocopy", src.replace("/", "\\"), dst.replace("/", "\\"), "/E", "/MT:16", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
                       capture_output=True, text=True)
    return r.returncode < 8


def prepare_packages(project):
    src = os.environ.get("AIDP_UNITY_EMBEDDED", DEFAULT_EMBEDDED)
    dst = os.path.join(project, "Packages")
    copied = []
    if not os.path.isdir(src):
        return copied
    os.makedirs(dst, exist_ok=True)
    for name in sorted(os.listdir(src)):
        s, d = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(s) and not os.path.exists(d) and robocopy(s, d):
            copied.append(name)
    return copied


def seed_library(project):
    lib = os.path.join(project, "Library")
    if os.path.isdir(lib) or not os.path.isdir(SEED_DIR):
        return False
    return robocopy(SEED_DIR, lib)


def kill_tree(pid):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def git_changed(project):
    r = subprocess.run(["git", "-C", project, "status", "--porcelain", "--", "Assets"], capture_output=True, text=True)
    return [line[3:].strip().strip('"') for line in r.stdout.splitlines() if line.strip()]


def check_meta(project, changed):
    bad = []
    for rel in changed:
        if rel.endswith("/") or not rel.endswith(".meta"):
            continue
        full = os.path.join(project, rel)
        if os.path.isfile(full) and not GUID_RE.search(open(full, encoding="utf-8", errors="replace").read()):
            bad.append(rel)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--method", required=True)
    ap.add_argument("--arg", action="append", default=[], help="nom=valeur, transmis a Unity sous -nom valeur")
    ap.add_argument("--log")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--editor", default=os.environ.get("AIDP_UNITY_EDITOR", DEFAULT_EDITOR))
    ap.add_argument("--no-seed", action="store_true")
    ap.add_argument("--keep-lock-wait", type=int, default=DEFAULT_LOCK_WAIT)
    a = ap.parse_args()

    project = os.path.abspath(a.project)
    if is_live(project):
        print(json.dumps({"ok": False, "error": "projet vivant refuse: " + project}))
        return 3
    if not os.path.isfile(os.path.join(project, "ProjectSettings", "ProjectVersion.txt")) or not os.path.isfile(a.editor):
        print(json.dumps({"ok": False, "error": "projet Unity ou editeur introuvable"}))
        return 2
    log = os.path.abspath(a.log or os.path.join(project, "..", os.path.basename(project) + ".unity-batch.log"))

    cmd = [a.editor, "-batchmode", "-nographics", "-quit", "-projectPath", project, "-executeMethod", a.method, "-logFile", log]
    for item in a.arg:
        name, _, value = item.partition("=")
        cmd += ["-" + name, value]

    if not acquire_lock(a.keep_lock_wait):
        print(json.dumps({"ok": False, "error": "verrou Unity batch occupe"}))
        return 1
    start = time.time()
    code, timed_out, seeded = -1, False, False
    try:
        packages = prepare_packages(project)
        seeded = False if a.no_seed else seed_library(project)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        while proc.poll() is None:
            if time.time() - start > a.timeout:
                timed_out = True
                kill_tree(proc.pid)
                break
            time.sleep(POLL_SECONDS)
        code = proc.wait()
        text = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else ""
        errors = [l.strip() for l in text.splitlines() if COMPILE_ERROR_RE.search(l) or CLI_FAIL in l][:ERROR_LINES_MAX]
        changed = git_changed(project)
        bad = check_meta(project, changed)
        ok = code == 0 and not errors and not bad and not timed_out
        if ok and not a.no_seed and not os.path.isdir(SEED_DIR):
            robocopy(os.path.join(project, "Library"), SEED_DIR)
        print(json.dumps({"ok": ok, "exit": code, "timeout": timed_out, "seconds": round(time.time() - start),
                          "library_seeded": seeded, "packages_copied": packages, "log": log, "errors": errors,
                          "changed": changed, "bad_meta": bad}, ensure_ascii=False))
        return 0 if ok else 1
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
