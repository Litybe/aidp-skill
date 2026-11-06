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
12. [Créer ou modifier un template](#12-créer-ou-modifier-un-template)
13. [Pourquoi v7 est plus robuste que v4](#13-pourquoi-v7-est-plus-robuste-que-v4)
14. [Dépannage & FAQ](#14-dépannage--faq)

---

## 1. Qu'est-ce que c'est ?

**ai-dev-pipeline v7** est un orchestrateur de pipelines de développement pour Claude Code. Il
automatise des workflows complets — implémenter une issue GitHub dans un projet Unity, produire un
asset pixel art, faire évoluer `aidp` ou son front, documenter un projet — en découpant le travail en
**stages** exécutés par des **sous-agents spécialisés**, avec des **points de validation humaine**
(gates) aux étapes critiques.

Le cœur du système est le binaire Rust **`aidp`** : c'est lui qui décide de tout. Il compile un
template YAML en un **script Workflow JavaScript déterministe** que Claude Code exécute nativement.
Claude n'improvise jamais l'orchestration — il ne fait que lancer quelques commandes `aidp`,
démarrer le Workflow, et vous relayer les questions.

**Ce que ça vous apporte concrètement :**

- Une issue GitHub implémentée de bout en bout (branche → plan → code → tests EditMode → PR →
  playtest dans l'éditeur → review → corrections), le merge restant votre décision.
- Des stages indépendants exécutés **en parallèle** (ex. les 4 dimensions d'une revue).
- Des sorties **validées par schéma JSON** — pas de parsing fragile de texte libre.
- Une **reprise native** après chaque gate : le préfixe déjà exécuté est servi depuis le cache,
  rien n'est recalculé.

---

## 2. Concepts clés

| Terme | Définition |
|---|---|
| **Template** | Un fichier YAML dans `templates/` qui décrit une pipeline : ses inputs, ses stages, ses gates. Ex. `dev-unity`, `pixelart`, `dev-aidp`. |
| **Run** | Une exécution d'un template sur une cible donnée. Identifiée par un `run_id` (`YYYYMMDD-HHMMSS-xxxx`). Ses artefacts vivent dans le vault Obsidian, sous `<vault>/Pipelines/<repo>/<feature>/<run_id>/` — tous les runs d'une même feature sont regroupés sous `<feature>`. |
| **Vault** | Le vault Obsidian où atterrit **tout** ce que les pipelines produisent (`D:/AIDP/Vault` dans le profil gamedev). Voir §9. |
| **Stage** | Une étape de la pipeline, exécutée par un sous-agent. Produit des artefacts déclarés (ex. `plan.md`, `findings.json`). |
| **Sous-agent** | Un des 4 agents génériques (analyzer / planner / executor / reviewer), spécialisé par la liste de `skills` qu'il charge. C'est lui qui fait le vrai travail. |
| **Gate** | Point de validation humaine. Le run se met en pause et Claude vous demande d'approuver ou d'abandonner avant de continuer. |
| **Track** | Niveau de profondeur de `dev-aidp` / `dev-studio` : `quick` (pas d'étude), `standard` (défaut), `deep` (+ revue quatre axes et boucle de correction). |
| **Scope** | Périmètre d'écriture autorisé pour un executor (ex. `production` = code applicatif seulement, `tests` = tests seulement). |
| **Workflow** | L'outil natif de Claude Code qui exécute le script JS émis par `aidp`. Gère la parallélisation, la validation par schéma, les tokens et la reprise. |
| **Knowledge graph (Graphify)** | Graphe de connaissance du workspace construit au `run init`. Les stages d'analyse interrogent le graphe au lieu de faire du Grep/Read massif. Non bloquant : sans le CLI `graphify`, la pipeline fonctionne quand même (les stages se rabattent sur Grep/Read). |
| **Socle de connaissance** | La doc durable d'un projet, dans `<vault>/Knowledge/<repo>/`, hors des runs. Deux couches : les **notes transverses** (ce que le projet est) et une **note par feature métier** dans `Features/` (comment cette capacité fonctionne). Écrit par les stages `knowledge:`, relu en premier par tous les stages de recherche et de planification. Voir §9. |

---

## 3. Installation

### Prérequis

Profil gamedev : **rien ne s'installe sur C:**.

- Claude Code avec l'outil `Workflow` (natif).
- Le binaire `aidp.exe` dans `D:\AIDP\bin`, compilé depuis le dépôt aidp (`D:\AIDP\src\aidp`,
  variable `AIDP_SRC`) avec sa toolchain Rust sur D:. Le skill ne contient que les templates, agents,
  commandes et hooks ; il ne compile rien. v4 n'est pas nécessaire.
- Pour les pipelines Unity et pixel art : Unity, les serveurs MCP Unity, Aseprite et Pixellab, `gh`
  connecté à GitHub, et les skills et agents `unity-*` / `pixel-*` (hors de ce dépôt).
- Facultatif : le CLI `graphify` pour le graphe de connaissance.

### Mise en place

```
powershell -NoProfile -ExecutionPolicy Bypass -File D:\AIDP\skill\setup-gamedev.ps1 -Project D:\CLAUDE_UNITY\<projet>
/pipeline-doctor-v7  # vérifie l'installation (binaire, compatibilité avec le skill, templates, hooks)
```

`setup-gamedev.ps1` (ou `/pipeline-setup-gamedev-v7`) pose `AIDP_SKILL_ROOT=D:\AIDP\skill` et
`AIDP_GATEWAY_DIR=D:\AIDP\gateway`, ajoute le hook Stop à `~/.claude/settings.json`, écrit le vault et
`ci.enabled: false` dans `~/.aidp/config.json`, copie agents et commandes dans `<projet>\.claude\`, puis
lance `aidp validate --all` et `aidp doctor`. Ces deux fichiers de config sont les seuls écrits sur C:
(Claude Code et aidp ne les lisent que là) ; leurs sauvegardes vont dans `D:\AIDP\backup\`. Le script
est relançable. Si `aidp doctor` signale `skill_compat`, le binaire est plus ancien que le
`min_aidp_version` de `SKILL.md` : recompilez-le depuis le dépôt aidp. Un `ci_autopilot_hooks` rouge est
attendu (pas de CI dans ce profil).

> **Note :** Claude utilise la variable utilisateur `AIDP_SKILL_ROOT` pour que les templates v7 soient
> découverts (et non ceux de v4). Si vous lancez `aidp` à la main dans un terminal ouvert avant le
> setup : `$env:AIDP_SKILL_ROOT = "D:\AIDP\skill"` (PowerShell).

---

## 4. Démarrage rapide

La commande principale est **`/run-pipeline-v7 [template] [cible]`** :

```
/run-unity-dev-pipeline 42                 # dev-unity, review-unity puis fix-review-unity sur l'issue #42
/run-pixelart-pipeline 43                  # pixelart sur l'issue d'asset #43
/run-pipeline-v7 dev-unity 42              # une seule pipeline
/run-pipeline-v7 knowledge-init .          # amorcer la base de connaissance du projet
/run-pipeline-v7 dev-aidp                  # faire évoluer aidp (depuis D:\AIDP\src\aidp)
```

Les phrases naturelles fonctionnent aussi : *« lance la pipeline v7 dev-unity sur l'issue 42 »*.

Si vous omettez le template ou la cible, Claude vous les demandera (il ne les devine **jamais**).
Il vous demandera aussi la valeur des inputs à choix multiples (ex. le `track`), avec le défaut
recommandé en première option.

---

## 5. Déroulement d'un run — ce que vous allez voir

Voici ce qui se passe, étape par étape, du point de vue utilisateur :

1. **Choix du template** — Claude liste les pipelines disponibles et vous demande de choisir.
2. **Collecte des inputs** — pour chaque input à choix (`enum`), une question vous est posée
   (ex. *track : quick / standard / deep*). Les inputs texte viennent de la cible que vous avez
   donnée (numéro d'issue, chemin…).
3. **Initialisation** — `aidp run init` crée l'état du run et construit/rafraîchit le graphe de
   connaissance du workspace.
4. **Compilation** — `aidp workflow emit` génère le script `workflow.js` déterministe.
5. **Exécution** — le Workflow tourne en arrière-plan. Vous voyez la progression par stage ;
   les stages indépendants tournent en parallèle. Chaque sous-agent rend une réponse structurée
   validée par schéma.
6. **Plan exécutable** (pipelines `dev-aidp` / `dev-studio`) — quand le planner a écrit son
   `plan.json` (un objet par tâche), le run s'arrête une fois sur `awaiting_plan` : `aidp` relit le
   plan, **génère la fin du workflow** en parallélisant les tâches, puis le run reprend
   automatiquement. Vous ne validez rien à ce moment-là (ce n'est pas un gate) ; Claude peut vous
   montrer l'ordonnancement retenu (`aidp workflow plan-status`).
7. **Gates** — quand un stage gated se termine (ex. `write_knowledge` dans `knowledge-init`), le run
   se met en pause et Claude vous demande : *« Approuver le stage `write_knowledge` ? »* → **approve** continue,
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
| `dev-unity` | `issue?` + `prompt?` + `feature?` + `playtest?` | Plan → implémentation → PR draft → test dans l'éditeur Unity (MCP Unity + computer use) → corrections du playtest. | — |
| `review-unity` | `issue?` + `pr?` + `feature?` | Review Unity de la PR : toute l'issue est-elle faite (CA, tests, actions manuelles, preuves de playtest), puis le code. Commentaires inline si corrections, sinon rapport de vérification complet. | — |
| `fix-review-unity` | `issue?` + `pr?` + `feature?` + `playtest?` + `mark_ready?` | Corrige les commentaires de review ouverts, re-teste dans l'éditeur, passe la PR en ready. `/run-unity-dev-pipeline <issue>` enchaîne les trois. | — |
| `pixelart` | `prompt` + `asset_kind?` + `source?` + `view?` + `size?` + `palette?` + `feature?` | Brief de direction artistique → génération Pixellab → animation → revue notée → retouche → export Unity. `/run-pixelart-pipeline <issue>` construit le `prompt` depuis l'issue. | — |
| `dev-aidp` | `prompt` + `feature` + `track` | Développe `aidp` lui-même (workspace Rust, schémas, docs), selon l'`AGENTS.md` du dépôt. La demande est toujours en texte libre. **Plan-driven.** | — |
| `dev-studio` | `prompt` + `feature` + `workspace?` + `track` | Développe `aidp-studio`, le front du daemon (Vite, React, TypeScript strict, Tailwind, TanStack Query/Router). Le front affiche, le daemon décide. **Plan-driven.** | — |
| `knowledge-init` | `.` ou un chemin de projet | Amorce la base de connaissance d'un projet depuis zéro (6 balayages en parallèle) — à lancer une fois. | write_knowledge |
| `dev-exemple` | `prompt` + `feature` | Démo minimale (contexte, plan, implémentation), sans skill ni gate. | — |

> Pour corriger seulement quelques threads choisis, sans pipeline : `aidp gh pr-fix <repo> <n> --threads <ids> [--points <ids>] [--note-file -]` lance une session autonome libre via le daemon. Elle corrige, répond sur chaque thread et pousse sur la branche de la PR.

**Fragments (`kind: fragment`) — jamais lancés seuls.** `review` (les 4 dimensions de rubrique en
parallèle, puis la synthèse), `knowledge-read` et `knowledge-update` (lecture puis mise à jour de la
base de connaissance, §9) n'existent que pour être composés via `uses:` dans `dev-aidp` et
`dev-studio`. Détail : docs/agents-reference.md §12.

### `dev-aidp` et `dev-studio`

```
prepare_branch → knowledge ‖ read_* → discover → study* → plan → implement (plan-driven)
     → [dev-studio : verify] → review** → correction_loop** → pr
```

`*` sauté en track `quick` (`dev-aidp` seulement) ; `**` en track `deep` seulement.

`implement` n'est pas un stage écrit à la main : il est **compilé depuis `plan.json`** (une tâche =
un sous-agent). Les tâches dont les fichiers sont disjoints tournent en parallèle ; celles qui
écriraient le même fichier sont sérialisées par `aidp`. Un sous-agent de merge termine : fichiers
partagés, build, suite de tests, `changed-files.json` consolidé. `pr` commite sur `feat/<feature>` et
n'ouvre une PR que si le dépôt a un remote.

### Choisir son track

| Track | Étude (`dev-aidp`) | Revue quatre axes + boucle de correction | Quand |
|---|---|---|---|
| `quick` | non | non | petit fix bien cadré |
| `standard` | oui | non | cas nominal (défaut) |
| `deep` | oui | **oui** | changement complexe ou risqué |

> Côté Unity, aucune pipeline ne merge : le merge reste votre clic (gate `merge_approval` du flow
> `perso-delivery`).

---

## 7. Les 4 sous-agents

Tous sont **génériques** ; c'est la liste de `skills` chargée par le stage qui les spécialise.

| Agent | Rôle | Fait | Ne fait pas |
|---|---|---|---|
| **analyzer** | recherche | Lit code, docs, tickets ; explore ; synthétise. | Écrire du code, créer des tickets, pousser. |
| **planner** | planification | Plans ordonnés et testables ; décompositions epic → stories. | Implémenter le plan. |
| **executor** | production | **Le seul qui change le monde** : code, tests, PRs, issues et commentaires GitHub, assets pixel art. | Reviewer son propre travail ; écrire hors de son `scope`. |
| **reviewer** | review | Audite un artefact → `findings.json` structuré. | Appliquer les corrections ; gonfler les findings. |

Exemples de spécialisation d'un executor :

- `unity-csharp-dev` + `unity-shader-hlsl` → développeur Unity C# / shaders ;
- `pixellab` + `pixel-art` + `pixel-animation` → pixel artist ;
- `map-room-design` + `ldtk` → level designer sur les maps LDtk ;
- `github-issue-ticket` → rédacteur d'issues GitHub.

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

Sur une pipeline plan-driven (`dev-aidp`, `dev-studio`), le run s'arrête une fois juste après le
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

Un run natif porte un drapeau `autonomous`, fixé au lancement. Il est vrai par défaut pour les lancements d'un flow et du dispatcher ; depuis le front, vous choisissez. Dans un run autonome, toutes les gates sont pré-approuvées et les agents ne posent jamais de question : ils prennent l'option recommandée (sinon la plus prudente et réversible) et la consignent dans `assumptions`. Un stage bloqué deux fois échoue avec la raison `blocked-twice`. Relisez les `assumptions` via `GET /api/runs/:id`. Le mode Workflow ne change pas. Voir `docs/native-execution.md`.

### Quel mode pour quel lancement

Tout pipeline lancé par le daemon (front, `aidp gateway start --template`, dispatcher et Start des tickets, automations, presets, étape `pipeline` d'un flow) crée un run natif (`mode: "native"`). Autonome par défaut : dispatcher, étape `pipeline` d'un flow. Non autonome par défaut : front (vous choisissez), presets et automations (`autonomous: true` pour activer). Pour revenir à l'ancien chemin (une session Claude qui pilote `workflow.js`), passez `engine: "workflow"` (alias historique `v7`) sur le lancement, le preset ou l'automation. `/run-pipeline-v7` et `aidp workflow emit` restent en mode Workflow. Sur un ticket, `autopilot.run_id` et `autopilot.session_id` portent l'id du run natif. Voir `docs/native-execution.md`.

---

## 9. Artefacts produits — le vault Obsidian

**C'est le changement de la v7 :** tout ce qu'une pipeline produit est écrit dans un vault Obsidian,
plus dans le dossier `.aidp/` du repo. Les artefacts deviennent des notes liées, cherchables, avec des
propriétés — au lieu de fichiers enfouis dans l'arbre de build.

```
<vault>/                                          D:/AIDP/Vault
└── Pipelines/
    ├── _Pipelines.md                             tableau de bord : tous les repos, 25 derniers runs
    └── pixelhood/                                nom du repo (remote git `origin`)
        ├── _pixelhood.md                         MOC du repo : toutes ses features
        └── issue-42/                             la feature
            ├── _issue-42.md                      MOC de la feature : tous ses runs + la recherche
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
    └── pixelhood/                                un dossier par projet
        ├── _pixelhood.md                         note générée : l'index des deux couches
        ├── architecture.md                       couche transverse : ce que le projet EST
        ├── events.json
        └── Features/                             couche feature : une note par feature
            ├── _Features.md                      note générée : le tableau des features
            ├── saut-mural.md                     règles, flux, carte du code, cas limites
            └── dash.md
└── TODO/                                         tickets locaux — HORS des runs
    ├── _TODO.md                                  tableau de bord généré
    ├── config.yaml, routing.yaml                 édités à la main
    ├── pixelhood/                                un dossier par service
    │   └── LOC-1.md                              une note par ticket local
    └── .state/                                   compteur + journal des transitions
```

**Amorcer un projet** (à faire une fois, avant tout le reste) :

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

### La boucle, câblée dans `dev-aidp` et `dev-studio`

1. **Lecture** — `knowledge-read` est le premier stage de la discovery. Il commence par la **note de la
   feature concernée**, complète avec les notes transverses, résume tout en `knowledge_context.md`, et
   termine par la liste de ce que le socle **ne dit pas** : c'est exactement ce que les lectures du
   code doivent aller chercher.
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
note si la feature existe déjà » finit par produire `saut-mural.md`, `sautmural.md` et
`saut-mural-v2.md` — et un socle dupliqué est pire que pas de socle. La décision est donc calculée :

```bash
rtk aidp knowledge resolve --name "Saut mural" --name GH-42
```

Chaque note existante est notée face à chaque requête — nom/alias/slug exact → `1.00`, clé de ticket présente
dans le `tickets:` de la note → `0.95`, sinon recouvrement de mots (accents pliés, mots vides ignorés).
Le verdict est `update` (≥ 0.78, avec **le fichier à éditer**), `ambiguous` (≥ 0.42, avec les candidates
à relire), `create` (avec **le chemin exact à écrire**, nommé d'après la feature et jamais d'après un
ticket), ou `supersede` — la note qui matche le mieux est elle-même périmée, son score est donc plafonné
à `0.50` (elle reste une candidate, mais ne peut plus être une cible de mise à jour) et la cible devient
la note nommée par son propre `superseded_by`. Tout stage `knowledge: feature` reçoit ce verdict **déjà calculé** dans son prompt, dérivé des
inputs du run (`feature` et, quand le template les déclare, les clés de ticket et le sujet) — l'agent
se voit donner le nom de fichier, il ne le
choisit pas.

Un cas est signalé explicitement : si les seules requêtes disponibles étaient des clés de ticket, le
résultat porte `weak: true`. « Aucune note ne liste GH-42 » est vrai de **tout** ticket à son
premier run et ne prouve pas que la feature est neuve : l'agent est alors invité à relancer la
résolution avec le nom métier lu dans le ticket, et à obéir à ce second verdict.

La résolution lit le frontmatter des notes — `aliases:` et `tickets:` sont donc ce qui la rend fiable :

```yaml
---
aidp: knowledge-feature
feature: Saut mural
slug: saut-mural                       # identique au nom de fichier
aliases: [wall jump, wall slide]
area: Mouvement du joueur
status: active
tickets: [GH-42, GH-57]
files: [Assets/Scripts/Player/Movement.cs, Assets/Scripts/Player/Collision.cs]
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
3. Le segment `<repo>` vient du remote git `origin`, donc deux checkouts du même repo (le checkout
   principal et un worktree) atterrissent au même endroit.

### Où `aidp` trouve le vault

Par ordre de priorité, le premier qui répond gagne :

| # | Source | Comment |
|---|---|---|
| 1 | `--vault <chemin>` | sur `rtk aidp run init` — ponctuel |
| 2 | `AIDP_VAULT` | variable d'env ; `off` / `none` / `0` force l'ancien layout |
| 3 | `~/.aidp/config.json` | `{"vault": "D:/AIDP/Vault"}` — écrit par `setup-gamedev.ps1` ou `rtk aidp vault init` |
| 4 | auto-détection | le dossier contenant un `.obsidian/` le plus proche, en cherchant depuis le repo **et parmi ses voisins** (c'est ainsi qu'un vault posé à côté des projets est trouvé) |
| — | rien trouvé | on retombe sur l'ancien `<repo>/.aidp/pipelines/…`, à l'identique |

```bash
rtk aidp vault status --format json-pretty
```

Affiche le vault retenu, **par quelle source**, le segment `<repo>` de ce workspace, le nombre de runs,
et un éventuel `ambiguity` (plusieurs vaults à portée — épingle-en un). Pour créer/épingler :

```bash
rtk aidp vault init --vault D:/AIDP/Vault
```

Et pour régénérer toutes les notes `_*.md` (après une mise à jour d'`aidp`, ou une note supprimée) :

```bash
rtk aidp vault reindex
```

### Ce qui reste dans le repo

**Rien de ce qu'aidp écrit** — pas même l'état qui appartient au repo plutôt qu'à un run précis. Le
marqueur `run-in-flight` vit dans
`<vault>/Pipelines/<repo>/.state/`, préfixé d'un point pour qu'Obsidian comme les générateurs de notes
passent à côté. La copie laissée dans `<repo>/.aidp/` par un binaire plus ancien est déplacée dès le
premier accès, et le dossier disparaît une fois qu'il ne reste plus rien de nous dedans.

Ce qui reste dans le repo, c'est **ce que vous y avez mis** : `.aidp/pipeline/flow/` (templates locaux
au projet), et dans le profil gamedev `.claude/agents/` et `.claude/commands/` copiés par
`setup-gamedev.ps1`. Ce sont des **entrées**, pas des sorties — aidp les lit, ne les crée jamais. Sans vault, le
run bascule en mode legacy et l'état retombe dans `.aidp/` : il n'a nulle part d'autre où aller. Et
les **runs d'avant la v7** restent où ils sont, sous `.aidp/pipelines/` : rien n'a été migré, et v7
n'a plus de chemin pour les recharger ou les reprendre.

Les artefacts principaux, tous validés par les schémas JSON de `schema/` :

| Artefact | Produit par | Contenu |
|---|---|---|
| `context.md` | analyzer (discover) | Synthèse du contexte (demande, base de connaissance, code). |
| `plan.json` | planner | **Le plan exécutable** : une tâche par objet (prompt, instructions, `needs`, `files`), + `shared_files` réservés au merge. C'est lui que `aidp` compile. |
| `plan.md` | planner | La narration du plan pour un humain (design, risques, rollback). |
| `plan-schedule.json` | `aidp` | L'ordonnancement retenu : vagues, parallélisme, et chaque ordre inséré pour éviter un conflit d'écriture (avec le fichier en cause). |
| `changed-files.json` | executor (code/tests) | Fichiers créés/modifiés/supprimés, nouvelles dépendances, statut build/lint. |
| `findings.json` | reviewer | Findings avec sévérité (`blocking` / `major` / `minor` / `info`), fichier/ligne, suggestion. |
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
| `/run-unity-dev-pipeline <issue>` | Enchaîner `dev-unity`, `review-unity` et `fix-review-unity` sur une issue. |
| `/run-pixelart-pipeline <issue>` | Lancer `pixelart` sur une issue d'asset. |
| `/pipeline-status-v7` | Lister les runs v7 du workspace. |
| `/pipeline-resume-v7 [run_id]` | Reprendre un run v7 en pause. |
| `/pipeline-setup-gamedev-v7 [projet] [vault]` | Setup du profil gamedev (`setup-gamedev.ps1`) : variables, hook Stop, config, agents et commandes du projet, doctor. |
| `/pipeline-doctor-v7` | Diagnostic de l'installation. |
| `/pipeline-new-v7` | Scaffolder un nouveau template v7 par Q&A. |
| `/pipeline-validate-v7 <id\|chemin>` | Valider un YAML contre le schéma. |
| `/agent-new-v7 [nom]` | Scaffolder un nouveau sous-agent. |

### Commandes `aidp` du vault (terminal)

| Commande | Usage |
|---|---|
| `rtk aidp vault status --format json-pretty` | Quel vault est retenu, par quelle source, combien de runs, et le segment `<repo>` de ce workspace. |
| `rtk aidp vault init --vault <chemin>` | Crée le squelette (`Pipelines/`, `Knowledge/`, `.obsidian/`, notes d'index) et épingle le chemin dans `~/.aidp/config.json`. |
| `rtk aidp vault reindex` | Régénère toutes les notes `_*.md` de tous les runs du vault. |
| `rtk aidp status` | Liste les runs de ce repo — ceux du vault **et** les anciens restés dans `.aidp/pipelines/`. |
| `rtk aidp run init … --no-vault` | Exception ponctuelle : garder les artefacts d'un run dans le repo. |
| `rtk aidp knowledge list --format json-pretty` | Le socle du repo courant : notes transverses, et une ligne par note de feature (slug, nom, alias, tickets). |
| `rtk aidp knowledge resolve --name "<feature>"` | Nouvelle feature ou feature existante : `update` + le fichier à éditer, `create` + le chemin à écrire, ou `ambiguous` + les candidates. Répétable (`--name` plusieurs fois), les clés de ticket comptent. |
| `rtk aidp knowledge index` | Régénère les notes d'index du socle (`_<repo>.md`, `Features/_Features.md`, `_Knowledge.md`) — à lancer après une édition à la main. |
| `rtk aidp knowledge path` | Les chemins résolus des deux couches. |
| `rtk aidp ticket new --service <repo> --summary "<texte>"` | Crée un ticket local dans `TODO/<service>/<KEY>.md` ; les autres verbes (`list`, `show`, …, `budget`) sont détaillés dans `docs/tickets.md`. |

Contrairement à `Pipelines/` et `Knowledge/`, `TODO/` n'est pas créé par `rtk aidp vault init` : c'est la
première commande `rtk aidp ticket` qui le crée à la demande.

Dans un stage, ces commandes n'ont besoin d'aucun flag : `$AIDP_RUN` est exporté par le prompt et
localise le socle du run.

Deux commandes de plus, sans lien avec le vault, mais qui se tapent au même endroit :

| Commande | Usage |
|---|---|
| `rtk aidp findings merge --input <fichier> --input <fichier> ... --out <fichier>` | Fusionne plusieurs `findings.json` d'axes de revue (correctness/sécurité/perf/maintenabilité) en un seul : recalcule les compteurs au lieu de les recopier, déduplique les findings identiques en gardant la sévérité maximale, et sort en erreur — en nommant le fichier fautif — si un axe est absent, illisible, ou ment sur ses propres comptes. |
| `rtk aidp setup agents [--dest <dossier>] [--force]` | Installe les agents restreints (`aidp-analyzer-ro`, `aidp-planner-ro`, `aidp-reviewer-ro`) dans `~/.claude/agents/` par défaut (`setup-gamedev.ps1` passe `--dest <projet>\.claude\agents`) — condition d'entrée de `settings.tool_enforcement: strict` (§11). Refuse d'écraser un fichier existant sans `--force` (ce registre est partagé avec vos autres agents). |

Un `findings.json` d'axe déclare désormais aussi ce qu'il a **contrôlé**, pas seulement ce qu'il a
trouvé : un tableau `checks[]` à trois états — `pass`, `fail`, `skip` (ce dernier exigeant un
`harness_gap` nommé). Voir `on_harness_gap` (§12) pour ce qui se passe quand un relecteur déclare
un trou.

### Workflow des tickets : actions et sondes d'attente

Le moteur `rtk aidp flow` enchaîne des actions sur un ticket. Celles de `perso-delivery` :
`git.worktree`, `git.branch`, `gh.pr_ready`, `gh.merge` et `worktree.remove` (aussi en commande :
`rtk aidp flow git-branch <KEY>`). Elles impriment du JSON ; un refus métier (branche distante avec des
commits étrangers, par exemple) sort en code 6. Un flow peut attendre un événement externe avec une
étape `wait` (sonde `pr.reviews` : les revues humaines de la PR sont arrivées). `gh.merge` ne s'exécute
qu'après le clic de la personne qui valide : le flow s'arrête sur une approbation, jamais de lui-même.

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
4. **Gates sur les actions irréversibles.** Merge, publication, création d'issues :
   toujours derrière une validation humaine ou une condition explicite.
5. **Encadrement des passages non fiables (frontière inter-stage).** La sortie d'un sous-agent
   (`summary`, `follow_ups`) devient littéralement une partie du prompt du stage suivant — diff,
   log, issue ou note du vault compris. Un scanner encadre les passages suspects dans un bloc
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
   parce qu'un analyzer en a besoin (`rtk git diff`, `rtk cargo check`). La restriction empêche donc
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

### Livraison par flow

Le flow `perso-delivery` enchaîne worktree, branche, `dev-unity`, `review-unity`, `fix-review-unity`,
PR ready et merge humain, sans bloc CI : `POST /api/tickets/:key/flow` avec le corps
`{"flow": "perso-delivery"}`. Nommez toujours le flow : celui que le daemon démarre quand la requête
n'en nomme aucun (`ticket-delivery`, aussi utilisé par `dispatcher.launch: flow`) n'est plus dans ce
skill. Détail dans `docs/flows.md` du dépôt aidp.

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
  issue:    { required: true, kind: string }
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
    skills: [graphify]              # ← c'est ça qui spécialise l'agent
    inputs: { issue: "{{ inputs.issue }}" }
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
      merge_hint: "Câbler les fichiers partagés (DI, asmdef), builder, consolider changed-files.json."

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
  # - name: review
  #   type: pipeline
  #   uses: review
  #   needs: [code]
  #   outputs: [{ name: findings, from: review.findings }]
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

### Règles de conception utiles

- **Parallélisme** : deux stages sans `needs` entre eux (mais avec le même amont) fusionnent en un
  bloc `parallel()`. Pattern recommandé : fan-out de lecteurs indépendants + un stage de synthèse
  en aval qui garde le nom canonique (voir `dev-aidp.yaml` : `knowledge` ‖ `read_rust` → `discover`).
- **Fan-out intra-stage (`fan_out:`)** : un stage seul peut lancer N sous-agents en parallèle, puis
  un sous-agent de merge qui produit l'enveloppe canonique du stage. Deux sources de shards :
  `items:` (liste statique, ex. catégories de tests) ou `from: "{{ stages.<s>.signals.<prop> }}"`
  (dynamique — l'émetteur injecte alors dans le prompt du producteur l'obligation d'émettre ce
  signal comme lots de travail **disjoints en fichiers**). Les shards partagent le working tree :
  chaque shard ne touche que ses fichiers et défère les fichiers partagés (DI, asmdef, manifestes)
  au merge via `follow_ups`. Source vide → dégradation en 1 seul sous-agent. Utilisé par
  `knowledge-init` sur `write_features` (dynamique).
- **Expressions** : `when:` et `gate:` acceptent `in`, `==`, `not` / `and` / `or`,
  `>` `<` `>=` `<=`, `default()` sur `inputs` / `stages` / `settings`.
- **`when` ≠ `gate`** : `when` décide si le stage s'exécute (conditionnel) ; `gate` met le run en
  pause pour validation humaine.
- **`isolation: worktree`** : réservez-le aux executors qui écrivent en parallèle ; c'est coûteux
  et inutile en lecture seule.
- **Choix des skills** : un skill déclaré sur un stage doit porter au moins une règle applicable au
  livrable de ce stage. Un skill de procédure sur son propre stage est accepté.
  Un test de garde refuse les paires skill/stage de sa liste d'exclusion.
- **Règles de skill vérifiées** : la revue lance `rtk aidp skill-rules check` sur le diff de la branche
  (pas de commentaire `//` hors `///` et `//!`, pas de clé de ticket dans les lignes `.rs` ajoutées).
  Les violations sortent en findings `blocking` sur l'axe `skill_rules`, avec fichier et ligne.
- **Graphe de connaissance** : les templates déclarent le skill `graphify`, qui interroge
  `graphify-out/` quand il existe et se rabat sur Grep/Read sinon. (Le binaire retire encore
  l'ancien skill `graphify-context` d'un run sans graphe, avec un avertissement par stage.)

---

## 13. Pourquoi v7 est plus robuste que v4

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
| Les templates v4 apparaissent au lieu des v7 | `AIDP_SKILL_ROOT` absent/incorrect, ou un vieil `aidp` v4 en tête de PATH | Le définir sur ce dossier (`D:\AIDP\skill`) avant chaque appel `aidp` ; relancer `setup-gamedev.ps1`, qui le pose et met `D:\AIDP\bin` dans le PATH. |
| `aidp: command not found` | `D:\AIDP\bin` absent du PATH | Ouvrir un nouveau terminal, ou relancer `setup-gamedev.ps1`. |
| `workflow emit` : sous-commande inconnue | binaire compilé sans `workflow` | Recompiler aidp depuis `D:\AIDP\src\aidp` et le copier dans `D:\AIDP\bin`. |
| Le run cale après approbation d'un gate | reprise mal formée | Vérifier que la reprise passe `resumeFromRunId` + le gate dans `args.approved_gates` ; les approbations antérieures sont persistées. |
| Un stage a écrit hors de son `scope` déclaré | rien ne bloque en direct — l'écriture a déjà eu lieu | Vérifier `aidp scope verify --run <id>` (sort en non-zéro sur violation) ou `scope_violations` dans `run-state.json` après réconciliation ; corriger à la main, aucun hook ne l'aurait empêché (§11). |
| Knowledge graph `skipped` / `failed` | CLI `graphify` absent | Non bloquant. Installer `graphify` vous-même (hors C:) pour réactiver l'accélération. |
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
