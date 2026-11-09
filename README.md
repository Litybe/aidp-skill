# ai-dev-pipeline v7 — moteur natif Workflow, sorties dans Obsidian

Même mental model que v4 — **`aidp` (binaire Rust) est la source de vérité, l'agent n'improvise pas** —
mais la boucle d'orchestration n'est plus pilotée par un LLM « dumb driver ». À la place, `aidp`
**compile la pipeline en un script JavaScript Workflow** déterministe que l'outil natif `Workflow`
de Claude Code exécute.

**Ce que la v7 ajoute à la v6 :** tout ce qu'une pipeline produit est écrit dans un **vault Obsidian**
(`<vault>/Pipelines/<repo>/<feature>/<run_id>/`) au lieu du dossier `.aidp/` du repo, et `aidp` y
maintient un jeu de **notes d'index générées** (`_*.md`) qui relient runs, stages, features et repos.
Les artefacts deviennent une base de connaissance navigable ; le repo reste propre.

> Ce dépôt ne contient que le **skill** : templates, agents, commandes, hooks et docs de pilotage.
> Le binaire `aidp` vient du **dépôt aidp** ([AlexisVuk/ai-dev-pipeline-v7](https://github.com/AlexisVuk/ai-dev-pipeline-v7),
> dans `D:\AIDP\src\aidp` ou à l'emplacement donné par `AIDP_SRC`), et les tests de bout en
> bout du dépôt [AlexisVuk/aidp-e2e](https://github.com/AlexisVuk/aidp-e2e). v4/v6 peuvent rester
> installées à côté sans impact.

---

## TL;DR

```
powershell -NoProfile -ExecutionPolicy Bypass -File D:\AIDP\skill\setup-gamedev.ps1 -Project D:\CLAUDE_UNITY\<projet>
                                   # variables, hook Stop, config, agents et commandes du projet, doctor
/run-unity-dev-pipeline 42         # dans le projet Unity : dev-unity, review-unity, fix-review-unity sur l'issue #42
/run-pipeline-v7 pixelart 43       # ou une pipeline au choix
```

---

## Profil gamedev

Ce skill est réduit au développement de jeu Unity en solo.

| Sujet | Profil gamedev |
|---|---|
| Outils | Unity (+ MCP Unity), Aseprite (MCP), Pixellab (MCP), GitHub (issues, PR) via `gh`, `aidp`, graphify (graphe de connaissance) |
| Absents | Jira, Confluence, Sonar, GitHub Actions et toute CI, Teams, Mongo, SQS, Datadog, déploiements, Codex, Copilot |
| Templates | `dev-unity`, `review-unity`, `fix-review-unity` (code Unity, session Desktop), `unity-implement`, `unity-review`, `unity-fix`, `unity-test` (route `code` du flow `game-code`, runs autonomes du daemon), `pixelart` (assets), `dev-aidp` (aidp lui-même), `dev-studio` (front `aidp-studio`), `knowledge-init` / `knowledge-read` / `knowledge-update` (base de connaissance), le fragment `review`, `dev-exemple` (démo) |
| Templates | `dev-unity`, `review-unity`, `fix-review-unity` (code Unity), `pixelart` (assets), `issue-refine` (affine une issue sans critères `CA-n`), `dev-aidp` (aidp lui-même), `dev-studio` (front `aidp-studio`), `knowledge-init` / `knowledge-read` / `knowledge-update` (base de connaissance), le fragment `review`, `dev-exemple` (démo) |
| Flow | `perso-delivery` (issue → PR mergée par toi) |
| Disque | **rien sur C:**. Skill `D:\AIDP\skill`, binaire `D:\AIDP\bin`, sources `D:\AIDP\src`, vault `D:\AIDP\Vault`, état du daemon `D:\AIDP\gateway`, agents et commandes dans `<projet>\.claude\`. Seuls `~/.claude/settings.json` (hook Stop) et `~/.aidp/config.json` (vault, CI coupée) restent sur C:, parce que Claude Code et aidp ne les lisent que là. |
| Installation | `setup-gamedev.ps1` (`/pipeline-setup-gamedev-v7`) : ne compile ni n'installe rien, voir l'en-tête du script |

Les skills et agents Unity et pixel art (`unity-*`, `pixel-*`, `pixellab`, `map-*`, `ldtk`) et les
serveurs MCP ne font pas partie de ce dépôt.

---

## Où atterrissent les artefacts

```
D:/AIDP/Vault/                                 le vault
└── Pipelines/
    ├── _Pipelines.md                          tableau de bord : tous les repos, runs récents
    └── pixelhood/                             nom du repo (remote git origin)
        ├── _pixelhood.md                      MOC du repo
        └── issue-42/
            ├── _issue-42.md                   MOC de la feature : tous ses runs
            ├── explore/                        recherche partagée entre les runs de la feature
            └── 20260825-091015-29f0/          un run
                ├── _20260825-091015-29f0.md   note du run : stages, inputs, gates, follow-ups
                └── implement/
                    ├── _implement.md          note du stage : résumé de l'agent, liens, artefacts
                    └── changed-files.json     l'artefact
```

Résolution du vault, premier qui répond : `--vault` → `AIDP_VAULT` (`off` désactive) →
`~/.aidp/config.json` → auto-détection (le dossier contenant un `.obsidian/` le plus proche, voisins
compris). Rien trouvé ⇒ ancien layout `.aidp/pipelines/`, inchangé.

Les notes préfixées `_` sont **générées** et réécrites à chaque run — ne pas les éditer.
`aidp vault status` dit où ça atterrit et pourquoi ; `aidp vault reindex` régénère tout.
Les runs d'avant la v7 restent dans `.aidp/pipelines/` et restent lisibles/resumables.

---

## Comment ça marche

1. **Choix du template + inputs** — comme v4 (`aidp pipeline list`, `AskUserQuestion`).
2. **`aidp run init`** — initialise le run (même mécanique que v4 : état, graphe Graphify, scopes).
3. **`aidp workflow emit --run <id>`** — génère `workflow.js` :
   - chaque stage → `agent(prompt, { schema, model, isolation })` → **sortie structurée
     validée par schéma** (plus de parsing `reply.md` en texte libre) ;
   - les stages indépendants adjacents → un bloc **`parallel()`** (ex. les 4 dimensions de la revue) ;
   - la boucle de correction → un **`while`** JS piloté par `signals.has_blocking_findings` ;
   - chaque `gate:` → un retour `awaiting_gate` (pause).
4. **L'outil `Workflow`** exécute le script en arrière-plan, de façon déterministe.
5. **Gates** — sur `awaiting_gate`, l'agent fait `AskUserQuestion`, puis **reprend** le même script
   avec `resumeFromRunId` + `args.approved_gates` (le préfixe déjà exécuté est servi par le cache).
6. **Plan exécutable** (pipelines `dev-aidp` / `dev-studio`) — le planner n'écrit plus une prose à
   interpréter mais **`plan.json` : un objet par tâche à réaliser** (son prompt, ses `needs`, et surtout
   ses `files` = les fichiers qu'elle écrit). `aidp` relit ce graphe et **génère la fin du workflow** :
   un sub-agent par tâche, en parallèle quand les fichiers sont disjoints, **sérialisé automatiquement**
   quand deux tâches écriraient le même fichier, puis un sub-agent de merge pour les fichiers partagés
   et le build. C'est donc `aidp` — pas le modèle — qui décide de la parallélisation. Conséquence : le
   script s'arrête une fois sur `awaiting_plan`, on relance `aidp workflow emit`, et on reprend
   (`resumeFromRunId`). Voir `aidp workflow plan-status --run <id>` pour visualiser l'ordonnancement.

---

## Pourquoi c'est plus robuste que v4

| Sujet | v4 | v7 |
|---|---|---|
| Boucle d'orchestration | LLM « dumb driver » appelle `orchestrate next` à chaque pas | script JS Workflow déterministe |
| Réponse du sub-agent | `reply.md` texte libre → `aidp reply parse` (fragile) | `agent({schema})` validé par schéma |
| Capture des tokens | le driver passe `--last-tokens` depuis le JSONL (course) | comptabilité du runtime Workflow |
| Stages indépendants | strictement séquentiels | `parallel()` |
| Isolation des écritures executor | scope-check PostToolUse réactif | `isolation: 'worktree'` proactif (opt-in) |
| Reprise | re-drive manuel | `resumeFromRunId` natif (préfixe en cache) |
| Plan | `plan.md` en prose, relu par l'agent suivant | `plan.json` (graphe de tâches) → `aidp` compile la fin du workflow |
| Découpage du travail | une liste d'étiquettes produite par le modèle | write set par tâche : `aidp` parallélise et sérialise les conflits |
| Emplacement des artefacts | `<repo>/.aidp/pipelines/…` | `<vault>/Pipelines/<repo>/<feature>/<run_id>/` + notes Obsidian générées |

Toutes les fragilités v4 liées au pilotage LLM **disparaissent par construction**. (Détail des
fragilités d'origine : voir le plan de conception.)

---

## Templates

`version: 5`. Les templates du profil gamedev :

| Template | Rôle |
|---|---|
| `dev-unity` | implémente une issue GitHub dans le projet Unity, ouvre la PR en draft, playtest dans l'éditeur, boucle de correction |
| `review-unity` | revue Unity de toute l'issue sur la PR (une review GitHub) |
| `issue-refine` | réécrit le corps d'une issue `aidp:triage` (skill `github-issue-ticket`, critères `CA-n`), puis remet `aidp:ready` |
| `fix-review-unity` | corrige les commentaires de review, rejoue le playtest, passe la PR en ready |
| `unity-implement` | route code : `prepare` → `plan` → `implement` (EditMode + compile gate C1) → `report`, PR draft `Closes #n` ; `track: bug` ajoute `repro` (test rouge d'abord). Sans playtest |
| `unity-review` | revue « avocat du diable » critère par critère (`CA-n`, une preuve chacun), lecture seule, sans Unity ; verdict `done` / `need-fix` |
| `unity-fix` | corrige les points ❌/⚠️ de la revue (`report_from: review`) ou les scénarios KO (`report_from: test`), compile gate C1, push, réponse sur chaque fil |
| `unity-test` | compile gate C1, EditMode + PlayMode, un scénario PlaytestDriver par `CA-n`, preuves dans la PR, `passed` ; `needs-feel-check` → `blocked: feel-check` |
| `pixelart` | brief, génération Pixellab, animation, revue notée, retouche, export Unity |
| `art-produce`, `art-review`, `art-import`, `art-headless` | route art : production (brief, Pixellab 10 générations max, animation, correction, PR draft), revue avocat du diable, test sans éditeur (`art-headless`, utilisé par `game-test-art`) ; `art-import` : ancien test éditeur |
| `map-produce`, `map-review`, `map-test`, `map-headless` | route map : graphe validé, salles LDtk, métriques et rendus, PR draft ; revue (solvabilité, sauts, BIBLE) ; test sans éditeur (`map-headless`, utilisé par `game-test-map`) ; `map-test` : ancien test d'import et de traversée en Unity |
| `art-fix`, `map-fix`, `doc-fix` | corrigent la PR après une revue (`report_from: review`) ou un test (`test`, art et map), push, `result.json` `{pr, branch, summary, pushed}` |
| `doc-write`, `doc-review` | route doc : BIBLE et `Docs/` cohérents avec le canon, revue (détail : `docs/gamedev-content-pipelines.md`) |
| `dev-aidp` | fait évoluer `aidp` lui-même (workspace Rust, règles de son `AGENTS.md`) |
| `dev-studio` | fait évoluer `aidp-studio`, le front du daemon (Vite, React, TypeScript strict) |
| `knowledge-init` | construit la base de connaissance d'un projet dans le vault |
| `knowledge-read`, `knowledge-update`, `review` | fragments composés par `dev-aidp` et `dev-studio` |
| `dev-exemple` | démo minimale sans skill |

- **`dev-aidp` et `dev-studio` sont plan-driven** : le stage d'implémentation déclare
  `plan_tasks: { from: "{{ stages.plan.outputs.plan }}", max: 5 }` et n'a aucun travail propre — il est
  compilé depuis `plan.json`. Le code de production **et** les tests sont des tâches du même plan.
- Un stage peut déclarer **`isolation: worktree`** (pour des executors qui écrivent en parallèle sans
  collision). Réservé aux mutateurs parallèles — inutile pour des reviewers en lecture seule.
- Langage d'expression enrichi (`not` / `and` / `or` / `>` `<` `>=` `<=`) pour des gates plus fins.

Étendre : `/pipeline-new-v7`.

---

## Mémoire et RAG

Les pipelines `unity-*`, `art-*`, `map-*` et `doc-*` utilisent le gestionnaire de mémoire et le RAG
du binaire (`aidp memory ...`, `aidp rag ...`, contrat C10) :

- `prepare` lit les mémoires actives pertinentes (`memory-context.md`, 2000 tokens au plus) et les passe
  aux stages suivants ; la BIBLE et le code se cherchent par `aidp rag search`, plus par lecture complète ;
- les derniers stages de revue, correction et test écrivent `memory-proposals.json` (5 leçons au plus) ;
  le daemon les ingère, l'humain approuve ;
- si les commandes échouent, le run continue sans mémoire et le signale ;
- `knowledge-read` / `knowledge-update` restent (notes longues par feature) ; la mémoire porte les leçons
  courtes et ciblées.

Recette : `templates/recipes/memory.md`. Détail : `docs/gamedev-content-pipelines.md`.

---

## Commandes

v7 embarque son **propre jeu de commandes** (dans `commands/`, installées par `setup-gamedev.ps1` dans
`<projet>\.claude\commands\`) :

| Commande | Rôle |
|---|---|
| `/run-pipeline-v7 <template> [target]` | lancer une pipeline |
| `/run-unity-dev-pipeline <issue>` | enchaîner `dev-unity`, `review-unity` et `fix-review-unity` sur une issue |
| `/run-pixelart-pipeline <issue>` | lancer `pixelart` sur une issue d'asset |
| `/pipeline-setup-gamedev-v7 [projet] [vault]` | setup du profil gamedev (`setup-gamedev.ps1`) |
| `/pipeline-doctor-v7` | health-check de l'installation v7 |
| `/pipeline-status-v7` | lister les runs du workspace courant |
| `/pipeline-resume-v7 [run_id]` | reprendre un run en pause / en gate |
| `/pipeline-validate-v7 [id\|path]` | valider un YAML de pipeline |
| `/pipeline-new-v7 [id]` | scaffolder un nouveau template |
| `/agent-new-v7 [name]` | scaffolder un nouveau sub-agent |

Et côté vault, en terminal : `aidp vault status` (où ça atterrit et pourquoi), `aidp vault init --vault <chemin>` (créer + épingler), `aidp vault reindex` (régénérer les notes).

## Exit codes

`aidp` returns one of eight codes, defined once in `aidp_core::ExitStatus` and shared by every subcommand:

| Code | Family | Example command |
|---|---|---|
| 0 | Success | any command that completes normally; also `--help` / `--version` |
| 1 | Internal | an unexpected error, an I/O failure, a schema error |
| 2 | HookWake (reserved) | a hook command waking a Claude Code session; stdout carries `hookSpecificOutput` |
| 3 | NotFound | `aidp validate nope`, `aidp run state --run nope`, `aidp ticket show NOPE-9`, `aidp scope check --stage nosuch` |
| 4 | PolicyRefusal | `aidp scope check` on a path outside scope, `aidp knowledge supersede --slug ../evil --by x`, a vault leak caught by `aidp scope verify` / `aidp run reconcile` |
| 5 | UpstreamFailure | a GitHub or gateway upstream error |
| 6 | NegativeVerdict | `aidp doctor` red, `aidp cost anomaly` flags an outlier, `aidp scope verify` finds violations, `aidp dev check --strict` fails |
| 7 | Usage | any CLI parse fault, e.g. `aidp validate --workspace-rooot x`, `aidp findings merge --out f` with no `--input`, a missing required config variable |

`aidp run reconcile` still exits 0 even when it records scope violations; that is a kept decision, not an oversight.

`aidp --help` refers back to this table by name.

## Pour aller plus loin

- [`USER-GUIDE.md`](USER-GUIDE.md) — **guide utilisateur complet** (démarrage, catalogue des
  templates, gates, artefacts, personnalisation, dépannage).
- [`SKILL.md`](SKILL.md) — la procédure exacte pour Claude.
- Le binaire `aidp` et ses schémas vivent dans le dépôt aidp
  ([AlexisVuk/ai-dev-pipeline-v7](https://github.com/AlexisVuk/ai-dev-pipeline-v7)) ; les tests de
  bout en bout dans [AlexisVuk/aidp-e2e](https://github.com/AlexisVuk/aidp-e2e).
- `SKILL.md` déclare `min_aidp_version` : `aidp doctor` (check `skill_compat`) signale un binaire trop
  ancien pour ce skill.
