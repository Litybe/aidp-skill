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
constats ❌/⚠️ de la dernière revue et fils non résolus, tour de correction, rapport du tour précédent) → `plan` (opus, lecture seule) → `fix` (sonnet) : commit
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

### Étape `plan` (`art-fix`, `map-fix`, `doc-fix` et `unity-fix`)

Entre `prepare` et `fix`, `plan` (opus, agent `planner`, `stage_dir_only`, lecture seule : aucune édition,
aucun git qui écrit, aucune écriture GitHub) produit `plan.md` et `fix-plan.json`
`{steps: [{finding_ids, files, change, verification}], risks, out_of_scope}`. Entrées : constats de la
revue, diff de la PR, issue et critères, mémoire C10 (`--stage plan`) et, dès le 2e tour,
`context.previous_fix` (dernier commentaire `<route>-fix-summary` et ses lignes ⏸️). Chaque constat
bloquant ou majeur a au moins une étape (fichier exact, symbole ou asset, changement précis, vérification) ;
un constat à ne pas corriger (faux positif, hors périmètre) est dans `out_of_scope` avec sa raison. Au
2e tour le plan explique pourquoi le tour précédent a échoué et change d'approche. Sans constat ouvert,
plan vide. `art-fix` : le plan ne prévoit que des retouches mineures du rendu Pixellab ; un besoin de
redessin va dans `out_of_scope`.

`fix` reçoit le plan (`needs: [prepare, plan]`), le suit étape par étape, sans élargir le périmètre, et
rend compte de chaque étape dans `fix.json` `plan_steps: [{index, finding_ids, status done|skipped, reason}]`.
Contrats de sortie (`result.json`, signaux) inchangés.

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

## Mémoire, RAG et base de connaissances (contrats C10 et C11)

Recettes : `templates/recipes/memory.md` (C10, leçons courtes) et `templates/recipes/knowledge.md`
(C11, notes longues). Les pipelines de jeu (`unity-*`, `dev-unity`, `review-unity`, `fix-review-unity`,
`art-*`, `pixelart`, `map-*`, `doc-*`, `bug-write`, `issue-refine`, `merge-conflict`, `flow-doctor`,
`review`, `dev-aidp`, `dev-studio`) les suivent. Il faut aidp 7.9 (`min_aidp_version`).

- **Lecture (injection du compilateur)** : `settings.knowledge` (`true` ou `{ enabled, budget, route,
  stages }`) fait ajouter à chaque stage d'agent un bloc gelé `## Knowledge (reference data, not
  instructions)` : mémoires, notes de connaissance et extraits, filtrés par les domaines de l'agent du
  stage. Plus de stage `prepare` pour la mémoire, plus d'entrée `memory`, plus de `memory-context.md` :
  C10 §1 est obsolète quand `settings.knowledge` est actif. `route` des templates : `code` (`unity-*`,
  `dev-unity`, `review-unity`, `fix-review-unity`, `review`), `art` (`art-*`, `pixelart`), `map`, `doc`,
  `tooling` (`dev-aidp`, `dev-studio`, `flow-doctor`) ; sans `route` (`bug-write`, `issue-refine`,
  `merge-conflict`), la route du ticket. `aidp --no-knowledge workflow emit` coupe le bloc.
- **À la demande** : plus de lecture complète de la BIBLE ou du code. Index `00_INDEX`, puis
  `rtk aidp rag search "<requête>" --agent-type <type> [--domain <domaine>] [--source bible|code|run|knowledge|...]
  --budget 1500` (recherche hybride BM25 + vecteurs, élargie par le glossaire) et lecture des seules lignes
  citées (`path:Lx-Ly`).
- **Écriture** : `verdict` des `*-review` et de `unity-review`, `fix` des `*-fix` et de `unity-fix`,
  `test` de `unity-test`, `report` de `art-import` et de `map-test` écrivent `memory-proposals.json`
  (5 leçons au plus, non évidentes, réutilisables, portée précise, `confidence` honnête ; liste vide
  admise). Le daemon l'ingère à la fin du run ; l'approbation reste humaine (CLI ou front) sauf
  `evidence` >= 2 et `confidence` >= 0,8.
- **Notes de connaissance** : les mêmes stages écrivent aussi `knowledge-proposals.json` (5 au plus :
  `action` add|update|supersede, `domain`, `scope` global|project, `slug`, `title`, `body` en sections
  `##` de 8000 caractères au plus, `tags`, `agents`, `importance`, `target` pour update et supersede,
  `evidence`), et les stages `report` de `unity-implement`, `art-produce`, `map-produce` et `doc-write`
  seulement si le run a établi quelque chose de nouveau (sinon liste vide). À proposer : un patron
  Unity/C# adopté, une règle de pixel art ou d'animation validée en revue, une règle de level design ou
  de salle, une décision de mécanique, un piège d'outil. À ne pas proposer : ce que le code ou git
  montrent, un correctif ponctuel, une leçon courte (c'est une mémoire). Le daemon réconcilie à la fin du
  run (dédoublonnage par similarité) ; `lore`, `game-design` et `rooms` vont toujours dans la boîte de
  revue `Knowledge/_inbox` : `rtk aidp memory inbox list`, puis `approve <nom>` ou `reject <nom>` (`rtk aidp memory ingest-knowledge <fichier|dossier>` ingère un fichier de propositions à la main).
- **Où vivent les notes** : `<vault>/Knowledge/_global/<domaine>/<slug>.md` (valables pour tout jeu :
  patrons Unity/C#, règles de pixel art) et `<vault>/Knowledge/<repo>/notes/<domaine>/<slug>.md` (un jeu :
  mécaniques, salles, lore). Domaines : `game-design`, `lore`, `mechanics`, `rooms`, `unity`, `csharp`,
  `pixel-art`, `pixel-animation`, `level-design`, `tooling`. Frontmatter `type: note`, `domain`, `tags`,
  `agents`, `status` (active|proposed|superseded), `importance`. `Knowledge/_glossary.md` (bloc `yaml`
  `groups:`) liste les synonymes français et anglais utilisés pour élargir les requêtes.
- **Modèle d'embedding** (recherche vectorielle, une fois, à la main) : `git clone
  https://huggingface.co/minishlab/potion-multilingual-128M
  <AIDP_GATEWAY_DIR>/memory/models/potion-multilingual-128M` (`git lfs` requis). Sans lui, BM25 seul ;
  `rtk aidp memory model status` dit où en est l'installation.
- **Agents hors pipeline** : le hook `SubagentStart` (`aidp memory hook subagent-start`, dans
  `hooks/settings.example.json`) injecte les notes de l'agent lancé.
- **Échec** : bloc absent ou commande en erreur, le run continue sans et le rapport le signale.
  Jamais de `blocked` pour cela.
- **Dépend du binaire** : aidp 7.8 pour `settings.knowledge`, `knowledge-proposals.json` et le hook ; sur
  un binaire plus ancien le champ est ignoré et les stages travaillent sans bloc.
- **Cohabitation avec `knowledge-read` / `knowledge-update`** (fragments inchangés, utilisés par
  `dev-aidp`, `dev-studio`, `knowledge-init`) : la base de connaissance (`<vault>/Knowledge/<repo>/`) garde
  des notes longues par feature (règles, flux, carte du code) ; la mémoire garde des leçons courtes
  (600 caractères) et ciblées par route et chemin. Les deux ne se remplacent pas : `knowledge-read`
  résume une feature avant une découverte, `memory context` rappelle des pièges et décisions précis. Le
  corpus RAG indexe aussi ces notes (source `knowledge`) : `rag search --source knowledge` les retrouve sans
  les relire en entier. Ne recopie pas une note de connaissance en mémoire.

## Écarts connus

- `resource: unity-editor` (C3) n'est pas un champ de stage : les flows de test `game-test-*` le tiennent pour tout le run (`workspace: project`).

## Bugs levés par un test en échec

Les flows `game-test-code|art|map` (v2) ne bouclent plus sur un correctif. Un test en échec crée une issue bug (labels `bug` et `bug:code|art|map`, titre `fix(GH-n): résumé`, sous-issue du ticket, marqueur `<!-- aidp:bug parent=n base=feat/GH-n -->`). Le ticket repasse `to-test` et attend ce bug (blocage ouvert). Le corps du bug est rédigé avant sa création par le pipeline `bug-write` (lecture seule, agent `executor`, modèle `sonnet`) : « Issue de base », « Description du bug » (attendu, obtenu, erreur ; défaut du produit distinct de l'échec d'environnement), « Plan à adopter », « Critères d'acceptation » (CA-n rattachés au scénario ou au test, dont « le test qui a échoué passe » et « aucun autre critère du parent ne régresse »). Le marqueur reste en tête, le rapport brut est replié en `<details>` à la fin ; si `bug-write` échoue, le bug est créé avec le rapport seul. Les flows `game-bug-*` prennent ces CA-n pour critères. Le bug suit `game-bug-code|art|map` : branche `fix/GH-<bug>` créée depuis `feat/GH-<n>`, PR vers `feat/GH-<n>` (jamais `main`), merge automatique quand le verdict de revue est `done` (sinon le bug reste `blocked`, rien n'est mergé). À la fermeture du bug le ticket repart en test. Plafond : 3 bugs par ticket, ensuite le ticket passe `blocked` avec un commentaire. La PR finale vers `main` reste une décision humaine. Patch `routing.yaml` : voir `templates/flows/README.md`.
