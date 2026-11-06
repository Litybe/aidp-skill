# Pipelines de contenu gamedev : art, map, doc

Lot P3 du plan gamedev. Huit templates `version: 5`, joués par le binaire `aidp` en sessions
`claude -p` autonomes, appelés par les flows `game-art`, `game-map`, `game-doc`
(plan `PLAN-GAMEDEV.md` §3.1, §4.2). Les pipelines `unity-*` et `issue-refine` sont décrits
ailleurs ; le contrat d'usage du compile gate C1 et des scénarios C2 est dans `unity-verify.md`
(skill `unity-issue-workflow`).

| Route | Produire | Revue | Test |
|---|---|---|---|
| `art` | `art-produce` | `art-review` | `art-import` |
| `map` | `map-produce` | `map-review` | `map-test` |
| `doc` | `doc-write` | `doc-review` | aucun (pas d'éditeur Unity) |

## Sorties lues par les flows (contrat C4)

Une sortie de stage est un fichier ; un flow lit un champ du JSON par
`steps.<id>.outputs.<fichier sans extension>.<champ>`.

| Pipeline | Fichier | Champs |
|---|---|---|
| `*-produce`, `doc-write` | `pr.json` (stage `report`) | `pr`, `branch`, `summary`, `url` |
| `*-review` | `verdict.json` (stage `verdict`) | `verdict` (`done` ou `need-fix`), `fix_needed`, `blocking`, `findings` (nombre), `next` |
| `*-review` | `findings.json` (stage `review`) | `findings` (liste), `fix_needed`, `criteria` |
| `*-review` | `review.md` | rapport Markdown, titré « ## Revue avocat du diable — verdict : done \| need-fix » |
| `art-import`, `map-test` | `result.json` (stage `report`) | `passed` (booléen), `report`, `blocked` |
| `art-import`, `map-test` | `report.md` | rapport Markdown, captures dans le dossier de stage |

Ids de stage (C5) : `prepare`, `brief`, `generate`, `animate`, `fix`, `import`, `test`, `graph`,
`rooms`, `write`, `review`, `verdict`, `report`. La politique de modèles du daemon (T5) remplace
le modèle écrit dans le template ; les valeurs écrites sont les défauts.

## art-produce

Issu de `pixelart` (conservé). `prepare` (haiku : issue, branche `art/<n>-<slug>`) →
`brief` (opus, `pixel-art-director`) → `generate` (opus, `pixel-artist`) → `animate`
(opus, `pixel-animator`, passe-plat pour un asset statique) → `verify` (opus, `pixel-reviewer`) →
boucle `correction` (`fix` opus `pixel-fixer` + `recheck` sonnet, 2 tours) → `report` (haiku :
commit, push, PR draft `Closes #n`).

- Entrées : `issue`, `prompt`, `asset_kind`, `source`, `style_ref`, `view`, `size`, `palette`
  (`rosy-42`), `max_cost` (défaut **10** générations par issue), `feature`.
- Budget Pixellab (C6) : `brief`, `generate`, `animate` et `fix` écrivent `pixellab-usage.json`
  (`balanceBefore`, `balanceAfter`, `generations`, `jobs`, `recordedAt`) ; le plafond de 10
  générations, tous stages confondus, est rappelé dans leur policy. Le stage `report` additionne
  les usages dans le corps de PR. Le daemon agrège et applique la réserve ; il n'appelle jamais
  Pixellab.
- Sortie : `pr.json`. La boucle lit `stages.verify.outputs.findings.fix_needed`.

## art-review

Avocat du diable art, lecture seule. `prepare` (haiku : PR, critères, téléchargement des fichiers de
la PR dans le dossier de stage) → `review` (sonnet, `pixel-reviewer` : `sprite_inspect`, `tag_list`,
`lint` avec la palette, `anim_audit` par tag, `unity_validate`, `.meta` lu en texte : 16 PPU, Point,
sans mipmap, compression none, conformité au brief et à la palette, défauts IA) → `verdict` (haiku).
Entrées : `issue`, `pr`, `palette`. Sorties : `findings.json`, `review.md`, `verdict.json`.

## art-import

Test Unity d'un asset. `prepare` (haiku) → `import` (sonnet : compile gate C1, `.meta` vérifiés et
corrigés par le MCP Unity si l'importeur ne les applique pas, sprite placé dans une scène de test
`Assets/Tests/Playtest/ArtImport.unity`, animation jouée au moins deux boucles, captures,
console propre) → `report` (haiku). Entrées : `issue`, `pr`, `scene`. Sorties : `import.json`,
`result.json`, `report.md`. Éditeur absent ou MCP muet : `blocked: unity-mcp`. Le verrou
`unity-editor` (C3) est porté par l'étape du flow, pas par le template.

## map-produce

Suit `map-create`. `prepare` (haiku : issue, BIBLE par index, état de départ, branche
`map/<n>-<slug>`) → `graph` (opus, `map-world-design` : `world_graph.json` étendu,
`validate_graph.py` à zéro FAIL avant toute géométrie) → `rooms` (opus, `map-room-design` puis
`ldtk` : un brief par salle, blockout, gameplay, détail, rendu PNG et `room_metrics.py` à chaque
passe, 3 itérations par salle) → `report` (haiku : `room_metrics.py --all --graph`,
`validate_graph.py --ldtk`, `ldtk validate`, rendus monde et salles, commit, push, PR draft). Un
FAIL restant bloque la livraison. Le `.ldtk` n'est modifié que par le CLI du skill `ldtk`. La PR
liste « À câbler dans Unity » (règles U1 à U6 de `unity-import.md`) et rappelle de rouvrir LDtk et de
sauver (Ctrl+S). Entrées : `issue`, `prompt`, `ldtk_file`, `graph_file`. Sorties : `graph.json`,
`rooms.json`, `metrics.txt`, `pr.json`.

## map-review

Trois axes calculés par script, pas déclarés : solvabilité (`validate_graph.py --ldtk`, pas de
softlock, verrous vus avant leur clé), sauts calibrés sur le mouvement du joueur (`room_metrics.py`,
`r1lint.py`, constantes de `map-create/references/constants.md` : saut 6,7 cellules, portée 11,4,
13,2 avec le coyote, double saut 13,3, dash 8, saut mural 9,6 ; ouvertures de porte de 4 à 8
cellules), cohérence BIBLE (règle `04_regle_de_conflit`). Puis les critères de l'issue. Sorties :
`findings.json`, `review.md`, `verdict.json`.

## map-test

`prepare` (haiku : salles touchées, chemins critiques calculés depuis `world_graph.json` en
respectant `requiert`, sondes et commandes du jeu) → `import` (sonnet : compile gate C1, réimport du
`.ldtk`, salles présentes dans la scène, console) → `test` (sonnet : un scénario C2 par chemin
critique dans `Assets/Tests/Playtest/Scenarios/issue-<n>-ca<k>.json`, joué par
`PlaytestBridge.Run`, résultats `.aidp/playtest/results/`) → `report` (haiku : `result.json`,
commit et push des seuls fichiers de scénario). Une sonde ou commande absente du jeu est « non
testable » et fait échouer `passed` si elle couvre un critère. Entrées : `issue`, `pr`, `scene`,
`ldtk_file`, `graph_file`.

## doc-write et doc-review

`doc-write` : `prepare` (haiku : plan de lecture par `00_INDEX`) → `write` (opus : édition de
`.claude/BIBLE/`, `Docs/`, ROADMAP ; `01_canon` gagne, puis le document propriétaire ; une
contradiction est notée dans `99_revue_critique/`, jamais effacée ; section « Questions ouvertes »
conservée) → `report` (haiku : commit, push, PR draft). `doc-review` : `prepare` → `review` (sonnet :
canon, conventions d'identifiants et marquages d'état, chiffres, structure, liens, critères) →
`verdict`. Pas de test Unity.

## Écarts connus

- Le fix après une revue `need-fix` n'a pas de template dédié dans ce lot : le flow relance la
  production (boucle `correction` pour l'art) ou une session de correction.
- `resource: unity-editor` (C3) n'est pas un champ de stage : à poser sur l'étape de flow.
