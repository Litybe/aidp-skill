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
> cloné dans `C:/CODE/Tools/aidp` ou à l'emplacement donné par `AIDP_SRC`), et les tests de bout en
> bout du dépôt [AlexisVuk/aidp-e2e](https://github.com/AlexisVuk/aidp-e2e). v4/v6 peuvent rester
> installées à côté sans impact.

---

## TL;DR

```
rtk git clone https://github.com/AlexisVuk/ai-dev-pipeline-v7 C:/CODE/Tools/aidp   # une fois : les sources d'aidp
/pipeline-setup-v7                 # build aidp depuis C:/CODE/Tools/aidp + hooks + commandes + PATH
rtk aidp vault init --vault C:/CODE/AIDP   # une fois : épingle le vault (sinon auto-détecté)
/run-pipeline-v7 dev SQIPI-1234    # lance la pipeline v7
```

---

## Où atterrissent les artefacts

```
C:/CODE/AIDP/                                  le vault
└── Pipelines/
    ├── _Pipelines.md                          tableau de bord : tous les repos, runs récents
    └── fraud-alerts-service/                  nom du repo (remote git origin)
        ├── _fraud-alerts-service.md           MOC du repo
        └── SQIPI-1234/
            ├── _SQIPI-1234.md                 MOC de la feature : tous ses runs
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
   - les stages indépendants adjacents → un bloc **`parallel()`** (ex. les 4 dimensions de l'audit) ;
   - la boucle de correction → un **`while`** JS piloté par `signals.has_blocking_findings` ;
   - chaque `gate:` → un retour `awaiting_gate` (pause).
4. **L'outil `Workflow`** exécute le script en arrière-plan, de façon déterministe.
5. **Gates** — sur `awaiting_gate`, l'agent fait `AskUserQuestion`, puis **reprend** le même script
   avec `resumeFromRunId` + `args.approved_gates` (le préfixe déjà exécuté est servi par le cache).
6. **Plan exécutable** (pipelines `dev` / `dev-lambda-ts`) — le planner n'écrit plus une prose à
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

`version: 5`, mêmes `id` que v4 (`dev`, `study`, `audit`, `discovery`, `tech-doc`, `func-doc`,
`ticket-create`) — pratique pour un benchmark iso-scénario. Nouveautés :

- **`audit`** : les 4 dimensions (correctness / security / perf / maintainability) tournent en
  **parallèle**, suivies d'un stage **`verify` adversarial** qui réfute chaque finding bloquant avant
  le rapport.
- **Toutes les pipelines `dev-*` (et `test-csharp`) sont **plan-driven** : le stage d'implémentation
  déclare `plan_tasks: { from: "{{ stages.plan.outputs.plan }}", max: 4 }` et n'a aucun travail propre —
  il est compilé depuis `plan.json`. Le code de production **et** les tests sont des tâches du même plan,
  donc plus de stage `tests` spécifique à une stack.
- **`templates/legacy/`** est l'archive des templates retirés du parc actif — un template n'est jamais
  supprimé, il est déplacé ici tel quel (même `id`, même contenu) le jour où il n'a plus sa place parmi
  les templates découvrables. `aidp` exclut ce dossier de la découverte : invisible dans
  `aidp pipeline list`, mais toujours chargeable par chemin explicite. Voir
  [`templates/legacy/README.md`](templates/legacy/README.md).
- Un stage peut déclarer **`isolation: worktree`** (pour des executors qui écrivent en parallèle sans
  collision). Réservé aux mutateurs parallèles — inutile pour des reviewers en lecture seule.
- Langage d'expression enrichi (`not` / `and` / `or` / `>` `<` `>=` `<=`) pour des gates plus fins.

- **`gha-fix`** et **`sonar-fix`** : les deux pipelines de correction CI. `gha-fix` remet un build
  GitHub Actions au vert (logs des jobs en échec réduits à l'erreur réelle, classement par cause
  racine, séparation stricte de ce que le code peut corriger et de ce qu'il ne peut pas — flaky,
  infra, secret expiré). `sonar-fix` fait repasser un quality gate SonarQube au vert **honnêtement** :
  toute forme de triche (`NOSONAR`, nouvelle exclusion, seuil abaissé, test sans assertion) est un
  finding bloquant, pas un fix. Les deux sont déclenchées automatiquement (voir ci-dessous).

Étendre : `/pipeline-new-v7`.

---

## CI autopilot — les pipelines se lancent toutes seules

Claude Code n'a pas de hook « la CI a échoué » : ses hooks se déclenchent sur *son* cycle de vie, pas
sur celui de GitHub. `aidp ci` fait le pont. Il sonde la PR en cours, empreinte chaque problème pour
qu'il ne se déclenche qu'une fois, et parle lui-même le protocole de hook (JSON sur stdin, JSON sur
stdout, exit 2) — donc `settings.json` ne contient que des one-liners.

| signal | source | pipeline |
|---|---|---|
| `gha` | checks GitHub Actions en échec sur le head sha | `gha-fix` |
| `sonar` | quality gate rouge, ou issues sur le nouveau code | `sonar-fix` |
| `comments` | threads de review non résolus | `pr-comments` |

Trois hooks (`hooks/ci-events.example.json`, installés par `/pipeline-setup-v7`) :

- **`PostToolUse` (Bash), `asyncRewake: true`** — celui qui rend la chose vraiment automatique. Après
  un `git push`, il reste en tâche de fond jusqu'à 30 min à surveiller les checks et **réveille la
  session** dès que ça passe au rouge. Tu pushes, tu continues, Claude revient vers toi avec la panne.
- **`Stop`** — en fin de tour, sort en 2 avec la directive s'il reste un signal, donc le run de
  correction démarre sans que tu tapes quoi que ce soit.
- **`UserPromptSubmit`** — cache uniquement, jamais de réseau ; son stdout devient du contexte, donc
  une session non réveillée sait quand même que la PR a trois commentaires et un gate rouge.

Au réveil, Claude invoque la skill **`ci-autopilot`**, qui lit `aidp ci dispatch` et enchaîne les
pipelines une par une via le protocole v7 normal. **L'autopilot décide s'il faut démarrer un run ;
jamais s'il faut pusher** — chacune de ces pipelines garde son gate sur l'étape qui écrit sur GitHub.

Le run déclenché par la CI est rangé sous la clé du ticket Jira de la PR (`feature`, résolue depuis le
nom de branche) plutôt que sous son numéro de PR ; `target` reste le numéro de PR, donc chaque stage
corrige bien la bonne PR.

Pilotage : `/ci-autopilot-v7`, ou directement

```
rtk aidp ci status --refresh --format json-pretty   # PR, checks, Sonar, threads, signaux
rtk aidp ci ack --all                               # faire taire l'état courant
rtk aidp ci config --enable false --save            # couper pour ce repo
rtk aidp ci config --auto-dispatch false --save     # signaler sans jamais démarrer
```

Sonar a besoin d'un host et d'un token :
`aidp sonar config --host https://sonarqube.betclic.net --save` + `SONAR_TOKEN` dans l'environnement
(jamais dans le repo). Sans eux, seul le signal `sonar` est dégradé — `aidp ci status` en donne la
raison dans `errors.sonar`.

---

## Benchmark v4 vs v7

```
rtk aidp bench run --versions v4,v7 --scenarios all --repeats 3
```

Mêmes scénarios (`benchmark/scenarios/*.yaml`, embarqués dans ce skill). Le rapport imprime les deltas
`v3 → v4` **et** `v4 → v7` (le benchmark croisé nécessite que v4 soit encore installée). KPIs de
robustesse propres à v7 (violations de protocole, parse-failures, exactitude des gates,
reproductibilité) : voir [`benchmark/kpis.md`](benchmark/kpis.md).

---

## Commandes

v7 embarque son **propre jeu de commandes** (dans `commands/`, installées dans `~/.claude/commands/`) :

| Commande | Rôle |
|---|---|
| `/run-pipeline-v7 <template> [target]` | lancer une pipeline |
| `/pipeline-setup-v7` | build `aidp` depuis le dépôt aidp (`AIDP_SRC`) + hooks + PATH + doctor |
| `/pipeline-setup-perso-v7 [vault]` | setup du profil perso (`docs/perso-profile.md`) : sans hooks CI, sans `/ci-autopilot-v7`, sans graphify, autopilot CI coupé |
| `/pipeline-doctor-v7` | health-check de l'installation v7 |
| `/pipeline-status-v7` | lister les runs du workspace courant |
| `/pipeline-resume-v7 [run_id]` | reprendre un run en pause / en gate |
| `/pipeline-validate-v7 [id\|path]` | valider un YAML de pipeline |
| `/pipeline-new-v7 [id]` | scaffolder un nouveau template |
| `/agent-new-v7 [name]` | scaffolder un nouveau sub-agent |
| `/ci-autopilot-v7 [status\|run\|ack\|off\|on\|reset]` | piloter l'autopilot CI |

Et côté vault, en terminal : `aidp vault status` (où ça atterrit et pourquoi), `aidp vault init --vault <chemin>` (créer + épingler), `aidp vault reindex` (régénérer les notes).

## Exit codes

`aidp` returns one of eight codes, defined once in `aidp_core::ExitStatus` and shared by every subcommand:

| Code | Family | Example command |
|---|---|---|
| 0 | Success | any command that completes normally; also `--help` / `--version` |
| 1 | Internal | an unexpected error, an I/O failure, a schema error |
| 2 | HookWake (reserved) | `aidp ci hook post-tool` / `aidp ci hook stop` waking a Claude Code session; stdout carries `hookSpecificOutput` |
| 3 | NotFound | `aidp validate nope`, `aidp run state --run nope`, `aidp ticket show NOPE-9`, `aidp scope check --stage nosuch` |
| 4 | PolicyRefusal | `aidp scope check` on a path outside scope, `aidp knowledge supersede --slug ../evil --by x`, a vault leak caught by `aidp scope verify` / `aidp run reconcile` |
| 5 | UpstreamFailure | a Jira, GitHub, or gateway upstream error |
| 6 | NegativeVerdict | `aidp doctor` red, `aidp cost anomaly` flags an outlier, `aidp scope verify` finds violations, `aidp dev check --strict` fails |
| 7 | Usage | any CLI parse fault, e.g. `aidp ci hook stop --workspace-rooot x`, `aidp findings merge --out f` with no `--input`, a missing required config variable |

`aidp mongo` and `aidp sqs` propagate their child process's exit code unchanged — they fall outside this table. `aidp run reconcile` still exits 0 even when it records scope violations; that is a kept decision, not an oversight.

`aidp --help` refers back to this table by name.

## Pour aller plus loin

- [`USER-GUIDE.md`](USER-GUIDE.md) — **guide utilisateur complet** (démarrage, catalogue des
  templates, gates, artefacts, personnalisation, dépannage).
- [`SKILL.md`](SKILL.md) — la procédure exacte pour Claude.
- Le binaire `aidp` et ses schémas vivent dans le dépôt aidp
  ([AlexisVuk/ai-dev-pipeline-v7](https://github.com/AlexisVuk/ai-dev-pipeline-v7)) ; le harnais de
  benchmark et les tests de bout en bout dans [AlexisVuk/aidp-e2e](https://github.com/AlexisVuk/aidp-e2e).
- `SKILL.md` déclare `min_aidp_version` : `aidp doctor` (check `skill_compat`) signale un binaire trop
  ancien pour ce skill.
