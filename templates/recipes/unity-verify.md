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

## 0. Joindre l'éditeur (MCP Unity)

Les outils `mcp__unity-mcp__Unity_*` sont différés : charge-les avec ToolSearch
(`select:mcp__unity-mcp__Unity_RunCommand,mcp__unity-mcp__Unity_ManageEditor,mcp__unity-mcp__Unity_ReadConsole`).

1. `Unity_ManageEditor` `{ Action: "GetProjectRoot" }` doit répondre avec `context.projectRoot`.
2. **MCP muet** (outil absent, erreur de connexion, délai dépassé) ou **autre projet** ouvert :
   arrête-toi. Réponds `status: blocked`, `signals.blocked_reason: "unity-mcp"`, avec dans `summary`
   « blocked: unity-mcp » et la cause (outil introuvable, MCP injoignable, projet différent). Ne
   lance pas Unity, ne tente pas le batchmode, ne passe pas au computer use pour compiler.
3. Ne change jamais de branche pendant que l'éditeur est ouvert : la branche courante doit être celle
   de la PR (`rtk git branch --show-current`).

## 1. Compile gate (contrat C1)

Une compilation = une requête identifiée par un `requestId` unique
(`<stage>-<epoch ms>`, ASCII, sans espace).

1. Appel par le MCP, avec `Unity_RunCommand` (gabarit `CommandScript` de l'outil) :
   ```csharp
   Aidp.Playtest.Editor.CompileGate.Request("<requestId>");
   ```
   Retour immédiat : la compilation n'est pas finie.
   Repli si `Unity_RunCommand` refuse : dépose `.aidp/compile/requests/<requestId>.json` contenant
   `{}` (le pont fichier le prend).
2. Attends `.aidp/compile/results/<requestId>.json` : teste sa présence toutes les 5 s, **timeout
   180 s**. Une éventuelle recompilation ne démarre pas tant que le fichier n'existe pas.
3. Lis-le :
   ```json
   { "id": "...", "ok": true, "errors": [ { "file": "Assets/...cs", "line": 12, "column": 5, "message": "CS0103: ..." } ],
     "warnings": 3, "durationMs": 8400, "unityVersion": "6000.6.7f1", "finishedAt": "..." }
   ```
   - `ok: true` : compile gate vert. Les warnings des fichiers que tu as touchés se corrigent aussi.
   - `ok: false` : corrige chaque erreur (`file:line`) et relance une **nouvelle** requête. Au plus
     5 requêtes par stage ; ensuite le stage échoue (`status: failed`) avec la dernière liste.
   - Pas de fichier au bout de 180 s : `Unity_ReadConsole` `{ Types: ["Error"] }` pour diagnostiquer
     une fenêtre modale ou un domain reload bloqué, puis sors `blocked: unity-mcp` (la compilation
     ne répond plus).
4. Rapporte dans le JSON du stage : `verification.compile` = `{ ok, errors, warnings, durationMs,
   requestId }`. Ne déclare jamais `ok` pour une compilation qui n'a pas tourné.

Shaders : le gate C1 les couvre si Unity les compile ; ajoute `Unity_ReadConsole` pour `Shader error in`.

## 2. Tests EditMode et PlayMode

Après un compile gate vert seulement.

- Lance les tests par l'éditeur ouvert (contrat C8), un `requestId` par mode
  (`<stage>-<epoch ms>`) : `Unity_RunCommand` avec
  ```csharp
  Aidp.Playtest.Editor.TestGate.Request("<requestId>", "EditMode"); // puis "PlayMode"
  ```
  Retour immédiat. Repli si `Unity_RunCommand` refuse : dépose
  `.aidp/test-results/requests/<requestId>-<mode>.json` contenant `{}` (le pont le prend). N'écris
  pas à la main d'appel `TestRunnerApi`.
- Attends `.aidp/test-results/<requestId>-<mode>.json` (timeout 300 s EditMode, 600 s PlayMode ;
  teste sa présence toutes les 5 s). Format :
  ```json
  { "id": "...", "mode": "EditMode", "total": 42, "passed": 41, "failed": 1, "skipped": 0, "durationMs": 9000,
    "failures": [ { "name": "Ns.Class.Test", "message": "...", "stack": "..." } ], "finishedAt": "..." }
  ```
  Pas de fichier au délai : `blocked: unity-mcp`.
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
1. Par le MCP : `Unity_RunCommand` avec `Aidp.Playtest.Editor.PlaytestBridge.Run("<id>");` (le
   scénario est cherché dans `Assets/Tests/Playtest/Scenarios/` puis dans `.aidp/playtest/requests/`).
   Repli : dépose `.aidp/playtest/requests/<id>.json`, le pont (FileSystemWatcher) l'exécute.
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
   résultat. Pas de fichier au délai : `blocked: unity-mcp`.

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
| MCP Unity muet, éditeur d'un autre projet, pas de résultat C1 / C2 au délai | `blocked`, `signals.blocked_reason: "unity-mcp"` |
| Critère `needs-feel-check` à juger | `blocked`, `signals.blocked_reason: "feel-check"` |
| Erreurs de compilation que tu ne sais pas corriger en 5 requêtes | `failed`, liste `file:line` |
| Scénario ou test KO | pas un blocage : `completed` avec `passed: false` (pipelines `unity-test`) |
