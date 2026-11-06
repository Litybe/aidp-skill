# Guide utilisateur — ai-dev-pipeline v7

> **Audience : humains.** Ce guide explique comment utiliser la pipeline au quotidien : la lancer,
> répondre aux gates, lire les résultats, choisir le bon template, et l'étendre.
> Pour la procédure exacte suivie par Claude, voir [SKILL.md](SKILL.md) ; pour la référence
> technique complète (contrats de données, schémas), voir [docs/agents-reference.md](docs/agents-reference.md).

---

## Sommaire

1. [Qu'est-ce que c'est ?](#1-quest-ce-que-cest-)
2. [Concepts clés](#2-concepts-clés)
3. [Installation](#3-installation)
4. [Démarrage rapide](#4-démarrage-rapide)
5. [Déroulement d'un run — ce que vous allez voir](#5-déroulement-dun-run--ce-que-vous-allez-voir)
6. [Catalogue des templates](#6-catalogue-des-templates)
7. [Les 4 sous-agents](#7-les-4-sous-agents)
8. [Gates, pauses et reprise](#8-gates-pauses-et-reprise)
9. [Artefacts produits — le vault Obsidian](#9-artefacts-produits--le-vault-obsidian)
10. [Commandes disponibles](#10-commandes-disponibles)
11. [Garde-fous et sécurité](#11-garde-fous-et-sécurité)
11bis. [CI autopilot — réagir tout seul aux events CI](#11bis-ci-autopilot--réagir-tout-seul-aux-events-ci)
12. [Créer ou modifier un template](#12-créer-ou-modifier-un-template)
13. [Benchmark v4 vs v7](#13-benchmark-v4-vs-v7)
14. [Dépannage & FAQ](#14-dépannage--faq)

---

## 1. Qu'est-ce que c'est ?

**ai-dev-pipeline v7** est un orchestrateur de pipelines de développement pour Claude Code. Il
automatise des workflows complets — implémenter un ticket Jira, auditer un service, rédiger une
étude technique, créer des tickets, documenter un microservice — en découpant le travail en
**stages** exécutés par des **sous-agents spécialisés**, avec des **points de validation humaine**
(gates) aux étapes critiques.

Le cœur du système est le binaire Rust **`aidp`** : c'est lui qui décide de tout. Il compile un
template YAML en un **script Workflow JavaScript déterministe** que Claude Code exécute nativement.
Claude n'improvise jamais l'orchestration — il ne fait que lancer quelques commandes `aidp`,
démarrer le Workflow, et vous relayer les questions.

**Ce que ça vous apporte concrètement :**

- Un ticket Jira implémenté de bout en bout (branche → analyse → plan → code → tests → review →
  corrections → PR) avec votre validation aux moments clés.
- Des stages indépendants exécutés **en parallèle** (ex. les 4 dimensions d'un audit).
- Des sorties **validées par schéma JSON** — pas de parsing fragile de texte libre.
- Une **reprise native** après chaque gate : le préfixe déjà exécuté est servi depuis le cache,
  rien n'est recalculé.

---

## 2. Concepts clés

| Terme | Définition |
|---|---|
| **Template** | Un fichier YAML dans `templates/` qui décrit une pipeline : ses inputs, ses stages, ses gates. Ex. `dev`, `audit`, `study`. |
| **Run** | Une exécution d'un template sur une cible donnée. Identifiée par un `run_id` (`YYYYMMDD-HHMMSS-xxxx`). Ses artefacts vivent dans le vault Obsidian, sous `<vault>/Pipelines/<repo>/<feature>/<run_id>/` — tous les runs d'une même feature sont regroupés sous `<feature>`. |
| **Vault** | Le vault Obsidian où atterrit **tout** ce que les pipelines produisent (par défaut `C:/CODE/AIDP`). Voir §9. |
| **Stage** | Une étape de la pipeline, exécutée par un sous-agent. Produit des artefacts déclarés (ex. `plan.md`, `findings.json`). |
| **Sous-agent** | Un des 4 agents génériques (analyzer / planner / executor / reviewer), spécialisé par la liste de `skills` qu'il charge. C'est lui qui fait le vrai travail. |
| **Gate** | Point de validation humaine. Le run se met en pause et Claude vous demande d'approuver ou d'abandonner avant de continuer. |
| **Track** | Niveau de profondeur d'une pipeline dev : `quick` (pas d'étude), `standard` (défaut), `deep` (étude + validation humaine du plan). |
| **Scope** | Périmètre d'écriture autorisé pour un executor (ex. `production` = code applicatif seulement, `tests` = tests seulement). |
| **Workflow** | L'outil natif de Claude Code qui exécute le script JS émis par `aidp`. Gère la parallélisation, la validation par schéma, les tokens et la reprise. |
| **Knowledge graph (Graphify)** | Graphe de connaissance du workspace construit au `run init`. Les stages d'analyse interrogent le graphe au lieu de faire du Grep/Read massif. Non bloquant : sans le CLI `graphify`, la pipeline fonctionne quand même. |
| **Socle de connaissance** | La doc durable d'un service, dans `<vault>/Knowledge/<repo>/`, hors des runs. Deux couches : les **notes transverses** (ce que le service est) et une **note par feature métier** dans `Features/` (comment cette capacité fonctionne). Écrit par les stages `knowledge:`, relu en premier par tous les stages de recherche et de planification. Voir §9. |

---

## 3. Installation

### Prérequis

- Claude Code avec l'outil `Workflow` (natif).
- Rust (`cargo`) pour compiler le binaire `aidp` — installé via https://rustup.rs.
- Les sources d'`aidp`, dans leur propre dépôt :
  `rtk git clone https://github.com/AlexisVuk/ai-dev-pipeline-v7 C:/CODE/Tools/aidp`
  (autre emplacement : variable `AIDP_SRC`). Le skill ne contient que les templates, agents,
  commandes et hooks ; `/pipeline-setup-v7` compile le binaire depuis ce dépôt puis le copie dans
  `~/.aidp/bin/` (le dossier placé sur le PATH). v4 n'est pas nécessaire.

### Mise en place

```
/pipeline-setup-v7   # compile aidp depuis le dépôt aidp, installe les hooks et les commandes, configure le PATH, installe graphify (optionnel)
/pipeline-doctor-v7  # vérifie l'installation (binaire, compatibilité avec le skill, templates, hooks)
```

C'est tout. Pour mettre `aidp` à jour, faites `git pull` dans le dépôt aidp, relancez `/pipeline-setup-v7`,
puis ouvrez un nouveau terminal. `/pipeline-setup-v7` exécute `setup.ps1` / `setup.sh` de ce dossier selon
l'OS ; ces scripts lancent eux-mêmes le `bootstrap` du dépôt aidp. Si `aidp doctor` signale `skill_compat`,
le binaire est plus ancien que le `min_aidp_version` de `SKILL.md` : mettez le dépôt aidp à jour.

> **Note :** Claude positionne automatiquement la variable `AIDP_SKILL_ROOT` sur ce dossier pour
> que les templates v7 soient découverts (et non ceux de v4). Vous n'avez rien à faire — mais si
> vous lancez `aidp` à la main dans un terminal, pensez à la définir :
> `$env:AIDP_SKILL_ROOT = "$HOME\.claude\skills\ai-dev-pipeline-v7"` (PowerShell).

---

## 4. Démarrage rapide

La commande principale est **`/run-pipeline-v7 [template] [cible]`** :

```
/run-pipeline-v7 dev SQIPI-1234          # implémenter un ticket Jira
/run-pipeline-v7 audit src/MyService     # auditer un service
/run-pipeline-v7 study "migration Aurora → DynamoDB"
/run-pipeline-v7 ticket-create docs/prd-fraude.md
/run-pipeline-v7 test-us-e2e SQIPI-1234  # tester une US automatiquement sur dev
```

Pour l'auto-test d'une US sur dev, `test-us-e2e` enchaîne `test-scenarios` (conception
du kit exécutable) puis `run-tests-dev` (déploiement dev optionnel + exécution HTTP /
Mongo / SQS + rapport pass/fail). Prérequis une seule fois : un fichier
`.aidp/dev-target.json` (voir la skill `dev-target-config`) et les CLIs `mongosh`,
`aws`, `gh` sur le PATH — `aidp dev check` vérifie tout.

Les phrases naturelles fonctionnent aussi : *« lance la pipeline v7 dev sur SQIPI-1234 »*,
*« run pipeline v7 audit »*.

Si vous omettez le template ou la cible, Claude vous les demandera (il ne les devine **jamais**).
Il vous demandera aussi la valeur des inputs à choix multiples (ex. le `track`), avec le défaut
recommandé en première option.

---

## 5. Déroulement d'un run — ce que vous allez voir

Voici ce qui se passe, étape par étape, du point de vue utilisateur :

1. **Choix du template** — Claude liste les pipelines disponibles et vous demande de choisir.
2. **Collecte des inputs** — pour chaque input à choix (`enum`), une question vous est posée
   (ex. *track : quick / standard / deep*). Les inputs texte viennent de la cible que vous avez
   donnée (clé Jira, chemin…).
3. **Initialisation** — `aidp run init` crée l'état du run et construit/rafraîchit le graphe de
   connaissance du workspace.
4. **Compilation** — `aidp workflow emit` génère le script `workflow.js` déterministe.
5. **Exécution** — le Workflow tourne en arrière-plan. Vous voyez la progression par stage ;
   les stages indépendants tournent en parallèle. Chaque sous-agent rend une réponse structurée
   validée par schéma.
6. **Plan exécutable** (pipelines `dev` / `dev-lambda-ts`) — quand le planner a écrit son
   `plan.json` (un objet par tâche), le run s'arrête une fois sur `awaiting_plan` : `aidp` relit le
   plan, **génère la fin du workflow** en parallélisant les tâches, puis le run reprend
   automatiquement. Vous ne validez rien à ce moment-là (ce n'est pas un gate) ; Claude peut vous
   montrer l'ordonnancement retenu (`aidp workflow plan-status`).
7. **Gates** — quand un stage gated se termine (ex. le plan en track `deep`, ou la PR), le run se
   met en pause et Claude vous demande : *« Approuver le stage `plan` ? »* → **approve** continue,
   **abort** arrête proprement avec un résumé.
8. **Blocages** — si un sous-agent est bloqué (info manquante, prérequis absent), le run se met en
   pause et Claude vous relaie ses questions. Vous fournissez ce qui manque, puis relancez.
9. **Fin** — au `done`, Claude réconcilie l'état du run (`aidp run reconcile`) et affiche le
   **résumé** : statut de chaque stage, artefacts produits, tokens consommés — dont, pour un stage
   plan-driven, le détail tâche par tâche.

Pendant tout ce temps, **Claude (l'orchestrateur) n'écrit aucun fichier et n'exécute aucune commande
hors `aidp`** : tout le travail réel est fait par les sous-agents du Workflow, chacun dans son
périmètre d'écriture.

---

## 6. Catalogue des templates

### Vue d'ensemble

| id | Cible / inputs clés | À utiliser pour | Gates |
|---|---|---|---|
| `dev` | clés Jira (une ou plusieurs US d'une même feature) + `track` + `stack` (`generic`\|`lambda-ts`, Lot T) | Implémenter un ticket de bout en bout (pipeline phare, **plan-driven** : les tâches du plan — code ET tests — sont parallélisées par `aidp`). `stack` route les skills de `implement` : `generic` (défaut) garde le jeu multi-stack d'aujourd'hui, `lambda-ts` bascule sur le jeu resserré de `dev-lambda-ts.yaml`. | plan (si `deep`), PR |
| `dev-csharp` | **clés Jira OU `prompt`** (+ `feature`, `track`) | Comme `dev` (**plan-driven**), optimisé C#/.NET Betclic — contexte et review **parallélisés**. Accepte une demande sans ticket (§ *Jira ou prompt*). | plan (si `deep`), PR |
| `dev-lambda-tsgit` | **clés Jira OU `prompt`** (+ `feature`, `track`) | Comme `dev-csharp` mais stack AWS Lambda TypeScript Betclic (tests jest). Accepte une demande sans ticket (§ *Jira ou prompt*). | plan (si `deep`), PR |
| `dev-lambda-ts` | clés Jira + `track` | Comme `dev` (**plan-driven**), stack AWS Lambda TypeScript Betclic. | plan (si `deep`), PR |
| `dev-angular` | clés Jira + `feature?` + `track` | Comme `dev` (**plan-driven**), stack Angular v22 Betclic front-end — chaque tâche de `implement` tourne dans son propre worktree git. | plan (si `deep`), PR |
| `dev-local` | `feature_file` (un `.txt` local) + `target_path?` + `track` | Comme `dev` mais 100 % local : pas de Jira, pas de Confluence, pas de git, pas de PR — le run se termine sur un stage `summary`. | plan (si `deep`) |
| `dev-unity` | `issue?` + `prompt?` + `feature?` + `playtest?` | Plan → implémentation → PR draft → test dans l'éditeur Unity (MCP Unity + computer use) → corrections du playtest. Profil perso (`docs/perso-profile.md`). | — |
| `review-unity` | `issue?` + `pr?` + `feature?` | Review Unity de la PR : toute l'issue est-elle faite (CA, tests, actions manuelles, preuves de playtest), puis le code. Commentaires inline si corrections, sinon rapport de vérification complet. | — |
| `fix-review-unity` | `issue?` + `pr?` + `feature?` + `playtest?` + `mark_ready?` | Corrige les commentaires de review ouverts, re-teste dans l'éditeur, passe la PR en ready. `/run-unity-dev-pipeline <issue>` enchaîne les trois. | — |
| `dev-csharp-short` | clés Jira | Démo/test du moteur : Plan (gate) → Code, rien d'autre. Volontairement **non** plan-driven (plan en prose). | plan |
| `dev-model-mix` | clés Jira + `track` | Variante **plan-driven** de `dev` sans étude : `plan` sur opus, `pr` sur haiku. | plan (si `deep`), PR |
| `dev-from-audit` | clés Jira + chemin du rapport d'audit + `track` | **Plan-driven**. Implémenter un ticket en s'appuyant sur un audit antérieur ; les tests sont des tâches du plan. | plan (si `deep`), PR |
| `dev-from-audit-lambda-ts` | clés Jira + chemin du rapport d'audit + `track` | Comme `dev-from-audit` (**plan-driven**), stack AWS Lambda TypeScript Betclic (tests jest). | plan (si `deep`), PR |
| `dev-composed` | clés Jira + `target_path` | Démo de composition : plan → implement (**plan-driven**) → **pipeline `audit` imbriquée** → PR. | PR |
| `dev-csharp-fraud-stack` | comme `dev-csharp` + `service`, `service_repo`, `stack_dir?` | `dev-csharp` avec une porte qualité en plus : le service est recompilé depuis l'arbre du run et la suite de non-régression locale Fraud rejouée entre l'implémentation et la review. | plan (si `deep`), rapport de stack, PR |
| `dev-aidp` | `prompt` + `feature` + `track` | Développe `aidp` lui-même (le workspace Rust, les templates, les schémas, la prose — ce guide inclus). Pas de Jira pour ce dépôt : la demande est toujours en texte libre. | plan (si `deep`), PR |
| `dev-aidp-viewer` | `prompt` + `feature` + `track` | Développe `aidp-viewer` (client React/Tailwind + proxy Express + types partagés) — même famille que `dev-aidp`. | plan (si `deep`), PR |
| `test-csharp` | clés Jira + `feature?` + `track` | Écrit uniquement des tests (xUnit + Reqnroll) pour une fonctionnalité **existante** — pas de stage `code`. | plan (si `deep`), PR |
| `audit` | `target_path` | Auditer un service sur 4 axes (correctness, security, perf, maintainability) **en parallèle**, avec passe adversariale anti-faux-positifs. Composable via `uses:` (double usage, § note plus bas). | rapport |
| `study` | `topic` (+ `scope_paths`) | Étude technique : investigation → synthèse → publication optionnelle. | synthèse |
| `study-to-jira` | `topic` | Étude → tickets Jira : investigue un sujet, décompose la recommandation en stories, puis crée les tickets. | review, création des tickets |
| `tech-doc` | `service_path` + `publish` | Doc technique (architecture événementielle, microservice) → Confluence. | publication (si `publish`) |
| `func-doc` | `feature` (+ clé Jira) | Doc fonctionnelle : user stories, parcours, edge cases. | review finale |
| `discovery` | `brief` | Brainstormer un backlog depuis un PRD ou un brief vague. | idéation |
| `ticket-create` | `source` + `project_key` (+ `parent_epic`) | Découper un epic/PRD en stories Jira et les créer. | décomposition |
| `knowledge-init` | `.` ou un chemin de service | Amorce la base de connaissance d'un service depuis zéro (6 balayages en parallèle) — à lancer une fois, avant tout autre pipeline sur ce service. | write_knowledge |
| `pr-comments` | n° ou URL de PR (auto-détecté sinon) + `track` + `feature?` | Traiter les commentaires de review d'une PR : classifier → planifier → corriger → répondre par thread. | plan, commit & reply |

> Pour corriger seulement quelques threads choisis, sans pipeline : `aidp gh pr-fix <repo> <n> --threads <ids> [--points <ids>] [--note-file -]` lance une session autonome libre via le daemon. Elle corrige, répond sur chaque thread et pousse sur la branche de la PR. `pr-comments` reste la voie pour classifier, planifier et traiter tous les commentaires.
| `gha-fix` | n° de PR (auto-détecté sinon) + `track` + `feature?` | Remettre un build **GitHub Actions** au vert : logs des jobs en échec réduits à l'erreur réelle → classement par cause racine → correction → reproduction locale → push + attente du verdict. Sépare strictement ce que le code peut corriger de ce qu'il ne peut pas (flaky, infra, secret expiré). Déclenché automatiquement par l'autopilot CI (§11bis). | plan, push & watch |
| `sonar-fix` | n° de PR (auto-détecté sinon) + `scope` (`new_code` / `gate_only` / `all_issues`) + `track` + `feature?` | Faire repasser un **quality gate SonarQube** au vert *honnêtement* : gate + issues + hotspots + la *règle* derrière chaque issue → décision par issue → correction et tests → push + relecture du gate. Toute triche (`NOSONAR`, exclusion, seuil abaissé, test sans assertion) est un finding bloquant. Déclenché automatiquement par l'autopilot CI (§11bis). | plan, push & recheck |
| `refacto-pr-lambda-ts` | n° de PR (auto-détecté sinon) + `track` | Refactorer le code **modifié par une PR** sur un service Lambda TS : 3 axes de scan en parallèle → plan → filet de sécurité (caractérisation + Stryker) → refacto plan-driven → double vérification → push sur la branche de travail. | plan, filet (si `deep`), push |
| `fraud-stack-test` | `service?`, `service_repo?`, `scenarios?` | Rejoue la suite de non-régression de la stack locale Fraud contre un microservice réel en Docker (zéro appel externe). Composable via `uses:` (double usage, § note plus bas). | rapport |
| `gdpr-anonymisation-test` | `layers?` (`local`\|`dev`\|`both`) | Teste l'anonymisation RGPD sur deux couches : harnais LocalStack et joueur réel dev/stage2 provisionné → clos → anonymisé. | dev_fixture (avant de toucher un environnement partagé), rapport |
| `cartography-fraud` | `service`, `repo_path`, `runtime?` (`csharp`\|`lambda-ts`) | Cartographie tout ce qu'un microservice Fraud touche hors de son propre processus, plus un brouillon de descripteur pour `localstack/fraud-stack`. Lecture seule sur le dépôt du service. | aucune (relecture des affirmations, pas d'approbation humaine) |
| `datadog-dashboard-fraud` | `action` (`create`\|`update`), `objective`, `dashboard_id?` | Brouillon de dashboard Datadog pour la squad Fraud uniquement, bloqué si le tag `team:fraud` manque. | review_guardrail |

**Fragments (`kind: fragment`, Lot T) — jamais lancés seuls.** Cinq ids du parc n'existent que pour être
composés via `uses:` dans un autre template ; les lancer directement (`run init --pipeline <id>`) produit
un run dont les stages n'ont de sens que branchés à autre chose : `review` (les 4 dimensions de rubrique
en parallèle — le stage `review` du template phare `dev` juste en dessous), `dev-discovery` (le contexte
Jira/prompt ‖ Confluence ‖ code, § *Jira ou prompt* plus bas), `knowledge-read` / `knowledge-update`
(lecture puis mise à jour de la base de
connaissance, §9), et `dev-tests-csharp-split` (la phase de tests C# composable — `tests_unit` ‖
`tests_reqnroll` → `tests_suite` — que `dev-csharp` branche après `implement`). `audit`, `fraud-stack-test`,
`run-tests-dev` et `test-scenarios` sont, eux, à **double usage** : lançables seuls (lignes ci-dessus) ET
composables via `uses:` — ils ne déclarent donc aucune clé `kind:`, le défaut (`pipeline`) suffisant aux
deux usages. Détail complet de chaque id : docs/agents-reference.md §12.

### Le template phare : `dev`

Flux complet (gates en **gras**) :

```
prepare_branch → discover → study* → **plan** → implement → review
                                                     ↘ correction_loop (si findings bloquants, max 2 itérations)
                                                                → **pr**
```

`implement` n'est pas un stage écrit à la main : il est **compilé depuis `plan.json`** (une tâche =
un sous-agent). Les tâches dont les fichiers sont disjoints tournent en parallèle (4 max par défaut) ;
celles qui écriraient le même fichier sont sérialisées par `aidp`. Un sous-agent de merge termine :
fichiers partagés, build, suite de tests, `changed-files.json` consolidé.

- **prepare_branch** — synchronise master et crée `feat/<TICKET>` ; tout le reste atterrit dessus.
- **discover** (analyzer) — lit la demande (ticket Jira **ou** prompt), Confluence et le code (via le
  graphe) → `context.md`.
- **study** (analyzer) — synthèse d'étude ; *sauté en track `quick`*.
- **plan** (planner, opus) — **plan exécutable** → `plan.json` (un objet par tâche : prompt,
  instructions, dépendances réelles, et les fichiers que la tâche écrit) + `plan.md` (la narration
  pour vous : design, risques, rollback) ; **gate humain en track `deep`**.
- **implement** (executor, scope `repo_wide`) — compilé depuis `plan.json` : N sous-agents en
  parallèle + merge. Les tests font partie du plan (`kind: tests`), il n'y a donc plus de stage
  `tests` séparé — et plus d'hypothèse de stack dans le template.
- **review** (reviewer) — audit structuré → `findings.json` + `summary.md`.
- **correction_loop** — si findings bloquants : replan → refix → re-review, 2 itérations max.
- **pr** (executor, scope `stage_dir_only`) — **gate humain**, puis PR + notification Teams.

### Choisir son track

| Track | Étude | Gate sur le plan | Quand |
|---|---|---|---|
| `quick` | non | non | petit fix bien cadré |
| `standard` | oui | non | cas nominal (défaut) |
| `deep` | oui | **oui** | ticket complexe / risqué — vous validez le plan avant toute écriture de code |

> La **PR est toujours gated**, quel que soit le track : aucun push sans votre accord.

### Spécificité `dev-csharp` : la parallélisation

Les lectures de contexte (demande ‖ Confluence ‖ graphe de code) et les 4 dimensions de review
(correctness ‖ security ‖ perf ‖ maintainability) tournent chacune dans un bloc `parallel()` —
c'est du travail en lecture seule, sans collision. Des stages de synthèse (`discover`, `review`)
agrègent ensuite les résultats.

### Jira ou prompt : d'où vient la demande (`dev-csharp`, `dev-lambda-tsgit`)

Ces deux templates prennent leur demande de **deux façons**, et une seule à la fois :

| Mode | Inputs | Ce qui lit la demande |
|---|---|---|
| Jira | `jira_keys: ["SQIPI-1", ...]` | `discover_jira` (skill `analyze-jira-ticket-aidp`) |
| Prompt | `prompt: "<la demande en clair>"` + `feature: "<slug>"` | `discover_prompt` |

`discover_prompt` produit la **même** note d'exigences qu'un ticket aurait donnée — demande reformulée
+ citation verbatim, périmètre et hors-périmètre, critères d'acceptation numérotés, hypothèses
assumées, questions ouvertes, zone de code impactée. Tout ce qui suit (`plan`, `implement`, `review`,
`correction_loop`, `pr`) est **identique** entre les deux modes.

Les deux stages s'excluent par un `when:` qui ne dépend que des inputs : `aidp workflow emit` le
résout à la compilation, donc **le stage inutile n'est jamais dispatché** et ne coûte rien (il
apparaît en `skip ‹stage› (when=false at compile time)` dans le script). En mode prompt, `feature`
est **obligatoire** : sans liste de tickets, rien d'autre ne peut nommer la branche `feat/<feature>`,
le dossier du vault et la PR.

Le même mécanisme vit dans la sous-pipeline réutilisable `dev-discovery`, donc n'importe quel autre
`dev-*` bascule en dual-mode en deux lignes : déclarer `prompt: { required: false, kind: string,
default: "" }` dans ses `inputs:` et le passer au `with:` du stage composite `discover`. Un template
qui ne le fait pas reste en mode Jira — `dev-discovery` neutralise `discover_prompt` à la compilation.

### Revue locale d'une PR : `pr-review` puis `verify-review`

Lancez `pr-review` avec la PR en `pr` (passe 1). Pour la passe 2 ou 3, lancez `verify-review` avec
`pass` et `previous_run` (l'id du run de la passe précédente). Les agents lisent seulement : les
écritures GitHub passent par `aidp gh review-post` (un commentaire inline par finding dans le diff,
les autres dans le corps de la review) et `aidp gh thread-reopen`, appelés par le workflow, jamais
par les templates. La boucle s'arrête quand une passe est propre, ou après la passe 3 avec le statut
`escalated`.

Les relecteurs ne lancent pas les tests : le contrôle des tests est jugé sur la CI de la PR
(`ci-status.json`, écrit par le stage `resolve`). CI verte : `pass` ; CI rouge : `fail` avec un finding ;
CI en cours : `skip`, et le run se met en pause comme pour tout contrôle non évalué. Une PR sans CI
n'a pas de contrôle des tests, et la synthèse l'écrit (« tests not verified: no CI check on this PR »).

### `dev-flow` et `correction-after-test-dev` : toutes stacks

`dev-flow` implémente une demande (clés Jira ou `prompt`) sur n'importe quelle stack : `csharp`, `lambda-ts`, `angular`, `rust` ou `ts-node`. L'input `stack` choisit la phase de tests à la compilation. `aidp project stack <dossier>` détecte la stack ; le pilote vous la propose. Sans `stack`, `aidp run init` prend celle qu'il détecte dans le dépôt ; `unknown` est refusé au démarrage du run. `pr` vaut `draft` (défaut), `ready` ou `none`. La PR contient une section Hypothèses : les choix que le run a faits seul. Avec `branch_ready: false`, une étape prépare d'abord la branche.

`correction-after-test-dev` corrige les bugs d'un rapport de test DEV (`prompt` : le rapport, puis le ticket) sur une branche et une PR qui existent déjà. Il ne crée ni branche ni PR : il pousse sur la branche courante et commente la PR.

### Spécificité `audit` : la passe adversariale

Après les 4 dimensions parallèles, un stage **`verify`** rejoue chaque finding bloquant en
essayant de le **réfuter** ; seuls les survivants restent bloquants. Cela élimine les
faux positifs avant le rapport final (gated).

### Spécificité `refacto-pr-lambda-ts` : le filet avant le code

Deux contraintes structurent ce template, et expliquent son ordre de stages :

1. **Périmètre = le diff de la PR.** `scope_diff` calcule les hunks (`git diff -U0` depuis le
   merge-base) et les mappe vers les symboles englobants — les « zones ». Tout candidat de refacto
   hors de ces zones est refusé par les scans et par le plan. On ne reformate rien hors des hunks :
   ça détruirait le diff du reviewer.
2. **Rien ne bouge sans preuve.** `safety_net` passe **avant** `refactor` : il écrit les tests de
   caractérisation des zones que le plan va toucher, prouve leur sensibilité par mutation Stryker
   scopée (`--mutate`), et rend un verdict par zone. Une zone sous le seuil (`mutation_threshold`,
   60 par défaut) est `blocked` : son task est `skipped`, pas refactoré. Le filet est commité seul,
   et un test de caractérisation qui doit changer pour que le refacto passe **est** la preuve d'un
   changement de comportement → revert du refacto, jamais du test.

Le contrat cardinal est le zéro changement de comportement : `verify_behavior` (opus, charge de la
preuve inversée) et `verify_health` (métriques avant/après) tournent en parallèle, et tout écart part
en **backlog** au lieu d'être corrigé au passage. Le run finit par un push sur la branche de travail
de la PR (jamais de nouvelle branche, jamais de force-push) + un commentaire de synthèse sur la PR.

Les trois skills compagnons portent la méthode : `ts-refactoring-catalog` (24 refactos nommés,
tiers T0/T1/T2, liste des faux refactos), `refactoring-safety-net` (caractérisation + mutation),
`lambda-ts-code-health` (baseline/delta objectifs, `health.json` comparable).

---

## 7. Les 4 sous-agents

Tous sont **génériques** ; c'est la liste de `skills` chargée par le stage qui les spécialise.

| Agent | Rôle | Fait | Ne fait pas |
|---|---|---|---|
| **analyzer** | recherche | Lit code, docs, tickets ; explore ; synthétise. | Écrire du code, créer des tickets, pousser. |
| **planner** | planification | Plans ordonnés et testables ; décompositions epic → stories. | Implémenter le plan. |
| **executor** | production | **Le seul qui change le monde** : code, tests, tickets Jira, pages Confluence, PRs, messages Teams. | Reviewer son propre travail ; écrire hors de son `scope`. |
| **reviewer** | review | Audite un artefact → `findings.json` structuré. | Appliquer les corrections ; gonfler les findings. |

Exemples de spécialisation d'un executor :

- `dotnet-engineering` + `aws-serverless` → développeur .NET/Lambda ;
- `pr` + `git-push` + `writing-clearly-and-concisely` → ouvreur de PR ;
- `create-ticket` + `ticket-decomposition` → rédacteur Jira ;
- `confluence-microservices` + `event-architecture` → publieur Confluence.

---

## 8. Gates, pauses et reprise

### Gates (validation humaine)

À chaque gate, le Workflow rend `awaiting_gate` et Claude vous pose la question. Deux réponses :

- **approve** — l'approbation est **persistée** (`aidp run record-resume`), le script est ré-émis
  et le Workflow reprend là où il s'était arrêté. Le préfixe déjà exécuté est servi depuis le
  cache : rien n'est recalculé, aucun token gaspillé.
- **abort** — le run s'arrête proprement et le résumé s'affiche.

Les approbations sont durables : si le run repasse par plusieurs gates, chaque approbation
précédente reste acquise automatiquement.

Le retour `awaiting_gate` transporte aussi les enveloppes de tous les stages déjà terminés :
Claude les réconcilie (`aidp run reconcile`) avant de vous poser la question, donc le run-state
reste à jour même quand le run s'arrête avant `done`. `reconcile` n'est pas réservé au cas `done` :
les trois arrêts anticipés (`awaiting_gate`, `awaiting_plan`, `paused`) transportent la même clé
`results`, donc un gate atteint tôt dans le run rapporte bien le travail déjà fait et déjà payé en
tokens, jamais 0/N.

### L'arrêt `awaiting_plan` (ce n'est pas un gate)

Sur une pipeline plan-driven (`dev`, `dev-lambda-ts`), le run s'arrête une fois juste après le
planner : la suite du workflow **n'existe pas encore**, puisqu'elle est générée depuis `plan.json`.
Claude relance simplement `aidp workflow emit` — qui valide le graphe de tâches, insère les
dépendances nécessaires pour éviter deux écritures concurrentes du même fichier — puis reprend le
run. Rien à valider de votre côté.

Si `plan.json` est mal formé, la compilation **échoue explicitement** (le message dit quoi corriger) :
il faut refaire tourner le stage `plan`. Personne ne modifie `plan.json` ni `workflow.js` à la main.

### Pauses (sous-agent bloqué)

Si un sous-agent rend `blocked` ou `failed`, ou pose des questions, le run se met en `paused`.
Claude vous relaie les questions et le résumé du blocage. Si la pause porte sur
`implement#T3`, c'est **une tâche du plan** qui a échoué : les autres ont pu réussir, et
`aidp workflow plan-status` vous dit lesquelles. En v7 v1, il n'y a **pas de reprise
automatique en milieu de stage** : fournissez l'information manquante puis relancez la pipeline.

Un signal `signals.malformed_envelope: true` sur la pause n'est pas une vraie coupure réseau
(contrairement à `transport_error`) : c'est une enveloppe rendue par un sous-agent, syntaxiquement
valide mais mal formée (par exemple ses `signals` retrouvés dans le texte de `summary`), détectée
après coup. Le correctif consiste à relire `envelope.summary` et relancer le stage, pas à rejouer
l'appel Workflow.

### Reprendre un run plus tard

```
/pipeline-status-v7           # lister les runs v7 du workspace et leur état
/pipeline-resume-v7 [run_id]  # reprendre un run en pause
```

Les approbations et le `runId` Workflow étant persistés, la reprise survit à une conversation
perdue.

### Runs natifs autonomes

Un run natif porte un drapeau `autonomous`, fixé au lancement. Il est vrai par défaut pour les lancements du workflow ticket, du dispatcher et du CI autopilot ; depuis le viewer, vous choisissez. Dans un run autonome, toutes les gates sont pré-approuvées et les agents ne posent jamais de question : ils prennent l'option recommandée (sinon la plus prudente et réversible) et la consignent dans `assumptions`. Un stage bloqué deux fois échoue avec la raison `blocked-twice`. Relisez les `assumptions` via `GET /api/runs/:id`. Le mode Workflow ne change pas. Voir `docs/native-execution.md`.

### Quel mode pour quel lancement

Tout pipeline lancé par le daemon (viewer, `aidp gateway start --template`, dispatcher et Start des tickets, automations, presets, CI autopilot, étape `pipeline` d'un flow) crée un run natif (`mode: "native"`). Autonome par défaut : dispatcher, CI autopilot, étape `pipeline` d'un flow. Non autonome par défaut : viewer (vous choisissez), presets et automations (`autonomous: true` pour activer). Pour revenir à l'ancien chemin (une session Claude qui pilote `workflow.js`), passez `engine: "workflow"` (alias historique `v7`) sur le lancement, le preset ou l'automation. `/run-pipeline-v7` et `aidp workflow emit` restent en mode Workflow. Sur un ticket, `autopilot.run_id` et `autopilot.session_id` portent l'id du run natif. Voir `docs/native-execution.md`.

---

## 9. Artefacts produits — le vault Obsidian

**C'est le changement de la v7 :** tout ce qu'une pipeline produit est écrit dans un vault Obsidian,
plus dans le dossier `.aidp/` du repo. Les artefacts deviennent des notes liées, cherchables, avec des
propriétés — au lieu de fichiers enfouis dans l'arbre de build.

```
<vault>/                                          C:/CODE/AIDP
└── Pipelines/
    ├── _Pipelines.md                             tableau de bord : tous les repos, 25 derniers runs
    └── fraud-alerts-service/                     nom du repo (remote git `origin`)
        ├── _fraud-alerts-service.md              MOC du repo : toutes ses features
        └── SQIPI-1234/                           la feature
            ├── _SQIPI-1234.md                    MOC de la feature : tous ses runs + la recherche
            ├── explore/                          recherche PARTAGÉE entre les runs
            │   ├── _explore.md                   note générée
            │   └── exploration.md                l'artefact de l'agent
            └── 20260825-091015-29f0/             un run
                ├── _20260825-091015-29f0.md      note générée : tableau des stages, inputs, gates
                ├── run-state.json                état du run
                ├── effective-pipeline.yaml, workflow.js, workflow-result.json
                └── implement/
                    ├── _implement.md             note générée : résumé de l'agent, liens, artefacts
                    └── changed-files.json        l'artefact de l'agent
└── Knowledge/                                    connaissance projet — HORS des runs
    ├── _Knowledge.md                             index : tous les projets documentés
    └── fraud-alerts-service/                     un dossier par projet
        ├── _fraud-alerts-service.md              note générée : l'index des deux couches
        ├── architecture.md                       couche transverse : ce que le service EST
        ├── events.json
        └── Features/                             couche feature : une note par feature métier
            ├── _Features.md                      note générée : le tableau des features
            ├── auto-exclusion-temporaire.md      règles, flux, carte du code, cas limites
            └── limites-de-depot.md
└── TODO/                                         tickets locaux — HORS des runs
    ├── _TODO.md                                  tableau de bord généré
    ├── config.yaml, routing.yaml                 édités à la main
    ├── fraud-alerts-service/                     un dossier par service
    │   └── LOC-1.md                              une note par ticket local
    ├── unrouted/                                 miroirs Jira dont le service n'a pas pu être déduit
    └── .state/                                   compteur + journal des transitions
        └── jira-sync.json                        rapport de la dernière synchro
```

**Amorcer un service** (à faire une fois, avant tout le reste) :

```bash
rtk aidp run init --pipeline knowledge-init --inputs '{"service_path":"."}'
```

ou `/run-pipeline-v7 knowledge-init .`. Six scans en parallèle (structure ‖ événements ‖ données ‖
domaine ‖ exploitation ‖ **features métier**), puis un stage `write_knowledge` **avec gate** qui
fusionne les cinq premiers en notes canoniques (`overview.md`, `architecture.md`,
`events.md`/`events.json`, `data.md`, `domain.md`, `operations.md`), puis `write_features` qui écrit
**une note par feature métier** (un sous-agent par feature, en parallèle), puis `verify` qui confronte
chaque affirmation au code et `correct` qui applique l'audit. Relancer la pipeline plus tard est sans
risque : elle relit les notes et les met à jour.

### Deux couches : le service, et chaque feature métier

`Knowledge/<repo>/` a **deux couches**, et la distinction est le cœur du sujet :

| Couche | Où | Répond à | Lue par |
|---|---|---|---|
| **transverse** | les notes à la racine du dossier | *qu'est-ce que ce service* — architecture, événements in/out, stores, vocabulaire du domaine, exploitation | un agent qui arrive à froid sur le service |
| **feature** | `Features/<slug>.md`, une note par feature métier | *comment cette capacité métier fonctionne ici* — ses règles et ses seuils, son flux, les fichiers qui la portent, ses cas limites et ses invariants | un agent qui va implémenter un ticket **sur cette feature** |

Pourquoi séparer : la note transverse doit rester courte pour être lue en entier, une feature métier
demande l'inverse — chaque règle, chaque seuil, chaque chemin de fichier. Dans un seul `domain.md` ces
deux objectifs s'annulent, et c'est le transverse qui perd : soit il reste vague, soit il devient un
pavé que plus personne ne lit. Séparés, l'agent qui implémente un ticket ouvre **une** note et y trouve
ce qui ressemble le plus à une spec de son travail.

Un stage choisit sa couche : `knowledge: service`, `knowledge: feature`, ou `knowledge: true` (les
deux). Le `stage_dir` d'un stage `feature` **est** `Features/`, donc `scope: stage_dir_only` l'empêche
de réécrire les notes transverses.

### La boucle, câblée dans `dev-*`, `study`, `tech-doc` et `func-doc`

1. **Lecture** — `knowledge-read` est le premier stage de la discovery. Il commence par la **note de la
   feature concernée**, complète avec les notes transverses, résume tout en `knowledge_context.md`, et
   termine par la liste de ce que le socle **ne dit pas** : c'est exactement ce que les lectures Jira /
   Confluence / code doivent aller chercher.
2. **Injection** — tous les stages de recherche et de planification reçoivent en plus, dans leur
   prompt : la liste des notes transverses, la liste des notes de feature **avec leurs noms et leurs
   alias**, et le nom de la note de feature qui correspond à ce run. Consigne : lire ça avant d'ouvrir
   le code.
3. **Mise à jour** — `knowledge-update` est le dernier stage de la discovery, et c'est **deux** stages :
   `knowledge_update` (`knowledge: service`) reverse dans les notes transverses ce que le run a appris
   **du service**, puis `knowledge_feature_update` (`knowledge: feature`) crée ou met à jour la note de
   la feature sur laquelle le run a réellement travaillé. Les deux ne touchent à rien si le run n'a
   rien apporté de neuf.

### Nouvelle feature ou feature existante : `aidp` décide, pas l'agent

C'est le point qui fait ou défait le socle. Un agent à qui on demande en prose de « mettre à jour la
note si la feature existe déjà » finit par produire `auto-exclusion.md`, `autoexclusion.md` et
`auto-exclusion-v2.md` — et un socle dupliqué est pire que pas de socle. La décision est donc calculée :

```bash
rtk aidp knowledge resolve --name "Auto-exclusion temporaire" --name SQIPI-1234
```

Chaque note existante est notée face à chaque requête — nom/alias/slug exact → `1.00`, clé Jira présente
dans le `tickets:` de la note → `0.95`, sinon recouvrement de mots (accents pliés, mots vides ignorés).
Le verdict est `update` (≥ 0.78, avec **le fichier à éditer**), `ambiguous` (≥ 0.42, avec les candidates
à relire), `create` (avec **le chemin exact à écrire**, nommé d'après la feature et jamais d'après un
ticket), ou `supersede` — la note qui matche le mieux est elle-même périmée, son score est donc plafonné
à `0.50` (elle reste une candidate, mais ne peut plus être une cible de mise à jour) et la cible devient
la note nommée par son propre `superseded_by`. Tout stage `knowledge: feature` reçoit ce verdict **déjà calculé** dans son prompt, dérivé des
inputs du run (`feature`, `jira_keys`, `topic`) — l'agent se voit donner le nom de fichier, il ne le
choisit pas.

Un cas est signalé explicitement : si les seules requêtes disponibles étaient des clés Jira, le
résultat porte `weak: true`. « Aucune note ne liste SQIPI-1234 » est vrai de **tout** ticket à son
premier run et ne prouve pas que la feature est neuve : l'agent est alors invité à relancer la
résolution avec le nom métier lu dans le ticket, et à obéir à ce second verdict.

La résolution lit le frontmatter des notes — `aliases:` et `tickets:` sont donc ce qui la rend fiable :

```yaml
---
aidp: knowledge-feature
feature: Auto-exclusion temporaire du joueur
slug: auto-exclusion-temporaire        # identique au nom de fichier
aliases: [self-exclusion, timeout joueur]
area: Responsible gaming
status: active
tickets: [SQIPI-1234, SQIPI-1300]
files: [src/SelfExclusion/SelfExclusionService.cs, src/SelfExclusion/SelfExclusionRepository.cs]
updated: 2026-08-27
tags: [aidp/knowledge-feature]
---
```

Vous pouvez éditer le socle à la main : rien n'y est écrasé (seules les notes `_*.md` sont générées), et
une correction que vous tapez profite à tous les runs suivants. **Compléter les `aliases:` d'une note de
feature est l'édition manuelle la plus rentable** : c'est ce qui empêche un run futur d'en créer un
doublon. Après une édition à la main, `rtk aidp knowledge index` régénère les notes d'index.

Trois règles à retenir :

1. **Les notes préfixées `_` sont générées par `aidp`** et réécrites à chaque appel qui touche le run.
   Ne les édite pas à la main — le contenu serait perdu. Tout le reste est produit par les sous-agents.
2. Les stages de **recherche** (discovery/study — agent `analyzer`, ou un nom
   `discover`/`study`/`explore`/`research`) écrivent **à la racine de la feature**, pas dans le run :
   partagés entre tous les runs. Un run ultérieur sur la même feature relit cette recherche et la
   complète au lieu de la refaire.
3. Le segment `<repo>` vient du remote git `origin`, donc deux checkouts du même repo
   (`.Net/fraud-alerts-service` et `.Net/5448/fraud-alerts-service`) atterrissent au même endroit.

### Où `aidp` trouve le vault

Par ordre de priorité, le premier qui répond gagne :

| # | Source | Comment |
|---|---|---|
| 1 | `--vault <chemin>` | sur `rtk aidp run init` — ponctuel |
| 2 | `AIDP_VAULT` | variable d'env ; `off` / `none` / `0` force l'ancien layout |
| 3 | `~/.aidp/config.json` | `{"vault": "C:/CODE/AIDP"}` — écrit par `rtk aidp vault init` |
| 4 | auto-détection | le dossier contenant un `.obsidian/` le plus proche, en cherchant depuis le repo **et parmi ses voisins** (c'est ainsi que `C:/CODE/AIDP` est trouvé depuis `C:/CODE/Lambda/fraud-actions`) |
| — | rien trouvé | on retombe sur l'ancien `<repo>/.aidp/pipelines/…`, à l'identique |

```bash
rtk aidp vault status --format json-pretty
```

Affiche le vault retenu, **par quelle source**, le segment `<repo>` de ce workspace, le nombre de runs,
et un éventuel `ambiguity` (plusieurs vaults à portée — épingle-en un). Pour créer/épingler :

```bash
rtk aidp vault init --vault C:/CODE/AIDP
```

Et pour régénérer toutes les notes `_*.md` (après une mise à jour d'`aidp`, ou une note supprimée) :

```bash
rtk aidp vault reindex
```

### Ce qui reste dans le repo

**Rien de ce qu'aidp écrit** — pas même l'état qui appartient au repo plutôt qu'à un run précis. Le
marqueur `run-in-flight` et le registre `ci-autopilot.state.json` de l'autopilot CI vivent dans
`<vault>/Pipelines/<repo>/.state/`, préfixé d'un point pour qu'Obsidian comme les générateurs de notes
passent à côté. La copie laissée dans `<repo>/.aidp/` par un binaire plus ancien est déplacée dès le
premier accès, et le dossier disparaît une fois qu'il ne reste plus rien de nous dedans.

Ce qui reste dans le repo, c'est **ce que vous y avez mis** : `.aidp/dev-target.json` et
`.aidp/sonar.json` (config de connexion), `.aidp/ci-autopilot.json` (config autopilot du repo, écrite
uniquement par un `rtk aidp ci config --save` explicite) et `.aidp/pipeline/flow/` (templates locaux au
projet). Ce sont des **entrées**, pas des sorties — aidp les lit, ne les crée jamais. Sans vault, le
run bascule en mode legacy et l'état retombe dans `.aidp/` : il n'a nulle part d'autre où aller. Et
les **runs d'avant la v7** restent où ils sont, sous `.aidp/pipelines/` : rien n'a été migré, et v7
n'a plus de chemin pour les recharger ou les reprendre.

Les artefacts principaux, tous validés par les schémas JSON de `schema/` :

| Artefact | Produit par | Contenu |
|---|---|---|
| `context.md` | analyzer (discover) | Synthèse du contexte (ticket, docs, code). |
| `plan.json` | planner | **Le plan exécutable** : une tâche par objet (prompt, instructions, `needs`, `files`), + `shared_files` réservés au merge. C'est lui que `aidp` compile. |
| `plan.md` | planner | La narration du plan pour un humain (design, risques, rollback). |
| `plan-schedule.json` | `aidp` | L'ordonnancement retenu : vagues, parallélisme, et chaque ordre inséré pour éviter un conflit d'écriture (avec le fichier en cause). |
| `changed-files.json` | executor (code/tests) | Fichiers créés/modifiés/supprimés, nouvelles dépendances, statut build/lint. |
| `findings.json` | reviewer | Findings avec sévérité (`blocking` / `major` / `minor` / `info`), fichier/ligne, suggestion. |
| `options.json` | analyzer (study) | Options comparées : pros/cons, risques, score, recommandation. |
| `audit-report.md` | executor (audit) | Rapport d'audit final (après passe adversariale). |
| `pr.json` | executor (pr) | URL et métadonnées de la PR créée. |

Le **résumé de fin de run** (`rtk aidp run summary`) liste chaque stage avec son statut, ses artefacts
et les tokens consommés.

> **Note :** les dates/durées par stage peuvent être vides dans `run-state.json` — c'est voulu
> (le script Workflow n'a pas d'horloge sandbox). Les tokens, eux, sont comptés par le runtime
> Workflow et repliés dans l'état au `reconcile`.

> **Nouveau (Lot 3) :** `run-state.json` porte aussi `guard_findings` — les passages encadrés par
> le scanner de frontière de stage (§11), un par sous-agent scanné. Rien n'y est supprimé ni
> bloqué : c'est une trace, au même titre que `scope_violations` (§11).

---

## 10. Commandes disponibles

Toutes les commandes sont propres à v7 (suffixe `-v7`) :

| Commande | Usage |
|---|---|
| `/run-pipeline-v7 [template] [cible]` | Lancer une pipeline v7. |
| `/pipeline-status-v7` | Lister les runs v7 du workspace. |
| `/pipeline-resume-v7 [run_id]` | Reprendre un run v7 en pause. |
| `/pipeline-setup-v7` | Installation one-shot : build `aidp` depuis le dépôt aidp, hooks, commandes, PATH, doctor. |
| `/pipeline-doctor-v7` | Diagnostic de l'installation. |
| `/pipeline-new-v7` | Scaffolder un nouveau template v7 par Q&A. |
| `/pipeline-validate-v7 <id\|chemin>` | Valider un YAML contre le schéma. |
| `/agent-new-v7 [nom]` | Scaffolder un nouveau sous-agent. |
| `/ci-autopilot-v7 [status\|run\|ack\|off\|on\|reset]` | Piloter l'autopilot CI (§11bis). |

Le benchmark comparatif entre versions reste `/pipeline-bench` (il nécessite que les versions
comparées soient installées).

### Commandes `aidp` du vault (terminal)

| Commande | Usage |
|---|---|
| `rtk aidp vault status --format json-pretty` | Quel vault est retenu, par quelle source, combien de runs, et le segment `<repo>` de ce workspace. |
| `rtk aidp vault init --vault <chemin>` | Crée le squelette (`Pipelines/`, `Knowledge/`, `.obsidian/`, notes d'index) et épingle le chemin dans `~/.aidp/config.json`. |
| `rtk aidp vault reindex` | Régénère toutes les notes `_*.md` de tous les runs du vault. |
| `rtk aidp status` | Liste les runs de ce repo — ceux du vault **et** les anciens restés dans `.aidp/pipelines/`. |
| `rtk aidp run init … --no-vault` | Exception ponctuelle : garder les artefacts d'un run dans le repo. |
| `rtk aidp knowledge list --format json-pretty` | Le socle du repo courant : notes transverses, et une ligne par note de feature (slug, nom, alias, tickets). |
| `rtk aidp knowledge resolve --name "<feature>"` | Nouvelle feature ou feature existante : `update` + le fichier à éditer, `create` + le chemin à écrire, ou `ambiguous` + les candidates. Répétable (`--name` plusieurs fois), les clés Jira comptent. |
| `rtk aidp knowledge index` | Régénère les notes d'index du socle (`_<repo>.md`, `Features/_Features.md`, `_Knowledge.md`) — à lancer après une édition à la main. |
| `rtk aidp knowledge path` | Les chemins résolus des deux couches. |
| `rtk aidp ticket new --service <repo> --summary "<texte>"` | Crée un ticket local dans `TODO/<service>/<KEY>.md` ; les autres verbes (`list`, `show`, …, `budget`) sont détaillés dans `docs/tickets.md`. |

**Suivi de release.** Une fois un ticket `done` avec une PR mergée, le dispatcher surveille (72 h par
défaut, `jira.release_watch_hours`) l'apparition d'un tag de release contenant le commit de merge.
Pour qu'il écrive ce tag dans Jira (`rtk aidp jira issue-edit`) et passe le ticket en QA Validation,
copiez vous-même ce bloc dans `config.yaml` du vault (proposition, rien n'est écrit pour vous) :

```yaml
jira:
  write_back: { on_release: true }
  status_map: { released: "QA Validation" }
  release_field: "Package name & Build name"
```

Détails dans `docs/tickets.md#release-watch`.

Contrairement à `Pipelines/` et `Knowledge/`, `TODO/` n'est pas créé par `rtk aidp vault init` : c'est la
première commande `rtk aidp ticket` qui le crée à la demande.

Dans un stage, ces commandes n'ont besoin d'aucun flag : `$AIDP_RUN` est exporté par le prompt et
localise le socle du run.

Deux commandes de plus, sans lien avec le vault, mais qui se tapent au même endroit :

| Commande | Usage |
|---|---|
| `rtk aidp findings merge --input <fichier> --input <fichier> ... --out <fichier>` | Fusionne plusieurs `findings.json` d'axes de revue (correctness/sécurité/perf/maintenabilité) en un seul : recalcule les compteurs au lieu de les recopier, déduplique les findings identiques en gardant la sévérité maximale, et sort en erreur — en nommant le fichier fautif — si un axe est absent, illisible, ou ment sur ses propres comptes. |
| `rtk aidp setup agents [--dest <dossier>] [--force]` | Installe les agents restreints (`aidp-analyzer-ro`, `aidp-planner-ro`, `aidp-reviewer-ro`) dans `~/.claude/agents/` — condition d'entrée de `settings.tool_enforcement: strict` (§11). Refuse d'écraser un fichier existant sans `--force` (ce registre est partagé avec vos autres agents). |

Un `findings.json` d'axe déclare désormais aussi ce qu'il a **contrôlé**, pas seulement ce qu'il a
trouvé : un tableau `checks[]` à trois états — `pass`, `fail`, `skip` (ce dernier exigeant un
`harness_gap` nommé). Voir `on_harness_gap` (§12) pour ce qui se passe quand un relecteur déclare
un trou.

### Workflow des tickets : actions et sondes d'attente

Le moteur `rtk aidp flow` enchaîne des actions sur un ticket. Chacune est aussi une commande :
`rtk aidp jira issue-assign <KEY> --me`, `rtk aidp jira issue-transition <KEY> --to-status <statut>`,
`rtk aidp gh copilot-review <repo> <n>`, `rtk aidp gh deployment-approve <run_id>`, `rtk aidp flow ci-watch`,
`rtk aidp flow deploy-dev`, `rtk aidp flow notify-teams`, `rtk aidp flow git-branch <KEY>` et
`rtk aidp flow jira-comment <KEY> --body-file <fichier>`. Elles impriment du JSON ; un refus métier
(Copilot indisponible, approbation refusée, branche distante avec des commits étrangers) sort en code 6.

Un flow peut attendre un événement externe grâce à trois sondes de `wait` :

- `ci.checks` : tous les checks du dernier commit de la PR sont terminés ;
- `copilot.review` : la revue Copilot est arrivée ;
- `pr.reviews` : les revues humaines de la PR sont arrivées.

La configuration du dépôt vit dans `.aidp/flow.json` (workflows CI, projet Sonar, workflow et
environnement de déploiement, `teams.enabled`, `copilot.enabled`, `caps.worktrees`), fusionnée par-dessus la
clé `flow` de `~/.aidp/config.json`. `deploy.dev` et `gh.merge` ne s'exécutent qu'après le clic de la
personne qui valide : le flow s'arrête sur une approbation, jamais de lui-même.

---

## 11. Garde-fous et sécurité

Le système applique une défense en profondeur :

1. **L'orchestrateur ne touche à rien.** Pendant un run, Claude (session principale) n'a pas le
   droit d'éditer des fichiers ni de lancer autre chose que `aidp`. Tout le travail passe par les
   sous-agents.
2. **Scopes d'écriture par stage.** Chaque executor déclare son périmètre : `production` (code
   applicatif, hors tests/docs), `tests` (tests + fixtures), `stage_dir_only` (artefacts hors
   repo : docs, tickets, notifs), `repo_wide` (rare, allowlist explicite), `custom`. Rien ne bloque
   une écriture hors scope pendant que le stage tourne : le contrôle se fait après coup, à la
   réconciliation (voir l'encadré ci-dessous) — le sous-agent doit rester dans son périmètre déclaré,
   pas compter sur un blocage.
3. **Isolation worktree (opt-in).** Un stage peut déclarer `isolation: worktree` pour exécuter son
   sous-agent dans un git worktree isolé — utile uniquement pour des executors qui **écrivent en
   parallèle** (aucun intérêt pour des reviewers en lecture seule).
4. **Gates sur les actions irréversibles.** PR, publication Confluence, création de tickets :
   toujours derrière une validation humaine ou une condition explicite.
5. **Encadrement des passages non fiables (frontière inter-stage).** La sortie d'un sous-agent
   (`summary`, `follow_ups`) devient littéralement une partie du prompt du stage suivant — diff,
   log CI, ticket ou note du vault compris. Un scanner encadre les passages suspects dans un bloc
   `<<<UNTRUSTED_UPSTREAM ...>>> ... <<<END_UNTRUSTED>>>`, accompagné d'une phrase rappelant que
   c'est une **donnée**, jamais une instruction. Rien n'est supprimé et rien n'est bloqué : c'est un
   encadrement, plus une trace — les trouvailles remontent sous `guard_findings` dans le résultat
   du run et sont persistées dans `run-state.json` (§9). Une note du socle de connaissance peut
   s'exclure du scan avec `aidp_guard: off` dans son frontmatter, à réserver à une note qui
   documente légitimement des motifs d'injection (une note « sécurité »). Seules les
   **métadonnées** d'une note sont scannées (nom, alias, tickets, statut, domaine, slug), jamais
   son corps : le corps n'est de toute façon jamais injecté dans un prompt.
6. **Outillage restreint par stage (opt-in).** `settings.tool_enforcement: strict|off`, **défaut
   `off`** — en `off`, rien ne change. En `strict`, les rôles de lecture (`analyzer`, `planner`,
   `reviewer`) sont dispatchés sous un agent spécialisé (`aidp-analyzer-ro`, `aidp-planner-ro`,
   `aidp-reviewer-ro`) portant une allowlist d'outils qui exclut `Edit`, `Write`, `MultiEdit` et
   `NotebookEdit`. L'`executor` n'est **jamais** restreint. Un stage peut écraser la matrice avec
   `tools: { allow: [...], deny: [...] }`. Passer en `strict` exige une préparation explicite :
   `rtk aidp setup agents [--dest <dossier>] [--force]` installe les agents restreints dans
   `~/.claude/agents/` (refuse d'écraser un fichier existant sans `--force` — ce registre est
   partagé avec vos autres agents), et `rtk aidp doctor` gagne un check `agent_toolsets` qui est la
   condition d'entrée : tant qu'il est rouge, `rtk aidp workflow emit` refuse d'émettre en `strict`.
   **Limite honnête, à écrire noir sur blanc :** `Bash` reste dans l'allowlist de lecture seule,
   parce qu'un analyzer en a besoin (`rtk git diff`, `rtk dotnet build`). La restriction empêche donc
   l'usage des **outils d'édition**, pas l'écriture par shell. La vraie borne d'écriture reste la
   vérification de scope a posteriori, `rtk aidp scope verify --run <id>` (point 2 ci-dessus).

> ℹ️ **État actuel : détection après coup, pas de blocage en direct.** Il n'existe qu'un seul chemin
> d'exécution, le Workflow — l'exemple de configuration (`hooks/settings.example.json`) ne livre plus
> aucun hook de garde préventif (le genre qui intercepterait une écriture avant qu'elle n'ait lieu) :
> les deux qui existaient ont été retirés pour de bon, parce que leur condition de déclenchement
> (`AIDP_RUN`/`AIDP_STAGE`) ne pouvait techniquement jamais être vraie — ce sont des lignes de texte de
> prompt, jamais des variables d'environnement de process. Le contrôle de périmètre se fait donc
> **a posteriori**, à la réconciliation : `rtk aidp run reconcile` compare les chemins que git dit que le
> run a réellement modifiés au `scope:` déclaré de chaque stage réussi, et enregistre les
> contrevenants dans `run-state.json` sous `scope_violations` ;
> `rtk aidp scope verify --run <id>` rejoue ce contrôle à la demande et sort en code non nul s'il trouve une
> violation. C'est de la **détection, pas de la prévention** : le fichier hors scope est déjà écrit au
> moment où la violation est observée. Un stage en `isolation: worktree` est vérifié séparément (son
> propre arbre, son propre diff), et tout stage que le vérificateur n'a pas pu atteindre est **nommé**
> dans le rapport plutôt que passé sous silence.

---

### Livraison par flow (`dispatcher.launch`)

Avec `dispatcher.launch: flow` (defaut `session`), le daemon livre un ticket de bout en bout par le flow `ticket-delivery`, ou a la demande via `POST /api/tickets/:key/flow`. Tant que le flow est actif, le ticket ne recoit ni session ni run de l'autopilot CI : la raison de skip `owned-by-flow` est normale. Detail dans `docs/flows.md`.

Pour un ticket local, le flow `local-delivery` enchaine worktree, dev, CI, revue locale et merge humain, sans etape Jira, sans deploiement DEV et sans notification Teams : `POST /api/tickets/:key/flow` avec le corps `{"flow": "local-delivery"}`.

Pour un projet perso sans CI ni Copilot, le flow `perso-delivery` enchaine worktree, `dev-unity` et merge humain, sans bloc CI : `POST /api/tickets/:key/flow` avec le corps `{"flow": "perso-delivery"}`. Le pipeline reprend le workflow du skill `unity-issue-workflow` (implémentation, review GitHub, corrections). Configuration et contraintes Unity : `docs/perso-profile.md`.

## 11bis. CI autopilot — réagir tout seul aux events CI

### Le problème

Claude Code n'a pas de hook « la CI a échoué ». Ses hooks se déclenchent sur **son** cycle de vie
(avant un outil, après un outil, fin de tour…), pas sur celui de GitHub. Donc, par défaut, il faut
venir lui dire « la CI est rouge, corrige ».

`rtk aidp ci` supprime cette étape.

### Comment ça marche

Trois moments où réagir est utile, trois hooks — tous le même binaire, qui lit le JSON du hook sur
stdin et répond en JSON de hook. Aucun quoting PowerShell dans `settings.json`.

| Moment | Hook | Ce qui se passe |
|---|---|---|
| Après un `rtk git push` | `PostToolUse` (Bash), `asyncRewake: true` | Le hook part **en tâche de fond** et surveille les checks jusqu'à 30 min. Dès que ça passe au rouge, il sort en 2 et **réveille la session**. Vous pushez, vous passez à autre chose, Claude revient vers vous avec la panne. |
| Fin de tour | `Stop` | S'il reste un signal non traité, sort en 2 avec la directive : Claude enchaîne au lieu de s'arrêter. |
| Prompt suivant | `UserPromptSubmit` | Cache uniquement (jamais de réseau, votre prompt n'attend rien) ; son stdout devient du contexte. |

Trois signaux, trois pipelines :

| signal | déclencheur | pipeline |
|---|---|---|
| `gha` | checks GitHub Actions en échec sur le head sha de la PR | `gha-fix` |
| `sonar` | quality gate SonarQube rouge, ou issues sur le nouveau code | `sonar-fix` |
| `comments` | threads de review non résolus | `pr-comments` |

Au réveil, Claude invoque la skill **`ci-autopilot`**, qui lit `rtk aidp ci dispatch` et enchaîne les
pipelines **une par une** (elles partagent le même working tree) via le protocole v7 habituel.

Le run est rangé dans le vault sous la clé du ticket Jira de la PR (`feature`), résolue depuis le nom
de branche (`feat/SQIPI-5694` → `SQIPI-5694`), plutôt que sous le numéro de PR ; `target` reste le
numéro de PR. Sans clé de ticket dans le nom de branche, le run garde le numéro de PR comme clé —
le cas normal d'une PR faite à la main.

### Ce qui reste sous votre contrôle

L'autopilot décide **s'il faut démarrer un run**. Il ne décide **jamais s'il faut pusher** : les
stages `push_and_watch` / `push_and_recheck` / `commit_and_reply` restent des gates. Concrètement :
Claude diagnostique, corrige et teste tout seul, puis vous demande avant que quoi que ce soit
n'atteigne GitHub.

### Anti-boucle et anti-collision

Quatre garde-fous, parce qu'un hook qui relance la session est exactement le genre de chose qui part
en boucle :

1. `stop_hook_active` — un hook `Stop` ne se ré-déclenche jamais sur sa propre continuation.
2. `max_notifications` (défaut : 1) — un signal non traité réveille la session **une fois**, puis se
   tait. Il ne réapparaît que si le head sha change (donc si le problème est nouveau).
3. **« notifié » ≠ « traité »** — vous avoir prévenu ne règle rien : `rtk aidp ci dispatch` renvoie encore
   le signal. Seul `rtk aidp ci ack` (ou un stage de push réussi) le retire.
4. `run-in-flight` (dans `<vault>/Pipelines/<repo>/.state/`) — tant qu'un run tourne, l'autopilot
   n'en démarre pas un second sur le même working tree. Un marqueur de plus de 6 h est considéré
   comme abandonné et ignoré, pour qu'un run planté ne le fasse pas taire définitivement.

### Piloter

```bash
rtk aidp ci status --refresh --format json-pretty   # PR, checks, Sonar, threads, signaux dérivés
rtk aidp ci dispatch                                # quelle pipeline, sur quelle cible, avec quels inputs
rtk aidp ci ack --all --note "corrigé à la main"    # faire taire l'état courant
rtk aidp ci config --enable false --save            # couper l'autopilot pour ce repo
rtk aidp ci config --auto-dispatch false --save     # signaler sans jamais démarrer de run
rtk aidp ci reset                                   # tout oublier ; tout ce qui est cassé re-signalera
```

Config : `.aidp/ci-autopilot.json` (par repo) ou `~/.aidp/config.json` → `"ci"`.
État : `.aidp/ci-autopilot.state.json`. Les deux sont dans `.aidp/`, déjà gitignoré.

Réglages utiles dans le fichier de config : `ignored_branches` (défaut `master`/`main`/`develop`),
`ignore_draft_prs` (défaut `true` — une PR en brouillon a le droit d'être rouge),
`watch_timeout_seconds`, `max_notifications`, et le mapping signal → pipeline si vous voulez router
`gha` vers votre propre template.

### Brancher Sonar

Le host et la clé projet se résolvent dans cet ordre : `.aidp/sonar.json` → `SONAR_HOST_URL` /
`SONAR_PROJECT_KEY` → `~/.aidp/config.json` → `sonar-project.properties` (la clé y est déjà dans tous
les repos Fraud). Chez Betclic le host est `https://sonarqube.betclic.net`.

```bash
rtk aidp sonar config --host https://sonarqube.betclic.net --save   # écrit .aidp/sonar.json
export SONAR_TOKEN=...                                          # jamais dans le repo
rtk aidp sonar config                                               # vérifier : has_token doit être true
rtk aidp sonar report --pr 65                                       # gate + issues + hotspots + mesures
```

Sans token, **seul** le signal `sonar` est dégradé : `gha` et `comments` continuent de marcher, et
`rtk aidp ci status` explique pourquoi dans `errors.sonar`.

### Installation

Les hooks sont dans `hooks/ci-events.example.json` et sont installés par `/pipeline-setup-v7`.
Pour les ajouter sans tout réinstaller :

```bash
rtk aidp setup merge-hooks   --example ~/.claude/skills/ai-dev-pipeline-v7/hooks/ci-events.example.json   --target ~/.claude/settings.json
```

Le merge est idempotent (relançable sans doublon) et fait une sauvegarde `.bak`.
`/pipeline-doctor-v7` affiche l'état sous `ci_autopilot_hooks`.

---

## 12. Créer ou modifier un template

Le plus simple : `/pipeline-new-v7` (Q&A interactif — génère directement du `version: 5`).
Validez avec `/pipeline-validate-v7`.

### Anatomie d'un template

```yaml
version: 5
id: mon-pipeline
description: Une ligne qui dit ce que fait la pipeline.
inputs:
  jira_key: { required: true, kind: string }
  track:    { required: true, kind: enum, values: [quick, standard, deep], default: standard }
settings:
  max_correction_iterations: 2      # plafond de la boucle review→fix→re-review
  knowledge_graph: { enabled: true, refresh: lazy, code_only: true }
stages:
  - name: discover                  # id unique du stage
    agent: analyzer                 # analyzer | planner | executor | reviewer
    model: sonnet                   # sonnet | opus | haiku — omis, PAS "modèle de la session" : l'émetteur
                                     # écrit toujours un model: résolu par défaut (opus pour un planner,
                                     # sonnet pour tout le reste, cf. "Nouvelles clés (Lot T)" ci-dessous)
    skills: [graphify-context]      # ← c'est ça qui spécialise l'agent
    inputs: { jira_key: "{{ inputs.jira_key }}" }
    outputs: [context.md]           # artefacts que le sous-agent DOIT produire

  - name: plan
    agent: planner
    needs: [discover]               # dépendances ; stages sans `needs` entre eux → parallel()
    with: { mode: feature }         # paramètres de mode (planner : feature | correction | …)
    gate: "{{ inputs.track == 'deep' }}"   # gate conditionnel (ou `gate: true`)

  - name: code
    agent: executor
    needs: [plan]
    scope: { mode: production }     # périmètre d'écriture
    outputs: [changed-files.json]
    # isolation: worktree           # opt-in, seulement pour mutateurs parallèles
    fan_out:                        # fan-out INTRA-stage : N sous-agents en parallèle + un merge
      from: "{{ stages.plan.signals.shards }}"   # dynamique : le planner découpe (contrat injecté)
      # items: ["shard A", "shard B"]            # OU statique (exactement un des deux)
      max: 4                        # plafond de shards concurrents (excédent replié dans le dernier)
      merge_hint: "Câbler les fichiers partagés (DI, csproj), builder, consolider changed-files.json."

  # Variante plan-driven du même stage : au lieu de shards nommés par le modèle, le stage est
  # COMPILÉ depuis le graphe de tâches du planner (`plan.json`). C'est `aidp` qui décide la
  # parallélisation, à partir du write set (`files`) déclaré par chaque tâche.
  # - name: implement
  #   agent: executor                # rôle/modèle par défaut de chaque tâche (une tâche peut surcharger)
  #   needs: [plan]
  #   scope: { mode: repo_wide }     # les tâches couvrent code de prod ET tests
  #   plan_tasks:
  #     from: "{{ stages.plan.outputs.plan }}"   # l'artefact plan.json d'un stage amont
  #     max: 4                       # plafond de tâches concurrentes (aucune tâche n'est repliée)
  #                                  # en exécution native : min(max, settings.max_parallel) ;
  #                                  # write sets disjoints en parallèle, sinon dans l'ordre du plan ;
  #                                  # chaque tâche est contrôlée sur ses propres `files`
  #     kinds: [code, tests]         # optionnel : ne réclamer qu'une partie des tâches du plan
  #     merge_hint: "Appliquer les fichiers partagés différés, builder, lancer la suite complète."
  #   outputs: [changed-files.json]
  #   # ⚠️ exclusif avec fan_out, interdit dans un `body:` de loop, et impose un aller-retour
  #   #    `awaiting_plan` → `aidp workflow emit` → resume (géré par le skill).

  - name: correction_loop
    type: loop                      # stage composite : boucle de correction
    when: "{{ stages.review.outputs.findings.has_blocking_findings }}"
    max_iterations: "{{ settings.max_correction_iterations }}"
    body: [ ... ]

  # Composition : réutiliser une pipeline entière comme un seul stage
  # - name: qa
  #   type: pipeline
  #   uses: audit
  #   with: { target_path: "{{ inputs.target_path }}" }
  #   outputs: [{ name: report, from: report.audit-report }]
```

### Nouvelles clés (Lot 3)

Toutes optionnelles, toutes calibrées pour laisser le comportement actuel strictement inchangé.

| Clé | Niveau | Défaut | Effet |
|---|---|---|---|
| `settings.budget_floor_tokens` | pipeline | *(absent — aucun plancher)* | Sous ce plancher, un item de `fan_out`/`plan_tasks` n'est plus dispatché : il rend `cancelled`, pas `failed` — il n'a jamais tourné. ⚠️ Le compteur de budget disponible dans le bac à sable ne compte que les tokens de **sortie** et sous-estime le coût facturable d'un facteur mesuré entre 31 et 87 (le contexte d'entrée et le cache pèsent l'essentiel) : un plancher exprimé dans cette unité porte donc sur 1 à 3 % du coût réel. Ce n'est pas une mesure de coût, c'est une heuristique d'arrêt. |
| `settings.on_item_failure` | pipeline | `pause` | En `continue`, un shard ou une tâche de plan en échec n'arrête plus le stage : les items non complétés sont nommément listés au sous-agent de merge, qui tranche. |
| `settings.tool_enforcement` | pipeline | `off` | Voir §11 — restreint l'outillage des rôles de lecture (`analyzer`/`planner`/`reviewer`) quand `strict`. |
| `fan_out.fold` | stage, dans `fan_out:` | `true` | Comportement actuel : la queue d'items excédentaires est repliée dans le dernier shard. À `false`, `fan_out.max` devient un cap de **concurrence** au lieu d'un cap de **découpage** — tout en restant un plafond dur sur le nombre total d'items. |
| `on_harness_gap` | stage | `continue` | Met le run en pause quand un relecteur déclare un trou (un `checks[]` avec `skip` + `harness_gap`, voir §10). C'est la valeur `pause` qui est posée sur le stage de synthèse de `templates/review.yaml`. |
| `tools: { allow: [...], deny: [...] }` | stage | *(absent — matrice par défaut)* | Écrase la matrice d'outillage de `tool_enforcement: strict` pour ce stage précis. |

### Nouvelles clés (Lot T)

Toutes optionnelles ; un template qui n'en déclare aucune garde exactement le comportement d'avant ce lot.

| Clé | Niveau | Défaut | Effet |
|---|---|---|---|
| `kind` | pipeline | `pipeline` | `fragment` marque un template qui n'existe que pour être composé via `uses:` — jamais lancé seul (§6 "Fragments"). Les templates qui ne déclarent rien restent `pipeline`, lançables directement. |
| `policy` | pipeline **et** stage | *(absent)* | Règles impératives injectées dans le prompt du sous-agent, sous le titre "## Règles non négociables (pipeline)" puis "(stage)". Plafonné à 10 règles de 300 caractères par le schéma — de la doctrine, pas de la prose de `description:`. **Piège de composition à connaître** : le `policy:` de NIVEAU PIPELINE d'un template composé via `uses:` n'atteint JAMAIS l'agent — `compose::expand` ne garde que les champs de niveau pipeline du PARENT et jette ceux de l'enfant composé. Un template destiné à être composé (typiquement un `kind: fragment`) doit donc porter ses règles sur le `policy:` de son STAGE, qui lui est bien inliné avec le reste du stage. |
| `description` (sur un stage) | stage | *(absent)* | Prose insérée telle quelle dans le prompt du sous-agent, juste après la ligne "Execute the `<stage>` stage of pipeline `<id>`". Sert aussi de texte à l'`AskUserQuestion` du driver quand un stage doit demander quelque chose à l'utilisateur. |
| `skills_by` | stage | *(absent)* | Route `skills:` selon la valeur d'un input déclaré : `{ input: <nom>, map: { <valeur>: [skill, ...] }, default: [skill, ...] }`. Résolu **à `run init`**, pas à l'émission : `effective-pipeline.yaml` porte directement la liste finale (`skills:` de base puis le paquet choisi, dédupliqués en gardant la première occurrence, ordre préservé) — la clé `skills_by:` elle-même n'existe plus dans le pipeline effectif. À ne pas confondre avec `plan_tasks.skills_by_kind`, qui route par `kind` de tâche de plan et se résout à l'émission, pas à l'init. |

Exemple réel (`templates/dev.yaml`) : le stage `implement` déclare `skills: [graphify-context]` puis
`skills_by: { input: stack, map: { generic: [...], lambda-ts: [...] }, default: [...] }` — un run avec
`--inputs '{"stack":"lambda-ts"}'` reçoit exactement le jeu de skills resserré de `dev-lambda-ts.yaml`,
un run par défaut (`stack` vaut `generic`) reproduit au skill et à l'ordre près le jeu multi-stack
d'avant ce lot.

### Règles de conception utiles

- **Parallélisme** : deux stages sans `needs` entre eux (mais avec le même amont) fusionnent en un
  bloc `parallel()`. Pattern recommandé : fan-out de lecteurs indépendants + un stage de synthèse
  en aval qui garde le nom canonique (voir `dev-csharp.yaml`).
- **Fan-out intra-stage (`fan_out:`)** : un stage seul peut lancer N sous-agents en parallèle, puis
  un sous-agent de merge qui produit l'enveloppe canonique du stage. Deux sources de shards :
  `items:` (liste statique, ex. catégories de tests) ou `from: "{{ stages.<s>.signals.<prop> }}"`
  (dynamique — l'émetteur injecte alors dans le prompt du producteur l'obligation d'émettre ce
  signal comme lots de travail **disjoints en fichiers**). Les shards partagent le working tree :
  chaque shard ne touche que ses fichiers et défère les fichiers partagés (DI, csproj,
  serverless.yml) au merge via `follow_ups`. Source vide → dégradation en 1 seul sous-agent.
  Utilisé par `dev*`/`dev-csharp`/`dev-lambda-ts` sur `code` (dynamique) et `tests` (statique).
- **Expressions** : `when:` et `gate:` acceptent `in`, `==`, `not` / `and` / `or`,
  `>` `<` `>=` `<=`, `default()` sur `inputs` / `stages` / `settings`.
- **`when` ≠ `gate`** : `when` décide si le stage s'exécute (conditionnel) ; `gate` met le run en
  pause pour validation humaine.
- **`isolation: worktree`** : réservez-le aux executors qui écrivent en parallèle ; c'est coûteux
  et inutile en lecture seule.
- **Choix des skills** : un skill déclaré sur un stage doit porter au moins une règle applicable au
  livrable de ce stage. Un skill de procédure sur son propre stage (`git-branch-setup`) est accepté.
  Un test de garde refuse les paires skill/stage de sa liste d'exclusion.
- **Règles de skill vérifiées** : la revue lance `rtk aidp skill-rules check` sur le diff de la branche
  (pas de commentaire `//` hors `///` et `//!`, pas de clé de ticket dans les lignes `.rs` ajoutées).
  Les violations sortent en findings `blocking` sur l'axe `skill_rules`, avec fichier et ligne.
- **`graphify-context` conditionnel** : sans graphe de connaissance pour le run, `rtk aidp workflow emit`
  retire ce skill de chaque stage et affiche un avertissement par stage.

---

## 13. Benchmark v4 vs v7

Les templates v7 gardent les mêmes `id` que v4, ce qui permet un benchmark iso-scénario :

```
rtk aidp bench run --versions v4,v7 --scenarios all --repeats 3
```

Le rapport imprime les deltas `v3 → v4` et `v4 → v7` (durée, tokens, build/tests, score d'audit,
tool calls), plus les KPIs de robustesse propres à v7 : violations de protocole, parse-failures,
exactitude des gates, reproductibilité. Raccourci : `/pipeline-bench`.

Pourquoi v7 est plus robuste que v4, en une table :

| Sujet | v4 | v7 |
|---|---|---|
| Boucle d'orchestration | LLM « dumb driver » à chaque pas | script JS Workflow déterministe |
| Réponse des sous-agents | `reply.md` texte libre parsé (fragile) | validée par schéma JSON |
| Stages indépendants | strictement séquentiels | `parallel()` |
| Capture des tokens | lecture JSONL (course) | comptabilité du runtime Workflow |
| Reprise | re-pilotage manuel | `resumeFromRunId` natif (cache) |
| Isolation des écritures | scope-check réactif | worktree proactif (opt-in) |

---

## 14. Dépannage & FAQ

| Symptôme | Cause probable | Solution |
|---|---|---|
| Les templates v4 apparaissent au lieu des v7 | `AIDP_SKILL_ROOT` absent/incorrect, ou un vieil `aidp` v4 en tête de PATH | Le définir sur ce dossier avant chaque appel `aidp` ; relancer `/pipeline-setup-v7` pour mettre le binaire v7 en tête de PATH. |
| `aidp: command not found` | dossier release absent du PATH | Ouvrir un nouveau terminal, ou relancer `/pipeline-setup-v7`. |
| `workflow emit` : sous-commande inconnue | binaire compilé sans `workflow` | Recompiler via `/pipeline-setup-v7`. |
| Le run cale après approbation d'un gate | reprise mal formée | Vérifier que la reprise passe `resumeFromRunId` + le gate dans `args.approved_gates` ; les approbations antérieures sont persistées. |
| Un stage a écrit hors de son `scope` déclaré | rien ne bloque en direct — l'écriture a déjà eu lieu | Vérifier `aidp scope verify --run <id>` (sort en non-zéro sur violation) ou `scope_violations` dans `run-state.json` après réconciliation ; corriger à la main, aucun hook ne l'aurait empêché (§11). |
| Knowledge graph `skipped` / `failed` | CLI `graphify` absent | Non bloquant. `pip install graphifyy` pour réactiver l'accélération. |
| Dates/durées par stage vides dans le résumé | pas d'horloge dans le sandbox Workflow | Voulu — seuls les tokens et statuts sont garantis. |
| Une tâche de plan est rapportée non exécutée alors qu'elle n'a rien à voir avec l'échec | verrou de fichier (`mutex_after`) confondu avec une vraie dépendance | Vérifier `mutex_after` vs `deps` dans le plan compilé (§9) : une tâche seulement sérialisée par verrou de fichier derrière une tâche en échec est désormais **lancée** (avec l'avertissement « Verrou fichier — prédécesseur en échec » en tête de son prompt), pas annulée. Seule une vraie dépendance déclarée (`needs`) propage l'échec. |
| Des items reviennent `cancelled` | plancher budgétaire atteint | Voir `settings.budget_floor_tokens` (§12) — `cancelled` veut dire « jamais dispatché », pas « a échoué ». Baisser le plancher, ou le retirer. |

**Le résumé affiche 0/N stages alors que le run a fini ?** Le script émis ne réécrit pas l'état du
run lui-même ; il faut la réconciliation (`aidp run reconcile --from workflow-result.json`) avant
`aidp run summary`. Claude le fait automatiquement en fin de run — si un résumé semble faux,
demandez-lui de re-réconcilier.

**Puis-je éditer `workflow.js` à la main ?** Non, jamais. Corrigez le **template** puis ré-émettez
(`aidp workflow emit`). Le script émis est un produit de compilation, pas une source.

**v4 et v7 peuvent-ils cohabiter ?** Oui — chaque version embarque désormais son propre workspace
Rust et son binaire `aidp` (celui de v7 est en tête de PATH et découvre automatiquement les
templates v7). Choisissez le moteur par la commande (`/run-pipeline` vs `/run-pipeline-v7`).
Supprimer v4 n'affecte pas v7.

**Que se passe-t-il si je réponds « abort » à un gate ?** Le run s'arrête proprement et un résumé
de ce qui a été fait s'affiche. Les artefacts déjà produits restent dans le vault, sous `<vault>/Pipelines/<repo>/<feature>/<run_id>/` — la note `_<run_id>.md` montre où le run s'est arrêté.

---

*Fichiers de référence : [SKILL.md](SKILL.md) (procédure de Claude), [AGENTS.md](AGENTS.md), [docs/agents-reference.md](docs/agents-reference.md)
(référence complète : contrats de données, schémas, catalogue détaillé), `templates/` (les
pipelines), `schema/` (les schémas JSON), `agents/` (les 4 sous-agents).*
