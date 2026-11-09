# Pipelines de contenu gamedev : art, map, doc

Lot P3 du plan gamedev. Onze templates `version: 5`, joués par le binaire `aidp` en sessions
`claude -p` autonomes, appelés par les flows `game-art`, `game-map`, `game-doc` et leurs flows de test
(plan `PLAN-GAMEDEV.md` §3.1, §4.2). Les pipelines `unity-*` et `issue-refine` sont décrits
ailleurs ; le contrat d'usage du compile gate C1 et des scénarios C2 est dans `unity-verify.md`
(skill `unity-issue-workflow`).

| Route | Produire | Revue | Test | Correction |
|---|---|---|---|---|
| `art` | `art-produce` | `art-review` | `art-import` | `art-fix` |
| `map` | `map-produce` | `map-review` | `map-test` | `map-fix` |
| `doc` | `doc-write` | `doc-review` | aucun (pas d'éditeur Unity) | `doc-fix` |

## Sorties lues par les flows (contrats C4 et C9)

Le dernier stage de chaque pipeline écrit `result.json` (objet plat, champs C4) et recopie ces
valeurs dans les `signals` de son enveloppe. Le daemon expose chaque clé de `result.json` comme
`steps.<id>.outputs.<clé>`, en plus des fichiers déjà exposés (`pr.json`, `verdict.json`,
`findings.json`, `review.md`, `report.md`). Statut `blocked` : raison dans `signals.blocked_reason`.

| Pipeline | Stage | `result.json` (champs) |
|---|---|---|
| `art-produce`, `map-produce`, `doc-write` | `report` | `pr` (numéro), `branch`, `summary` |
| `art-review`, `map-review`, `doc-review` | `verdict` | `verdict` (`done` ou `need-fix`), `findings` (liste de `findings.json`, ou son chemin au-delà de 50) |
| `art-import`, `map-test` | `report` | `passed` (booléen), `report` (+ `pr`, `failed`, `blocked`, et `scenarios`, `not_testable` pour `map-test`) |
| `art-fix`, `map-fix`, `doc-fix` | `fix` | `pr`, `branch`, `summary`, `pushed` |

Fichiers conservés : `pr.json` (`pr`, `branch`, `summary`, `url`, …), `verdict.json` (`fix_needed`,
`blocking`, `next`, …), `findings.json` (`findings`, `fix_needed`, `criteria`), `review.md`
(« ## Revue avocat du diable — verdict : done \| need-fix »), `report.md`. Collision de clé :
`steps.<id>.outputs.pr` est le numéro de `result.json`, le fichier `pr.json` passe sous `pr_file`.

Ids de stage (C5) : `prepare`, `brief`, `generate`, `generate_reference`, `generate_pixellab`, `animate`, `fix`, `import`, `test`, `graph`,
`rooms`, `write`, `review`, `verdict`, `report`. La politique de modèles du daemon (T5) remplace
le modèle écrit dans le template ; les valeurs écrites sont les défauts.

## art-produce

Issu de `pixelart` (conservé). `prepare` (haiku : issue, branche `art/<n>-<slug>`) →
`brief` (sonnet, `pixel-art-director`) → `generate_reference` (opus, `executor`, MCP Aseprite seul :
référence dessinée à la main) → `generate_pixellab` (sonnet, `pixel-artist`, Pixellab depuis cette référence) → `animate`
(opus, `pixel-animator`, passe-plat pour un asset statique) → `verify` (sonnet, `pixel-reviewer`) →
boucle `correction` (`fix` sonnet `pixel-fixer` + `recheck` sonnet, 2 tours) → `report` (haiku :
commit, push, PR draft `Closes #n`).

- Entrées : `issue`, `prompt`, `asset_kind`, `source`, `style_ref`, `view`, `size`, `palette`
  (`rosy-42`), `max_cost` (défaut **10** générations par issue), `feature`.
- Rendu final : c'est toujours celui de Pixellab, même si l'issue prescrit une grille ou un dessin à la main. Aseprite sert à la référence et aux retouches mineures ; `scripts/pixellab_fidelity.py` échoue si `fix` s'en écarte trop.
- Budget Pixellab (C6) : `brief`, `generate_pixellab`, `animate` et `fix` écrivent `pixellab-usage.json`
  (`balanceBefore`, `balanceAfter`, `generations`, `jobs`, `recordedAt`) ; le plafond de 10
  générations, tous stages confondus, est rappelé dans leur policy. Le stage `report` additionne
  les usages dans le corps de PR. Le daemon agrège et applique la réserve ; il n'appelle jamais
  Pixellab.
- Sorties : `pr.json`, `result.json`. La boucle lit `stages.verify.outputs.findings.fix_needed`.

## art-review

Avocat du diable art, lecture seule. `prepare` (haiku : PR, critères, téléchargement des fichiers de
la PR dans le dossier de stage) → `review` (sonnet, `pixel-reviewer` : `sprite_inspect`, `tag_list`,
`lint` avec la palette, `anim_audit` par tag, `unity_validate`, `.meta` lu en texte : 16 PPU, Point,
sans mipmap, compression none, conformité au brief et à la palette, défauts IA) → `verdict` (haiku).
Entrées : `issue`, `pr`, `palette`. Sorties : `findings.json`, `review.md`, `verdict.json`, `result.json`.

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
`rooms.json`, `metrics.txt`, `pr.json`, `result.json`.

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

`doc-write` : `prepare` (haiku : plan de lecture par `00_INDEX`) → `write` (sonnet : édition de
`.claude/BIBLE/`, `Docs/`, ROADMAP ; `01_canon` gagne, puis le document propriétaire ; une
contradiction est notée dans `99_revue_critique/`, jamais effacée ; section « Questions ouvertes »
conservée) → `report` (haiku : commit, push, PR draft). `doc-review` : `prepare` → `review` (sonnet :
canon, conventions d'identifiants et marquages d'état, chiffres, structure, liens, critères) →
`verdict`. Pas de test Unity.

## art-fix, map-fix, doc-fix

Correction d'une PR après une revue `need-fix` (ou un test KO). `prepare` (haiku : PR, branche,
constats ❌/⚠️ de la dernière revue et fils non résolus, tour de correction) → `fix` (sonnet) : commit
sur la branche de la PR, push sans force, réponse sur chaque fil, un commentaire `<route>-fix-summary`.
Aucun Unity ; la PR reste en draft (`ready` et fusion = le flow). Jamais d'assouplissement d'un critère.

- Entrées : `issue`, `pr`, `feature` ; `report_from: review|test` (défaut `review`) pour `art-fix` et
  `map-fix` (`test` = échecs du dernier rapport `art-import` / `map-test`). `doc-fix` : revue seule.
- `art-fix` (agent `pixel-fixer`) : corrige à la main dans Aseprite, re-mesure (`lint`, `anim_audit`,
  `unity_validate`), exporte pour Unity ; Pixellab limité aux appels gratuits et aux nettoyages à
  0,1 génération dans le plafond de 10 ; `pixellab-usage.json` (C6) si Pixellab est appelé.
- `map-fix` : graphe par `map-world-design` (`validate_graph.py` à zéro FAIL), salles par
  `map-room-design` et le CLI `ldtk` (`room_metrics.py`, rendus PNG) ; un FAIL restant bloque le push.
- `doc-fix` : alignement sur `01_canon` puis le document propriétaire, contradiction notée dans
  `99_revue_critique/`, coherence checks de `doc-write`.
- Sortie : `result.json` `{pr, branch, summary, pushed}` ; `fix.json` porte le détail. Aucun constat
  ouvert : `pushed: false`, rien posté.

## Flows : qui appelle quoi

Deux voies (contrat C13). **Voie de dev**, en parallèle : `game-code`, `game-art`, `game-map` tournent en
**worktree** (`workspace` par défaut), sans éditeur Unity. Claim (`aidp:in-progress`) → `git.worktree` →
`git.branch` → produire (`pushes: true`, branche et PR draft poussées) → boucle revue (2 tours :
`aidp:review`, pipeline de revue, `gh.issue_comment` du verdict, correction si `verdict == 'need-fix'`) →
**stop** : `ticket.to_test` (label `aidp:to-test` et phase `to-test` du ticket) → `worktree.remove`, le flow
finit `done`. Les stages de dev ne lancent ni compile gate C1 ni tests C8 (`verification.compile =
"deferred"`, `unity-verify.md` §0.0).

**Voie de test**, une issue à la fois par projet : le dispatcher lance le `test_flow` de la route
(`routing.yaml`) quand la voie est libre (`dispatcher.test_slots`, 1). `game-test-code`, `game-test-art`,
`game-test-map` : `workspace: project`, **pas de worktree**, toutes les étapes tournent dans le checkout principal
du projet (l'éditeur Unity de l'utilisateur y est ouvert). `git.checkout` (`checkout`) : checkout propre
obligatoire, sinon `blocked: dirty-checkout` (label `aidp:blocked`, commentaire d'issue listant les
fichiers, run `escalated`) ; puis `git switch` sur la branche de l'issue. Ensuite : boucle test (2 tours :
`aidp:testing`, test, commentaire, correction avec `report_from: test` si `passed == false`) → `gh.pr_ready`
→ `aidp:awaiting-merge` → `git.restore` (retour sur la base si le checkout est propre, sinon laissé tel quel
et dit dans un commentaire d'issue) → `merge_approval` humain → `gh.merge` → `aidp:done`. Sur `escalated`,
échec ou annulation, le daemon fait le même `git.restore`.

**Verrou** : un run `workspace: project` tient la ressource `unity-editor:<projet>` de sa première
étape (`git.checkout`) jusqu'au retour (`git.restore`, ou fin du run). Un second flow de test reste en
`waiting_external` (`resource:unity-editor`) sur son `git.checkout`. Les étapes n'ont pas de clé
`resource:` ; les stages ne changent jamais de branche. `game-doc` reste en worktree jusqu'au merge (pas d'Unity).

| Voie de dev | Produire | Revue ⇄ correction | Fin | Voie de test (`test_flow`) | Test ⇄ correction |
|---|---|---|---|---|---|
| `game-code` | `unity-implement` | `unity-review` ⇄ `unity-fix` | `to-test` | `game-test-code` | `unity-test` ⇄ `unity-fix` |
| `game-art` | `art-produce` | `art-review` ⇄ `art-fix` | `to-test` | `game-test-art` | `art-headless` ⇄ `art-fix` (sans éditeur, `.meta` créés par `scripts/unity_meta.py` et commités) |
| `game-map` | `map-produce` | `map-review` ⇄ `map-fix` | `to-test` | `game-test-map` | `map-headless` ⇄ `map-fix` (sans éditeur) |
| `game-doc` | `doc-write` | `doc-review` ⇄ `doc-fix` | merge | aucun | aucun |

Boucle épuisée : l'`until` de chaque boucle s'arrête aussi à `settings.max_*_rounds` (une boucle arrêtée par `max` seul escalade le run aussitôt et rien ne s'exécute après), puis label `aidp:blocked` et `fail` avec `kind: business` : le run finit `escalated` (sans `kind`, `failed`). Le dernier tour `need-fix` est corrigé mais pas re-revu : issue bloquée, un humain regarde. Le daemon passe `issue`, `track` et `route` aux pipelines (ticket GitHub) : aucun `with: { issue }` dans les flows. Le verrou (C3) est tenu par le run (`workspace: project`), jamais par le template. Les labels sont
posés par `gh.issue_label`, les rapports par `gh.issue_comment` avec `cost_footer: true`.

## Mémoire et RAG (contrat C10)

Recette : `templates/recipes/memory.md`. Les 15 pipelines `unity-implement`, `unity-review`, `unity-fix`,
`unity-test`, `art-*` (`art-produce`, `art-review`, `art-fix`, `art-import`), `map-*` (`map-produce`,
`map-review`, `map-fix`, `map-test`) et `doc-*` (`doc-write`, `doc-review`, `doc-fix`) la suivent.

- **Lecture** : `prepare` lance `rtk aidp memory context --project "<projectRoot>" --issue GH-<n>
  --route <code|art|map|doc> --stage <stage suivant> --budget 2000` et écrit la sortie telle quelle dans
  `memory-context.md` (sortie du stage). Les stages suivants la reçoivent dans l'entrée `memory`
  (`{{ stages.prepare.outputs.memory-context }}`). Le stage suivant nommé dans `--stage` est : `plan`
  (`unity-implement`), `review` (`*-review`), `fix` (`*-fix`), `test` (`unity-test`), `brief`
  (`art-produce`), `import` (`art-import`, `map-test`), `graph` (`map-produce`), `write` (`doc-write`).
- **À la demande** : plus de lecture complète de la BIBLE ou du code. Index `00_INDEX`, puis
  `rtk aidp rag search "<requête>" --source bible|code|run|... --budget 1500` et lecture des seules lignes citées
  (`path:Lx-Ly`).
- **Écriture** : `verdict` des `*-review` et de `unity-review`, `fix` des `*-fix` et de `unity-fix`,
  `test` de `unity-test`, `report` de `art-import` et de `map-test` écrivent `memory-proposals.json`
  (5 leçons au plus, non évidentes, réutilisables, portée précise, `confidence` honnête ; liste vide
  admise). Le daemon l'ingère à la fin du run ; l'approbation reste humaine (CLI ou front) sauf
  `evidence` >= 2 et `confidence` >= 0,8.
- **Échec** : `memory-context.md` contient « Mémoire indisponible : <cause> », le run continue sans
  mémoire et le rapport le signale. Jamais de `blocked` pour cela.
- **Dépend du binaire** : `aidp memory ...` et `aidp rag ...` (lot P6, Rust) ; tant qu'ils manquent,
  les stages suivent la voie d'échec ci-dessus.
- **Cohabitation avec `knowledge-read` / `knowledge-update`** (fragments inchangés, utilisés par
  `dev-aidp`, `dev-studio`, `knowledge-init`) : la base de connaissance (`<vault>/Knowledge/<repo>/`) garde
  des notes longues par feature (règles, flux, carte du code) ; la mémoire garde des leçons courtes
  (600 caractères) et ciblées par route et chemin. Les deux ne se remplacent pas : `knowledge-read`
  résume une feature avant une découverte, `memory context` rappelle des pièges et décisions précis. Le
  corpus RAG indexe les notes de connaissance (source `knowledge`) : `rag search --source knowledge`
  les retrouve sans les relire en entier. Ne recopie pas une note de connaissance en mémoire.

## Écarts connus

- `resource: unity-editor` (C3) n'est pas un champ de stage : les flows de test `game-test-*` le tiennent pour tout le run (`workspace: project`).

## Bugs levés par un test en échec

Les flows `game-test-code|art|map` (v2) ne bouclent plus sur un correctif. Un test en échec crée une issue bug (labels `bug` et `bug:code|art|map`, titre `fix(GH-n): résumé`, sous-issue du ticket, marqueur `<!-- aidp:bug parent=n base=feat/GH-n -->`). Le ticket repasse `to-test` et attend ce bug (blocage ouvert). Le bug suit `game-bug-code|art|map` : branche `fix/GH-<bug>` créée depuis `feat/GH-<n>`, PR vers `feat/GH-<n>` (jamais `main`), merge automatique quand le verdict de revue est `done` (sinon le bug reste `blocked`, rien n'est mergé). À la fermeture du bug le ticket repart en test. Plafond : 3 bugs par ticket, ensuite le ticket passe `blocked` avec un commentaire. La PR finale vers `main` reste une décision humaine. Patch `routing.yaml` : voir `templates/flows/README.md`.
