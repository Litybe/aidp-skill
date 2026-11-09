# Vérifier un projet Unity depuis un stage aidp (compile gate C1, tests EditMode C8), en batchmode

Recette partagée des pipelines `unity-implement`, `unity-review` (lecture seule), `unity-fix` et
`unity-test`. **Les stages ne font que du headless** : l'éditeur Unity est lancé en `-batchmode
-nographics` dans le worktree du stage, pour compiler et jouer les tests EditMode. Aucun stage ne
lance de test PlayMode, aucun scénario PlaytestDriver, aucun MCP Unity, aucun computer use : le
test en PlayMode est fait **à la main** par l'humain avant le merge (§3).

Chemin de ce fichier : `<skill_root>/templates/recipes/unity-verify.md`
(`skill_root` = `$AIDP_SKILL_ROOT`).

Les chemins ci-dessous sont relatifs à la **racine du projet Unity** (`context.projectRoot`), sauf
`<stage_dir>`, le dossier de ton stage (là où tu écris tes sorties). Les logs et les résultats Unity
vont dans `<stage_dir>`, jamais dans le dépôt.

## 0. Prérequis : un worktree à toi, un éditeur trouvé

Les flows `game-*` travaillent toujours dans un **worktree** du ticket (dev comme test). Un
batchmode ne se lance jamais sur un projet qu'un éditeur a ouvert : Unity refuse (« Multiple Unity
instances cannot open the same project ») et un éditeur ouvert sur le checkout principal n'est
jamais le tien.

1. `rtk curl -s http://127.0.0.1:3001/api/unity/status` (route absente : regarde un process
   `Unity` et sa ligne de commande `-projectPath`). Si `editor.running` vaut `true` et que
   `editor.projectPath` désigne `context.projectRoot` (casse et `/`/`\` ignorés) : réponds
   `status: blocked`, `signals.blocked_reason: "unity-editor-busy"`, « blocked: unity-editor-busy »
   dans `summary`. Ne ferme jamais l'éditeur.
2. L'exécutable Unity, premier qui existe :
   - `$AIDP_UNITY_EDITOR` ;
   - `unity.editorPath` de `.claude/unity-workflow.json` à la racine du dépôt ;
   - la version `m_EditorVersion` de `ProjectSettings/ProjectVersion.txt` dans un dossier Unity Hub
     par défaut : `%ProgramFiles%\Unity\Hub\Editor\<version>\Editor\Unity.exe`,
     `~/Unity/Hub/Editor/<version>/Editor/Unity`,
     `/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity`.
   Rien : `blocked`, `signals.blocked_reason: "unity-editor-path"`. La version de l'exécutable doit
   être celle de `ProjectVersion.txt` (un autre éditeur migrerait le projet) : sinon `blocked`,
   `unity-version`.
3. Options communes à chaque appel : `-batchmode -nographics -projectPath "<projectRoot>" -logFile
   "<stage_dir>/unity-<requestId>.log"`. Un `requestId` par appel : `<stage>-<epoch ms>`, ASCII,
   sans espace. Jamais `-quit` avec `-runTests`. Un seul Unity à la fois dans ton worktree ; attends
   la fin du process avant d'en lancer un autre.
4. Délais : **900 s** pour le premier appel dans un worktree (import de la `Library`), **600 s**
   ensuite. Dépassé : tue le process, réponds `blocked`, `unity-timeout`, avec la fin du log.
5. Le log contient `No valid Unity Editor license` : `blocked`, `unity-license`. Il contient
   `Multiple Unity instances cannot open the same project` : `blocked`, `unity-editor-busy`.

## 1. Compile gate (contrat C1)

```
"<Unity>" -batchmode -nographics -quit -projectPath "<projectRoot>" -logFile "<stage_dir>/unity-compile-<requestId>.log"
```

1. Lance la commande et attends sa fin (délais du §0).
2. Verdict, **le log fait foi** : `ok` vaut `true` seulement si le code de sortie est 0 **et** que
   le log ne contient ni une ligne `error CS` ni `Scripts have compiler errors`. Les erreurs sont les
   lignes `<fichier>.cs(<ligne>,<colonne>): error CS<code>: <message>` (chemin relatif à la racine du
   projet, dédoublonnées). Les warnings sont les lignes `warning CS` dédoublonnées. Shaders : une ligne
   `Shader error in` est une erreur.
3. Écris `<stage_dir>/compile-<requestId>.json` :
   ```json
   { "id": "<requestId>", "ok": true, "errors": [ { "file": "Assets/...cs", "line": 12, "column": 5, "message": "CS0103: ..." } ],
     "warnings": 3, "durationMs": 48000, "unityVersion": "6000.6.7f1", "exitCode": 0, "log": "unity-compile-<requestId>.log", "finishedAt": "..." }
   ```
   - `ok: true` : compile gate vert. Les warnings des fichiers que tu as touchés se corrigent aussi.
   - `ok: false` : corrige chaque erreur (`file:line`) et relance une **nouvelle** requête. Au plus
     5 requêtes par stage ; ensuite le stage échoue (`status: failed`) avec la dernière liste.
4. Rapporte dans le JSON du stage : `verification.compile` = `{ ok, errors, warnings, durationMs,
   requestId }`. Ne déclare jamais `ok` pour une compilation qui n'a pas tourné.

Fichiers que le batchmode écrit : il importe les nouveaux assets et crée leurs **`.meta`** (commite-les
avec leurs fichiers, `rtk git status` les montre). S'il a réécrit `ProjectSettings/*.asset`,
`Packages/packages-lock.json` ou `UserSettings/` sans que ton changement l'exige : `rtk git restore`
ces fichiers. Ne commite jamais `Library/`, `Temp/`, `Logs/`, `obj/`, `*.csproj`, `*.sln`, `.aidp/`.

## 2. Tests EditMode (contrat C8)

Après un compile gate vert seulement.

```
"<Unity>" -batchmode -nographics -projectPath "<projectRoot>" -runTests -testPlatform EditMode -testResults "<stage_dir>/editmode-<requestId>.xml" -logFile "<stage_dir>/unity-editmode-<requestId>.log"
```

- `-testFilter "<Namespace.Classe>"` (ou le nom complet d'un test) sert à vérifier vite un test précis,
  par exemple le rouge d'un test de reproduction. Le dernier appel du stage joue **toute** la suite,
  sans filtre.
- Codes de sortie du Unity Test Framework : `0` tout passe, `2` au moins un test en échec, `3`
  erreur d'exécution (compilation cassée, assembly introuvable). Un `3` avec `error CS` dans le log
  est un compile gate KO : reviens au §1.
- Lis le XML NUnit : `<test-run total passed failed skipped duration>` à la racine ; chaque échec est
  un `<test-case fullname result="Failed">` avec `<failure><message>` et `<stack-trace>`. Pas de
  `test-case` du tout (aucune assembly EditMode) : `total: 0`, note `no-tests`, pas un échec, mais
  dis-le.
- Écris `<stage_dir>/tests-<requestId>.json` :
  ```json
  { "id": "<requestId>", "mode": "EditMode", "total": 42, "passed": 41, "failed": 1, "skipped": 0, "durationMs": 9000,
    "failures": [ { "name": "Ns.Class.Test", "message": "...", "stack": "..." } ], "exitCode": 2, "log": "unity-editmode-<requestId>.log", "finishedAt": "..." }
  ```
- Un test qui échoue est un échec du stage, sauf pour le stage `repro` où le rouge est attendu.
- Jamais de `-testPlatform PlayMode` : le PlayMode est manuel (§3).

## 3. PlayMode : manuel, hors pipeline

Aucun stage ne joue le jeu. Ce que seul le PlayMode peut montrer (déplacement, collisions,
caméra, animation, sensation) est testé **par l'humain** avant le merge, à partir de la section
**« Test manuel en PlayMode »** du corps de la PR : pour chaque critère `CA-n` qui ne se prouve pas
par un test EditMode, un scénario `T-n` en trois lignes (**scène ou arène**, **actions** au clavier
ou à la manette, **résultat attendu** observable). Le stage `implement` écrit cette section, les
stages `fix` la tiennent à jour, `unity-review` vérifie qu'elle couvre chaque critère, et
`unity-test` la recopie en check-list dans son commentaire de PR.

Le package `com.aidp.playtest` (PlaytestDriver : scénarios JSON, clavier virtuel, sondes, captures,
enregistrement de repro) reste disponible **pour toi, dans l'éditeur ouvert** : un stage ne dépose
aucune requête dans `.aidp/`, ne lit aucun résultat `.aidp/playtest/`, ne crée ni ne modifie de
fichier sous `Assets/Tests/Playtest/Scenarios/`. Une sonde ou une commande n'est plus exigée par un
critère : si le jeu en a, elles se corrigent comme du code ordinaire.

## 4. Sorties de statut, rappel

| Situation | Réponse du stage |
|---|---|
| Éditeur ouvert sur `projectRoot` (jamais le cas dans un worktree) | `blocked`, `signals.blocked_reason: "unity-editor-busy"` |
| Exécutable Unity introuvable, ou d'une autre version que le projet | `blocked`, `unity-editor-path` / `unity-version` |
| Licence absente, délai dépassé | `blocked`, `unity-license` / `unity-timeout` |
| Erreurs de compilation que tu ne sais pas corriger en 5 requêtes | `failed`, liste `file:line` |
| Test EditMode KO (stage `unity-test`) | pas un blocage : `completed` avec `passed: false` |
| Test EditMode KO (stages `implement`, `fix`) | corrige avant de pousser ; irréparable : `failed` |
