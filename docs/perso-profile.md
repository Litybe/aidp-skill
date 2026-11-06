# Profil perso : projets GitHub sans CI, sans Copilot, sans Jira

Ce profil sert à utiliser aidp sur des projets personnels hébergés sur GitHub. Il ne garde que la
lecture des pipelines et des flows YAML et leur orchestration. Le binaire reste le même : aucune
fonction Jira, Sonar, Teams, CI ou Copilot n'est appelée tant qu'aucun template ni aucune config ne
la demande.

## Ce que le profil utilise

| Élément | Rôle |
|---|---|
| `templates/dev-unity.yaml` | Le workflow du skill `unity-issue-workflow` en pipeline : prepare → implement → review → correction → ready |
| `templates/flows/perso-delivery.yaml` | Flow d'un ticket local : worktree → branche → `dev-unity` → PR prête → merge humain → nettoyage |
| Skill `github-issue-ticket` | Rédaction des issues GitHub servant de tickets : description technique, critères d'acceptation, scénarios de test, contrôle « prêt pour haiku » |
| Skills `unity-issue-workflow`, `unity-csharp-dev` et `unity-shader-hlsl` | Procédures, références (`unity-verify.md`, `github.md`, `config.md`), règles C# Unity et règles des shaders HLSL (URP en priorité, SRP Batcher, variantes, précision, compute, contrôle de compilation) |
| Agents `unity-issue-implementer`, `unity-pr-reviewer`, `unity-review-fixer` | Les trois étapes du workflow, sous `~/.claude/agents/` |
| L'agent générique `executor` | Les stages `prepare` et `ready` |
| Un vault Obsidian perso | Les runs et les tickets locaux |

Ce que le profil n'utilise pas : `ci.watch`, `gha-fix`, `sonar-fix`, `gh.copilot_review`, `jira.*`,
`deploy.dev`, `notify.teams`, les pipelines `*-fraud`, `dev-discovery` (qui lit Jira et Confluence).

## Les pipelines Unity : `dev-unity` → `review-unity` → `fix-review-unity`

`/run-unity-dev-pipeline <issue>` les lance dans cet ordre ; le flow `perso-delivery` aussi.

**`dev-unity`**

| Stage | Agent | Modèle | Rôle |
|---|---|---|---|
| `prepare` | `executor` | haiku | Dépôt Unity, `rtk gh auth`, conf `.claude/unity-workflow.json`, issue, arbre propre, PR liée, nom de branche. Écrit `context.json` |
| `plan` | `planner` + `unity-csharp-dev` | opus | `plan.md` : critères, fichiers, étapes, tests EditMode, scénarios de playtest, actions manuelles, risques |
| `implement` | `unity-issue-implementer` | opus | Suit le plan : branche, code, tests EditMode, compilation batch, PR en draft. Écrit `pr.json` |
| `playtest` | `unity-playtester` | sonnet | Test dans l'éditeur (`references/unity-playtest.md`) : MCP Unity + computer use, un scénario par critère ; rapport en commentaire de PR |
| `playtest_fix` → `fix_playtest`, `retest` | implémenteur, playtester | opus, sonnet | 2 tours max tant que `fix_needed` ; au-delà, le run se met en pause |
| `report` | `executor` | haiku | `report.md`, `state.json`. La PR reste en draft |

**`review-unity`** : `prepare` → `review` (`unity-pr-reviewer`, opus : toute l'issue est-elle faite, avec preuves, puis le code ; une review GitHub — commentaires si corrections, rapport de vérification sinon) → `verdict`.

**`fix-review-unity`** : `prepare` (fils ouverts) → `fix` (`unity-review-fixer`) → `playtest` → `ready` (PR prête si rien de bloquant). Sans fil ouvert, `fix` et `playtest` rendent la main tout de suite.

L'éditeur : `implement` compile en batchmode (éditeur fermé) ; le playtest ouvre l'éditeur et le laisse
ouvert, et les corrections suivantes compilent par le MCP Unity (`unity-verify.md` §2).

Les agents Unity ont une section « Lancé par aidp », qui les fait travailler comme les agents
génériques. Elle s'ajoute à leur procédure Unity sans rien en retirer, et ils restent utilisables
seuls ou par `/unity-issue-workflow`. Quand aidp les lance :

- **Contexte** : ils lisent `inputs.context`.
- **Artefacts** : ils les écrivent dans leur dossier de stage du vault.
- **Réponse** : ils rendent l'enveloppe de réponse, avec `outputs` en chemins absolus,
  `assumptions` et `follow_ups`, et sans jamais poser de question.
- **Signaux** : `pr_number` et `compile_ok` pour l'implémenteur ; `fix_needed`,
  `has_blocking_findings` et `unevaluated_checks` pour le reviewer ; `pushed` et `open_blocking`
  pour le fixer.
- **Findings** : le reviewer écrit aussi un `findings.json` au format aidp, avec les gravités
  traduites (`bloquant` → `blocking`, etc.) et ses `checks`.

Écarts avec le skill :

- Aucune question en cours de run. Ce que le skill demandait devient une décision : éditeur ouvert →
  `unity.verify: skip` pour ce run, consigné en hypothèse ; arbre sale, issue fermée ou PR
  introuvable en reprise → stage `prepare` bloqué.
- Un seul tour de review : `review.maxRounds` de la conf n'est pas lu.
- Une compilation qui échoue encore après trois tentatives bloque le run après l'ouverture de la PR,
  comme le `compile_failed` du skill.
- Sans `issue`, la demande est `prompt` (le corps du ticket local dans le flow) et la PR n'a pas de
  ligne `Closes #`.

## Installation

Sur la machine perso, utilise le setup perso plutôt que `/pipeline-setup-v7` :

```powershell
powershell -ExecutionPolicy Bypass -File ~/.claude/skills/ai-dev-pipeline-v7/setup-perso.ps1 -Vault "D:/Vaults/Perso"
```

Ou depuis Claude Code : `/pipeline-setup-perso-v7 D:/Vaults/Perso`.

Il fait la même chose que `setup.ps1`, sans l'outillage du travail. Voici ce qu'il fait :

- Il reprend l'`aidp.exe` déjà installé quand les sources d'aidp sont absentes.
- Il installe seulement le hook Stop, sans les hooks de l'autopilot CI.
- Il installe les quatre agents génériques et génère les agents `aidp-*-ro`.
- Il installe les commandes, sauf `/ci-autopilot-v7`.
- Il écrit `~/.aidp/config.json` avec l'autopilot CI coupé.
- Il n'installe pas graphify.
- Il lance `doctor` ; l'absence des hooks CI n'y est pas comptée comme une erreur.

Il coupe l'autopilot CI pour toute la machine : ne le lance pas sur un poste de travail qui s'en
sert.

## Configuration

`~/.aidp/config.json`, réduit au vault, avec l'autopilot CI coupé (il est actif par défaut, et
`setup-perso.ps1` l'écrit pour toi) :

```json
{
  "vault": "D:/Vaults/Perso",
  "ci": { "enabled": false }
}
```

Sur une machine qui sert aussi au travail, garde ta config et bascule par variables
d'environnement dans le terminal du projet perso :

```powershell
$env:AIDP_VAULT = "D:/Vaults/Perso"
$env:AIDP_SKILL_ROOT = "$HOME/.claude/skills/ai-dev-pipeline-v7"
```

Et coupe l'autopilot CI du dépôt avec `<repo>/.aidp/ci-autopilot.json` : `{ "enabled": false }`.

La conf du projet Unity reste celle du skill : `.claude/unity-workflow.json` à la racine du dépôt
(champs et défauts : `~/.claude/skills/unity-issue-workflow/references/config.md`).

Prérequis : `git`, `gh` authentifié sur ton compte GitHub, `aidp` installé par
`/pipeline-setup-v7`, les trois skills et les trois agents Unity sous `~/.claude`, Unity Hub avec la
version d'Editor du projet.

## Lancer un dev

Écris d'abord l'issue avec le skill `github-issue-ticket` (« crée une issue pour … ») : description
technique avec chemins et signatures, critères `CA-n`, scénarios de test `T-n`. Les stages tournent
sur haiku, sauf la review : un ticket précis évite qu'ils devinent.


Directement depuis Claude Code, à la racine du projet Unity :

```
/run-pipeline-v7 dev-unity
```

Entrées : `issue` (numéro d'issue GitHub) ou `prompt` (la demande en texte), `feature` (dossier du
run), `start_at` (`implement`, `review` ou `fix` sur la PR déjà liée), `mark_ready` (`true` par
défaut).

Par le daemon, pour un ticket local du vault :

```
POST /api/tickets/:key/flow   {"flow": "perso-delivery"}
```

Le flow passe `mark_ready: false` : c'est son étape `ready` qui sort la PR du draft.

## Unity : ce qu'il faut savoir

- **L'Editor ne doit pas avoir le projet ouvert.** Unity refuse deux instances sur le même projet ;
  avec `Temp/UnityLockfile` présent, le run continue sans compiler ni tester. Le flow travaille dans
  un worktree, donc ton Editor ouvert sur le checkout principal ne gêne pas.
- **Chaque worktree reconstruit `Library/`.** Le skill évite les worktrees pour cette raison ; le
  flow en utilise un par ticket, et son premier run paie le réimport complet du projet.
- **Compilation et tests en batch**, selon `references/unity-verify.md` du skill.
- **Fichiers `.meta`, scènes, prefabs, assets** : jamais modifiés à la main. Ce qui demande
  l'éditeur part dans les actions manuelles de la PR.
- **Dépôt.** Un `.gitignore` Unity (`Library/`, `Temp/`, `Logs/`, `obj/`, `Build/`,
  `UserSettings/`) et Git LFS pour les assets binaires sont attendus ; le pipeline ne les crée pas.

## Ajouter une autre stack

Copie `dev-unity.yaml` sous un autre id et remplace les trois agents par ceux de la stack (ou par
`executor` et `reviewer` avec des consignes inline), puis copie `flows/perso-delivery.yaml` sous un
autre id en changeant le `use:` de l'étape `dev`.
