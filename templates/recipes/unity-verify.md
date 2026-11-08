# Vérifier un projet Unity depuis un stage aidp (compile gate C1, tests, scénarios C2)

Recette partagée des pipelines `unity-implement`, `unity-review`, `unity-fix` et `unity-test`.
Elle remplace, pour ces pipelines, le `unity-verify.md` batchmode du skill `unity-issue-workflow` :
**l'éditeur Unity reste ouvert pendant toute la file, on ne lance jamais Unity en batchmode** et on
ne ferme jamais l'éditeur. Le verrou `unity-editor` du daemon garantit qu'un seul stage touche
l'éditeur à la fois (pose-le uniquement si ton stage l'exige ; la revue n'utilise pas Unity).

Chemin de ce fichier : `<skill_root>/templates/recipes/unity-verify.md`
(`skill_root` = `$AIDP_SKILL_ROOT`, par défaut `D:\AIDP\skill`).

Les chemins `.aidp/...` sont relatifs à la **racine du projet Unity** (`context.projectRoot`), jamais
au dossier de stage. `.aidp/` est ignoré par git : ne le commite jamais.

## 0.0 Mode : compile gate immédiate ou différée (voie de dev en worktree)

Les flows de dev (`game-code`, `game-art`, `game-map`) tournent en **worktree** : aucun éditeur n'y est
ouvert. Les flows de test (`game-test-*`) tournent dans le checkout principal, éditeur ouvert. Décide
du mode avant tout, pour les stages `implement`, `repro` et `fix` de la revue (`report_from: review`) :

1. `rtk curl -s http://127.0.0.1:3001/api/unity/status` (route absente : regarde le process `Unity.exe`
   et sa ligne de commande `-projectpath`).
2. L'éditeur est ouvert sur `context.projectRoot` (casse et `/`/`\` ignorés) : **mode immédiat**, suis
   §0 à §2 comme avant.
3. Sinon (éditeur fermé, autre projet, ou `projectRoot` est un worktree) : **mode différé**. Ne fais ni
   requête C1 ni requête C8, n'attends aucun fichier de résultat, ne sors **jamais** `blocked:
   unity-editor` ni `blocked: unity-branch` pour cette raison, ne lance pas Unity. Écris le code et les
   tests avec soin (relis-les, vérifie les `using`, les signatures, les noms de tests), commite les
   `.meta` que tu peux écrire à la main seulement si le projet les versionne et que tu connais le GUID
   (sinon laisse l'éditeur les créer au test), et rapporte `verification.compile = "deferred"`,
   `verification.tests = "deferred"` (dans `signals`, `compile_ok: null`, `editmode_failed: null`).
   Un test de reproduction (`repro`) n'est alors pas exécuté : il est écrit et commité, `red` vaut
   `null` et `signals.red` aussi ; le stage ne sort pas `blocked: no-repro` faute de pouvoir le
   lancer. La PR dit « Vérification : compile et tests différés au test Unity (voie de test) ».
4. La compilation et les tests ont lieu au test Unity (`unity-test`, mode immédiat), qui renvoie les
   erreurs en `unity-fix` `report_from: test` dans le checkout principal.

Le stage `unity-test` reste exigeant : éditeur absent = `blocked: unity-editor`, jamais « différé ».

## 0. Joindre l'éditeur (pont fichier)

Les sessions headless (`claude -p`) n'ont pas le MCP Unity : le canal officiel est le **pont fichier**
du package `com.aidp.playtest`, ouvert dans l'éditeur (requêtes dans `.aidp/*/requests/`, résultats
dans `.aidp/*/results/`). Le MCP (`mcp__unity-mcp__Unity_*`) n'est jamais une condition : ne le charge
que si ses outils sont déjà là, et n'attends pas sa connexion.

1. `rtk curl -s http://127.0.0.1:3001/api/unity/status` : `editor.running` doit valoir `true` et
   `editor.projectPath` désigner `context.projectRoot` (casse et `/`/`\` ignorés). Si la route ne répond
   pas, regarde le process `Unity.exe` et sa ligne de commande (`-projectpath`).
2. **Éditeur fermé** ou **autre projet** ouvert : arrête-toi. Réponds `status: blocked`,
   `signals.blocked_reason: "unity-editor"`, avec « blocked: unity-editor » et la cause dans `summary`.
   Ne lance pas Unity, pas de batchmode, pas de computer use pour compiler.
3. Le flow `game-*` travaille dans le checkout principal du projet (`context.projectRoot`), là où
   l'éditeur est ouvert : il a déjà basculé ce checkout sur la branche de l'issue (`git.checkout`) et
   tient le verrou `unity-editor` jusqu'au retour sur la base. Vérifie que l'éditeur est ouvert sur
   `projectRoot` (route `unity/status`, §0.1) et que la branche courante est celle de l'issue / de la PR
   (`rtk git branch --show-current`). Sinon `status: blocked`, `signals.blocked_reason: "unity-branch"`,
   « blocked: unity-branch » et les deux branches dans `summary`. **Jamais de `git switch` /
   `git checkout` de branche dans un stage** : la bascule est faite par le flow, pas par toi.

## 1. Compile gate (contrat C1)

Une compilation = une requête identifiée par un `requestId` unique
(`<stage>-<epoch ms>`, ASCII, sans espace).

1. Dépose `.aidp/compile/requests/<requestId>.json` contenant `{}` : le pont fichier le prend. Écris
   le fichier une seule fois, d'un coup (écris-le sous un nom temporaire puis renomme-le). Le pont peut
   mettre quelques secondes à répondre pendant un domain reload.
2. Attends `.aidp/compile/results/<requestId>.json` : teste sa présence toutes les 5 s, **timeout
   600 s**. Une éventuelle recompilation ne démarre pas tant que le fichier n'existe pas.
3. Lis-le :
   ```json
   { "id": "...", "ok": true, "errors": [ { "file": "Assets/...cs", "line": 12, "column": 5, "message": "CS0103: ..." } ],
     "warnings": 3, "durationMs": 8400, "unityVersion": "6000.6.7f1", "finishedAt": "..." }
   ```
   - `ok: true` : compile gate vert. Les warnings des fichiers que tu as touchés se corrigent aussi.
   - `ok: false` : corrige chaque erreur (`file:line`) et relance une **nouvelle** requête. Au plus
     5 requêtes par stage ; ensuite le stage échoue (`status: failed`) avec la dernière liste.
   - Pas de fichier au bout de 600 s : regarde la fin de `<projectRoot>/Logs/Editor.log` (fenêtre
     modale, domain reload bloqué, package absent), puis sors `blocked: unity-editor`.
4. Rapporte dans le JSON du stage : `verification.compile` = `{ ok, errors, warnings, durationMs,
   requestId }`. Ne déclare jamais `ok` pour une compilation qui n'a pas tourné.

Shaders : le gate C1 les couvre si Unity les compile ; cherche `Shader error in` dans `Logs/Editor.log`.

## 2. Tests EditMode et PlayMode

Après un compile gate vert seulement.

- Lance les tests par l'éditeur ouvert (contrat C8), un `requestId` par mode (`<stage>-<epoch ms>`) :
  dépose `.aidp/test-results/requests/<requestId>-<mode>.json` contenant `{}` (`<mode>` = `EditMode`
  puis `PlayMode`), le pont le prend. N'écris pas à la main d'appel `TestRunnerApi`.
- Attends `.aidp/test-results/<requestId>-<mode>.json` (timeout 300 s EditMode, 600 s PlayMode ;
  teste sa présence toutes les 5 s). Format :
  ```json
  { "id": "...", "mode": "EditMode", "total": 42, "passed": 41, "failed": 1, "skipped": 0, "durationMs": 9000,
    "failures": [ { "name": "Ns.Class.Test", "message": "...", "stack": "..." } ], "finishedAt": "..." }
  ```
  Pas de fichier au délai : `blocked: unity-editor`.
- `total: 0` avec `"note": "no-tests"` (aucune assembly de tests du mode) : `tests: none` (pas un échec, mais dis-le).
- Un test qui échoue est un échec du stage, sauf pour le stage `repro` où le rouge est attendu.
- Un nouveau fichier sous `Assets/` a besoin de son `.meta` : l'éditeur ouvert l'a créé, `rtk git status`
  doit le montrer, commite-le avec le fichier. Ne commite jamais `Library/`, `Temp/`, `Logs/`,
  `UserSettings/`, `obj/`, `*.csproj`, `*.sln`, `.aidp/`. Si l'éditeur a réécrit `ProjectSettings/*.asset`
  ou `Packages/packages-lock.json` sans que ton changement l'exige : `rtk git restore` ces fichiers.

## 3. Scénarios PlaytestDriver (contrat C2)

Un scénario par critère `CA-n` de l'issue (et par `T-n` manuel jouable), en données, dans
`Assets/Tests/Playtest/Scenarios/issue-<n>-ca<k>.json` (bibliothèque de non-régression, commitée par
`unity-implement` ou `unity-fix`, jamais par `unity-test`). Une demande ponctuelle va dans
`.aidp/playtest/requests/<id>.json` (même schéma, non commitée).

```json
{ "id": "issue-214-ca2", "scene": "Assets/Scenes/Level_1.unity", "timeoutMs": 10000,
  "setup": [ { "cmd": "teleport", "x": 12, "y": 3 }, { "cmd": "give", "ability": "dash" } ],
  "steps": [ { "hold": "rightArrow", "ms": 300 }, { "press": "x" }, { "wait": 400 }, { "capture": "after-dash" } ],
  "assert": [ "player.x > 17.5", { "expr": "player.grounded == true", "withinMs": 500 }, "player.hp == 3" ] }
```

- Steps : `hold` (touche + `ms`), `press`, `release`, `tap`, `wait` (ms), `capture` (nom). Touches =
  noms de `UnityEngine.InputSystem.Key` en camelCase ; manette `gamepad.<control>` en option.
- Asserts : `<sonde>.<champ> <op> <valeur>`, op `== != < <= > >=`, `~=` avec tolérance
  (`player.x ~= 17.5 ± 0.2`) ; forme objet avec `withinMs` (vrai au moins une fois dans le délai).
- Sondes (`[PlaytestProbe("player")]`) et commandes (`[PlaytestCommand("teleport")]`) : celles du jeu
  vivent dans `Assets/Scripts/Playtest/`. Une sonde ou une commande qui manque pour un critère est un
  point à implémenter (stage `implement` ou `fix`), pas à contourner par un test faux.

Lancer un scénario :
1. Dépose le scénario dans `.aidp/playtest/requests/<id>.json` (copie du fichier de
   `Assets/Tests/Playtest/Scenarios/` pour un scénario de la bibliothèque) : le pont (FileSystemWatcher)
   l'exécute et gère l'entrée et la sortie de Play Mode.
2. Attends `.aidp/playtest/results/<id>.json` (timeout = `timeoutMs` du scénario + 60 s ; pas de
   polling plus serré que 3 s).
3. Lis-le :
   ```json
   { "id": "...", "passed": false, "durationMs": 4200,
     "asserts": [ { "expr": "player.x > 17.5", "passed": false, "actual": 16.9, "message": "..." } ],
     "captures": [ ".aidp/playtest/results/<id>/after-dash.png" ], "gif": null, "log": [], "error": null }
   ```
   `passed: false` ou `error` non nul = scénario KO ; garde `expr`, `actual`, `message` comme preuve.
   `gif: null` est normal quand `D:\DevTools\ffmpeg\bin\ffmpeg.exe` n'existe pas.
4. Le résultat ne vient jamais d'une capture d'écran ni du computer use : seulement du fichier de
   résultat. Pas de fichier au délai : `blocked: unity-editor`.

Preuves : mets dans le commentaire de PR le tableau scénario / critère / résultat / valeurs, et les
captures utiles (copie-les sous `Docs/` ou joins-les selon `references/github.md` du skill
`unity-issue-workflow` ; sans cela, cite leur chemin `.aidp/...`).

## 4. Critère `needs-feel-check`

Un critère de « feeling » (rythme, sensation, lisibilité visuelle) que seule une session humaine peut
juger porte `needs-feel-check` dans l'issue. Aucune sonde ne le tranche : ne l'invente pas. Les autres
critères se testent normalement ; le stage conclut `blocked` avec `signals.blocked_reason:
"feel-check"` et la liste de ces critères (un check manuel dans une session Desktop).

## 5. Sorties de statut, rappel

| Situation | Réponse du stage |
|---|---|
| Éditeur fermé ou sur un autre projet, stage `implement` / `repro` / `fix` de revue | pas de blocage : mode différé (§0.0), `verification.compile = "deferred"` |
| Éditeur fermé ou sur un autre projet, stage `unity-test` ; ou pas de résultat C1 / C2 / C8 au délai éditeur ouvert | `blocked`, `signals.blocked_reason: "unity-editor"` |
| Branche courante du checkout différente de celle de l'issue | `blocked`, `signals.blocked_reason: "unity-branch"` |
| Critère `needs-feel-check` à juger | `blocked`, `signals.blocked_reason: "feel-check"` |
| Erreurs de compilation que tu ne sais pas corriger en 5 requêtes | `failed`, liste `file:line` |
| Scénario ou test KO | pas un blocage : `completed` avec `passed: false` (pipelines `unity-test`) |
