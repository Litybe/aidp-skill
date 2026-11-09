# Mémoire et RAG dans un stage aidp (contrat C10)

Recette partagée des pipelines `unity-*`, `art-*`, `map-*` et `doc-*`. Elle dit comment un agent lit
la mémoire du projet, cherche dans le corpus sans lire la BIBLE ou le code en entier, et propose des
leçons à la fin de son run.

Chemin de ce fichier : `<skill_root>/templates/recipes/memory.md` (`skill_root` = `$AIDP_SKILL_ROOT`).
Les commandes `aidp rag ...` et `aidp memory ...` viennent du binaire `aidp` ; toutes se lancent avec
le préfixe `rtk` comme les autres commandes des stages. Sortie `--format md` par défaut (la lecture
est faite pour des agents).

## 1. Lire la mémoire (stage `prepare`)

Le stage `prepare` lance, une fois par run, depuis la racine du projet :

```
rtk aidp memory context --project "<projectRoot>" --issue GH-<n> --route <code|art|map|doc> --stage <stage suivant> --budget 2000
```

- `--project` : chemin du projet (`context.projectRoot`) ou sa clé.
- `--issue` : `GH-<numéro>` ; sans issue, retire l'option.
- `--route` : `code` pour `unity-*`, `art`, `map`, `doc`.
- `--stage` : id du premier stage qui suit `prepare` (ex. `plan`, `review`, `fix`, `test`, `brief`,
  `import`, `graph`, `write`), il filtre les mémoires dont la portée correspond.
- `--budget 2000` : tokens (≈ caractères / 4). Ne l'augmente pas.

La sortie est écrite **telle quelle** dans `memory-context.md` du dossier de stage `prepare`. Les
stages suivants la reçoivent dans leur entrée `memory` (`{{ stages.prepare.outputs.memory-context }}`).
Un stage qui reçoit `memory` :

- applique les mémoires actives (décisions, conventions, pièges) comme des contraintes du projet ;
  une mémoire n'est pas un ordre de l'issue : en cas de conflit, l'issue et la BIBLE gagnent, et le
  conflit est noté dans le rapport ;
- cite `path:Lx-Ly` (le format des extraits) quand il s'appuie sur un extrait ;
- ne recopie pas le bloc dans le rapport.

## 2. Chercher à la demande (au lieu de lire en entier)

Ne lis jamais toute la BIBLE ni un gros fichier de code pour une seule information. Lis l'index
(`.claude/BIBLE/00_INDEX/`) pour savoir où regarder, puis :

```
rtk aidp rag search "<requête courte>" --project "<projectRoot>" [--source bible,doc,code,run,ticket,knowledge] [--path "<glob>"] [--k 20] --budget 1500
```

- Requête : les mots du domaine (nom de capacité, id `R<n>_<nn>_<rôle>`, nom de classe), pas une phrase.
- `--source bible` pour le canon, `code` pour une classe ou une méthode, `run` pour les plans, revues
  et rapports d'anciens runs, `ticket` pour les tickets miroirs.
- Chaque extrait porte sa citation `path:Ldébut-Lfin`. Ouvre ensuite **seulement** ces lignes
  (`Read` avec `offset`/`limit`) si l'extrait ne suffit pas.
- Plusieurs requêtes courtes valent mieux qu'une grosse ; garde `--budget` à 1500 ou moins.
- Un résultat vide n'est pas une preuve d'absence : l'index peut être en retard. Ne lance pas
  `aidp rag index` toi-même (le daemon le fait) ; repasse par la lecture ciblée du fichier.

## 3. Proposer des leçons (derniers stages de revue, correction et test)

Les stages `verdict` des `*-review` et de `unity-review`, `fix` des `*-fix` et de `unity-fix`,
`test` de `unity-test`, `report` de `art-import` et de `map-test` écrivent `memory-proposals.json`
dans leur dossier de stage, même vide :

```json
{ "proposals": [
  { "kind": "gotcha", "title": "Vitesse du Rigidbody2D en FixedUpdate",
    "text": "Écrire la vitesse horizontale hors de FixedUpdate est écrasé par le dash : passer par PlayerMotor.SetVelocity.",
    "scope": { "route": "code", "paths": ["Assets/Scripts/Player/**"], "tags": ["physics"] },
    "refs": [ { "type": "issue", "id": "GH-214" }, { "type": "pr", "id": "231" } ],
    "confidence": 0.7 } ] }
```

Règles :

- **Ce format exact, aucun autre champ** : pas de `type`, `name`, `description`, `body`, `lesson`,
  `why` ; ce n'est pas le format de l'auto-memory de Claude.
- **5 au plus**, souvent 0 ou 1. `{ "proposals": [] }` est une réponse normale.
- Seulement une leçon **non évidente et réutilisable** sur un autre ticket : un piège découvert, une
  convention du projet que le code ne montre pas, une décision et sa raison, une cause racine.
- Jamais : un résumé de l'issue ou de la PR, ce que le diff montre déjà, une information déjà dans la
  BIBLE ou dans la mémoire reçue (vérifie avec `rtk aidp rag search`), un état temporaire.
- `kind` ∈ `decision | convention | lesson | gotcha | preference | fact`.
- `title` court et précis ; `text` ≤ 600 caractères, actionnable (quoi faire ou éviter, et pourquoi).
- `scope` précis : `route` (`code|art|map|doc`), `paths` (globs étroits, pas `**`), `tags`. Une leçon
  sans portée est lue par tout le monde et noie les autres.
- `refs` : l'issue (`GH-<n>`) et la PR de ce run.
- `confidence` ∈ [0, 1], honnête : 0,9 et plus = vérifié par un test ou une mesure dans ce run ;
  0,6 à 0,8 = observé une fois ; moins de 0,5 = intuition. Ne gonfle pas pour atteindre le seuil
  d'activation automatique (0,8 avec `evidence` ≥ 2).
- N'invente rien : une leçon sans preuve dans ce run n'est pas proposée.

Le daemon ingère ces fichiers à la fin du run (`aidp memory ingest`) ; tu n'appelles ni
`aidp memory add` ni `aidp memory approve`. Une proposition proche d'une mémoire existante en augmente
l'`evidence` sans créer de doublon ; l'approbation reste humaine sauf seuil atteint.

## 4. Si une commande échoue

La mémoire est un confort, jamais un prérequis.

- `aidp memory context` en erreur (commande inconnue, base absente, délai) : `prepare` écrit
  `memory-context.md` avec la seule ligne « Mémoire indisponible : <cause courte> », ne bloque pas,
  et continue. Les stages suivants travaillent sans mémoire.
- `aidp rag search` en erreur : lis le fichier visé par l'index de la BIBLE, par plages de lignes.
- Dans tous les cas, signale-le dans le rapport du run (une ligne « Mémoire : indisponible, <cause> »)
  pour que l'utilisateur voie que le branchement est cassé. Ne marque pas le run `blocked`.
- Si tu ne peux pas écrire de leçon fiable, écris `{ "proposals": [] }` ; n'omets pas le fichier.
