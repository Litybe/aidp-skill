---
description: Run the ai-dev-pipeline-v7 `pixelart` pipeline (art direction brief, Pixellab generation, animation, scored review, hand cleanup, Unity export) on one GitHub issue that describes a pixel art asset. Usage — /run-pixelart-pipeline <issue>.
argument-hint: "<issue number>"
---

Run the **pixelart** pipeline of **ai-dev-pipeline-v7** on GitHub issue `$1`. Activate the
**ai-dev-pipeline-v7** skill and follow its `SKILL.md` « Procedure » (steps 3 to 6: `run start`,
`Workflow`, write `workflow-result.json`, `run reconcile`, gates, pauses, exit 127). You are a thin
driver: the five pixel agents (`pixel-art-director`, `pixel-artist`, `pixel-animator`,
`pixel-reviewer`, `pixel-fixer`) do the real work inside the Workflow.

## Arguments
- `$1` = the GitHub issue number (`42` or `#42`; strip the `#`). Missing or not a number:
  `AskUserQuestion` for it. Never guess.

## 1. Preconditions
1. Set `AIDP_SKILL_ROOT=~/.claude/skills/ai-dev-pipeline-v7` for every `aidp` call (bash prefix, or
   `$env:AIDP_SKILL_ROOT` in PowerShell).
2. The current directory must be the game project (a Unity project holds `Assets/` and
   `ProjectSettings/`). Otherwise stop and say so: the sprites are written into this project.
3. `rtk aidp vault status --format json-compact` once: warn if no vault is configured, then go on.
4. The MCP servers `pixellab` and `aseprite` must be connected (ToolSearch `pixellab` / `aseprite`).
   Missing → stop and say which one.

## 2. Read the issue
`rtk proxy gh issue view <n> --json number,title,body,labels,url,state` (the only non-`aidp` Bash
call allowed besides the ones in §5). A closed issue: say so and ask whether to go on.

Map it to the pipeline inputs. A value comes, in this order, from a label, then a `key: value` line of
the body (case-insensitive, `-`, `*` and `**` markup ignored, French aliases accepted), then the
default:

| Input | Label | Body keys | Default |
|---|---|---|---|
| `asset_kind` | `pixel:<kind>` or `asset:<kind>` | `asset_kind`, `type`, `kind`, `besoin` | inferred (below), never asked |
| `view` | `view:<v>` | `view`, `vue` | `side` |
| `size` | — | `size`, `taille`, `canvas` | `""` (project profile) |
| `palette` | `palette:<name>` | `palette` | `rosy-42` |
| `source` | — | `source`, `base`, `animate` | `""` |
| `style_ref` | — | `style_ref`, `style`, `reference` | `""` |
| `max_cost` | `budget:<n>` | `max_cost`, `budget`, `generations` | `30` |

- `asset_kind` values: `item`, `item_animation`, `character`, `character_animation`, `ui`,
  `ui_animation`, `tileset`, `tileset_animation`, `map_assets`, `image`. Accept French words
  (personnage → character, objet → item, interface → ui, tuiles → tileset; « animation » or « animé »
  adds `_animation`). A value outside the list is ignored and the kind is inferred.
- **Inferring `asset_kind`** (no label, no body key, or a value outside the list): decide alone from
  the title, the body and the acceptance criteria, first rule that matches. Never ask the user.
  1. Base kind:
     - `map_assets` — several props + tiles for one biome or room, « kit », « décor de zone ».
     - `tileset` — tileset, tuiles, autotile, terrain, sol, mur peint au pinceau LDtk, IntGrid.
     - `ui` — UI, HUD, interface, menu, bouton, barre, icône d'inventaire, écran-titre, logo, titre.
     - `character` — personnage, PNJ, ennemi, boss, créature, joueur, Garance, silhouette d'un être.
     - `image` — illustration, fond, background, parallax, splash, image plein écran.
     - `item` — everything else: objet, interactable, prop, porte, pont, levier, lanterne, mur,
       plancher, échelle, cairn, pickup, collectible.
  2. Add `_animation` when the asset moves or changes over frames: « animation », « animé »,
     « frames », « N frames », « boucle », « lueur », « clignote », « balance », « effritement »,
     « cassable », « s'ouvre », « s'abaisse », or several timed states (« 3 états » played in turn).
     Several static variants or states with no timing stay static (one frame per tag).
  3. Several assets in one issue: take the kind of the main asset (the first one of the title) and
     let the brief stage cover the others in the same run.
  Write the inferred kind and the rule that chose it in the summary of §3 and in the report and PR
  body of §5 / §6 (« Type choisi : `item_animation` — "4 frames" dans le titre »).
- `prompt` = `#<n> <title>` + a blank line + the body (labels and `key: value` lines kept: the brief
  stage reads them too). `feature` = `issue-<n>`; target = `issue-<n>`.

## 3. Summary, no confirmation
Never ask before spending: the budget is `max_cost` from §2 (label, body key, else `30`), and that
value is the approval. Call `get_balance` once: a budget above the generations left is lowered to
what is left (say so). Print in 3-5 lines, then go straight to §4: issue title, asset_kind with the
rule that chose it, view, size, palette, source / style_ref when set, budget and balance.

## 4. Run
`rtk aidp run start --pipeline pixelart --target issue-<n> --input prompt=<prompt> --input asset_kind=<kind> --input view=<view> --input size=<size> --input palette=<palette> --input source=<source> --input style_ref=<style_ref> --input max_cost=<n> --input feature=issue-<n>`
(pass the prompt with `--inputs '<json>'` instead when it holds quotes or newlines: build one JSON
object with every input, and keep `--target`). Then drive it to the end per `SKILL.md`.
- `done` → §5.
- Paused at `correction` (still `fix_needed` after two fix + recheck rounds) → relay the remaining
  findings of the last `recheck/findings.json` and its regeneration advice, then
  `AskUserQuestion`: « Défauts encore ouverts après 2 tours. Garder l'asset tel quel ? » →
  *Garder et finir le rapport (recommandé)* / *Arrêter ici*. Never relaunch a paid generation
  yourself.
- `brief` blocked (plan above the budget) → do not raise `max_cost`: report the cheapest viable
  plan and its cost, then stop (`QUEUE-RESULT: blocked — budget <max_cost> < plan <cost>` when the
  queue asked for that line). The user reruns with a `budget:<n>` label.
- Any other pause, `blocked` or `failed` → relay the envelope (stage, summary, follow-ups) and
  `rtk aidp run summary --run <run_id>`, then stop. A Pixellab « out of generations » block: say to
  check `get_balance`, then the `pixellab` skill's `rotate_secret.py` and a Claude Code restart, then
  `/pipeline-resume-v7 <run_id>`.

## 5. End
Read `<run_dir>/brief/art-brief.md`, `<run_dir>/animate/asset.json`, the last findings
(`recheck/findings.json`, else `verify/findings.json`) and `fix/fix.json` when it exists. Print one
short report:
- the asset: kind, canvas, frames and ms per tag, palette, files written in the project (.aseprite,
  exported sheet + JSON), the control GIF / preview paths;
- quality: review score /10 and workbench score, findings fixed / left open;
- Pixellab: ids (character / object / tileset, animation groups), generations spent / budget,
  balance left;
- the run dir (vault path) and `run_id`.
Post the report on the issue: `rtk proxy gh issue comment <n> --body-file -` with the report on
stdin (no local paths outside the project, no token). Keep the comment URL.

## 6. Publish on a PR
The sprites are delivered as a pull request, never straight on `main`. Run each git / gh command
with `rtk proxy` and stop at the first failure (relay it, then end with `QUEUE-RESULT: failed` when
the queue asked for that line).
1. List the project files the run wrote or changed: every path under `Assets/` named in
   `generation.json`, `asset.json` and `fix.json` (.aseprite, exported sheet .png + .json,
   .controller / .anim if any), plus their `.meta` files (generated by Unity; when one is missing,
   say so in the PR body and go on). Nothing else: never `git add -A` or `git add .`.
1b. Screenshots for the PR: write upscaled previews of the final asset to
   `Docs/art-previews/issue-<n>/` (outside `Assets/`, so Unity imports nothing):
   `mcp__aseprite__preview` of the .aseprite at scale 8 (`single` for a static asset, plus `strip`
   of each tag for an animation) saved as `<asset>_preview.png` / `<asset>_<tag>_strip.png`, and the
   control GIF of each animated tag copied as `<asset>_<tag>.gif` when the run made one. Add them to
   the file list of step 1. If `preview` cannot write a file, use `mcp__aseprite__export` with a
   scale of 8, or `aseprite -b <file.aseprite> --scale 8 --save-as <png>`.
2. `git status --porcelain -- <files>` must show them; `git rev-parse --abbrev-ref HEAD` gives the
   base branch (`main` normally).
3. `git switch -c art/issue-<n>-<short-slug>` (slug from the asset name, ascii, max 30 chars; add
   `-2` if the branch exists).
4. `git add -- <files>` then `git commit -m "feat(art): <issue title without its own prefix> (#<n>)"`
   with the body `Closes #<n>` and the commit attribution lines of the system reminder.
5. `git push -u origin art/issue-<n>-<short-slug>`.
6. `gh pr create --base <base> --head art/issue-<n>-<short-slug> --title "<issue title>" --body-file -`
   with on stdin, in French: `Closes #<n>`, `## Aperçu` (each screenshot of step 1b as
   `![<asset> <tag>](https://github.com/<owner>/<repo>/blob/<commit sha>/Docs/art-previews/issue-<n>/<file>?raw=true)`,
   sha from `git rev-parse HEAD` after the push, so the images survive the branch deletion),
   `## Contenu` (each file, canvas, frames and ms per tag,
   palette, slices / pivot), `## Vérifs` (lint, `unity_validate`, workbench score, review /10),
   `## Écarts ouverts` (findings left open, one line each with its id), `## Reste manuel` (Unity
   import, prefab wiring, Play Mode), the link to the issue comment, then the PR attribution line of
   the system reminder. Not a draft.
7. `git switch <base>` so the next run starts from a clean base (the files stay on the PR branch).
8. `gh pr view <pr> --json body` and check every `## Aperçu` URL answers
   (`gh api repos/<owner>/<repo>/contents/Docs/art-previews/issue-<n>/<file>?ref=<sha>`); fix the
   body with `gh pr edit <pr> --body-file -` if one is wrong.
9. Print the PR URL. Never merge it, never close the issue.

## Rules
- One run at a time; never start a second while one is running or paused.
- Do NOT call `Edit`, `Write`, `MultiEdit`, or non-`aidp` Bash yourself, except: `gh issue view`
  (§2), `gh issue comment` (§5), the git / gh commands and the preview files of §6, writing
  `<run_dir>/workflow-result.json`, and reading the files named in §5. Never hand-edit a `workflow.js`.
- Never answer a gate or a question for the user, never raise `max_cost` above the §2 value.
