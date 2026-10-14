# Analyse de l'animation Z80 (AMSpiriT, chargée via un fichier SNA glissé)

Notes vivantes, mises à jour au fur et à mesure de l'investigation via l'API
REST de l'émulateur AMSpiriT (localhost:6128). Aucun assembleur source n'est
encore fourni : tout ce qui suit vient de l'inspection dynamique (registres,
RAM, écran) et d'un désassembleur Z80 maison (aucun outil de ce type n'était
installé sur la machine).

**Correction importante (2026-09-17) :** l'animation observée n'a **aucun
rapport avec "SHAKER-C-3.CSL"**. Ce script CSL était juste ce qui tournait au
lancement du process AMSpiriT ; l'animation vient en réalité d'un fichier
`.SNA` glissé-déposé dans l'émulateur ensuite, qui a chargé l'état RAM/CPU
actuel. Le titre de ce document a été corrigé en conséquence. Le script CSL
reste "running" côté `/api/script` mais ce n'est plus pertinent pour ce
travail — il occupe juste le moteur d'eval Lua (`/api/eval` renvoie `busy`
tant qu'il tourne).

## 0. Contexte d'exécution

- Process : `amspirit-lite-qt --script SHAKER-C-3.CSL --ssm ../shaker27.dsk --debug-script`
  (sans rapport avec l'animation, cf. correction ci-dessus).
- Animation réelle chargée via un `.SNA` déposé sur l'émulateur après coup.
- API dispo sur `http://127.0.0.1:6128` (⚠️ `localhost` résout mais la
  connexion échoue depuis certains contextes sandboxés — utiliser `127.0.0.1`).
- Aucun ROM/BASIC actif : `memmap` = 4 banques RAM pures (pas de flag `rom`),
  `basic_state.prog_size = 2` (programme BASIC vide). C'est donc du code
  machine pur, chargé directement en RAM par le script CSL/disque, pas un
  loader BASIC classique.
- `emu.cpc_model = 2`, `crtc_type = 1`.
- Le programme tourne en continu (`paused:false`), mais deux lectures
  successives de `/api/z80` (à 1s d'intervalle) donnent le **même PC = 740
  (0x02E4)** avec `R` qui a bien avancé (59 → 107) : le point d'échantillonnage
  HTTP tombe systématiquement sur un même point de synchronisation par frame
  (probablement un hook du script CSL/debug), pas un vrai gel du CPU.
- **Assembleur `fantams` fourni (2026-09-17)** dans le répertoire courant
  (`./fantams`, binaire, syntaxe décrite dans `./syntax.md`) — pour plus
  tard, quand on écrira des variantes de l'effet. Usage (`fantams` sans
  argument affiche l'aide) :
  `fantams file.asm [-o out] [-s] [-E] [--strict] [--target cpc6128|cpcplus]
  [-P profil] [-T script.ld] [--sym[=out.sym]] [--dump-profile N]`.
  Pas encore utilisé pour l'instant (on est encore côté désassemblage).
- Tous les fichiers de travail (dumps RAM, désassembleur maison,
  screenshots) vivent maintenant dans `./scratchpad/` (répertoire courant,
  non versionné) plutôt que dans le scratchpad temporaire de session —
  gardés d'une session à l'autre.
- **Compendium CRTC fourni (2026-09-17)** dans `./compendium-crtc/`
  (conversion Markdown du *Amstrad CPC CRTC Compendium V1.11*, Longshot/Logon
  System). Référencé ci-dessous — il a permis de corriger et de confirmer
  plusieurs hypothèses (§5.1, §5.8). **PDF original ajouté ensuite** dans
  `./compendium-crtc/source/ACCC1.11-FR.pdf` (295 pages) : consulté pour les
  chapitres 10-12 (R9/R5/R4, ruptures), non couverts par la conversion
  Markdown initiale — extrait ajouté dans
  `compendium-crtc/05-comptages-r9-r5-r4-ruptures.md`, coquille
  "RHAL"→"R.L.A.L." corrigée dans `glossaire.md`. Le texte a suffi ; les
  schémas/chronogrammes complexes du PDF n'ont pas été nécessaires ici.

## 1. Endpoints API utiles pour ce travail

Découverts via `/api/doc` puis `/api/doc/<nom>` :

- `/api/ram?addr&len&bank&view` (GET) — dump hexa RAM. `view=cpu` applique le
  mapping mémoire courant (utile ici puisqu'il n'y a pas de ROM en jeu).
- `/api/codemap` (GET/DELETE) — bitmap des 65536 adresses atteintes par le
  Z80 depuis le dernier reset du bitmap. **Essentiel** pour distinguer le
  vrai code exécuté des tables de données au milieu du binaire.
- `/api/history` — dernières instructions exécutées (pc + 4 octets bruts +
  registres), sans paramètre de taille.
- `/api/z80`, `/api/crtc`, `/api/ga`, `/api/psg` — snapshots des puces.
- `/api/screenshot` — PNG de la frame courante.
- `/api/script` — statut du script CSL (`running`, capture de `print()`).
- `/api/exec`, `/api/ram` (POST) — pour plus tard : relocaliser le PC,
  patcher de la RAM, tester des variantes sans recompiler.
- `/api/step`, `/api/z80_bp`, `/api/raster_bp` — pas-à-pas et breakpoints,
  utile pour la suite quand on voudra tracer précisément le rendu.

**Pas de désassembleur côté API.** Vérifié explicitement : `/api/doc` ne
liste aucun endpoint de désassemblage, `/api/doc/step` et `/api/doc/eval`
ne renvoient rien de plus (juste `{ok}` / `{ok,seq}`), et `/api/history` ne
renvoie que les octets bruts (`hex`) + registres, jamais de mnémonique. Le
moteur Lua sandboxé de `/api/eval` pourrait en théorie exposer une fonction
de désassemblage, mais il est actuellement bloqué (`busy`) par le script CSL
`SHAKER-C-3.CSL` toujours en cours d'exécution — à retester si on l'arrête
(`DELETE /api/script`, pas encore fait, à confirmer avec toi avant de le
stopper puisqu'il n'était pas lancé par nous). Pour l'instant, le
désassembleur maison `scratchpad/z80dis.py` reste la seule option.

## 2. Empreinte du code

Via `/api/codemap`, la totalité des adresses exécutées tient dans une
fenêtre étroite :

```
min 0x015F  max 0x0572   (721 adresses marquées exécutées sur cette plage)
```

**Sémantique du bitmap, précisée (2026-09-17) :** `/api/codemap` ne marque
que l'adresse de **fetch de l'opcode** (le premier octet de chaque
instruction), pas les octets d'opérande qui suivent. Une instruction 3 octets
(`LD BC,nn`, par ex.) ne laisse donc qu'1 bit sur 3 dans le bitmap — les
"trous" entre bits marqués sont normaux et **ne veulent pas dire "donnée, pas
exécutée"**. Pour savoir si une zone est vraiment inerte, il faut regarder si
elle a **zéro bit marqué sur toute sa longueur**, pas juste "des trous".

⚠️ Correction d'une erreur d'analyse précédente : la zone ~0x02DC–0x04E5
n'est **pas** une table de données inerte — elle est en fait exécutée quasi
octet par octet (voir §5.3bis). C'est le signe d'un point d'entrée qui varie
selon l'appel (voir plus bas), pas d'une donnée statique.

## 3. Outillage : désassembleur Z80 maison

Aucun désassembleur Z80 (z80dasm, sjasmplus, etc.) n'était disponible sur la
machine. Un désassembleur minimal a été écrit
(`scratchpad/z80dis.py`, basé sur le schéma de décodage x/y/z/p/q) :
couvre les opcodes non préfixés, `CB`, `ED`, `DD`/`FD` (registres IX/IY et
`(IX+d)`/`(IY+d)`). Suffisant pour ce binaire (pas de `DDCB`/`FDCB` observé).
Usage : `python3 z80dis.py ram_dump.bin <base> <offset> <longueur>`.

## 4. Ce qu'on voit à l'écran

Deux captures à 1s d'écart diffèrent sur ~4700 pixels/416k (~1%) : il y a
bien une animation en cours, mais discrète. Visuellement (`screenshot1.png`) :

- fond noir,
- une ligne horizontale violette (haut-gauche),
- **deux traînées diagonales** avec un dégradé de couleur identique :
  magenta → rose → blanc → cyan → bleu → rouge → jaune,
- les deux traînées bougent légèrement d'une frame à l'autre.

→ Hypothèse de travail : effet **"étoile filante" / meteor** à trajectoire
diagonale, tracé via une petite table de dégradé de couleurs, pas de
sprite/bitmap complexe. Cohérent avec la taille du code (~1 Ko utile).

## 5. Blocs de code identifiés (0x015F–0x0572)

Adresses en hexa. Toujours des hypothèses à confirmer une fois l'assembleur
source disponible — noté "(TBD confirmer)" quand l'interprétation est
incertaine.

### 5.1 `0x015F` — Init CRTC : rupture ligne à ligne (R.L.A.L.) — confirmée par le PDF source, chapitre 12.3

```
015F  LD BC,#BC07 / OUT (C),C     ; sélection registre CRTC R7 (position VSYNC)
0164  INC B / OUT (C),B           ; écrit 0xBD dans R7 → position VSYNC = 0xBD
0167  LD BC,#BC09 / OUT (C),C     ; sélection R9 (hauteur caractère - 1)
016C  LD BC,#BD00 / OUT (C),C     ; R9 = 0   → 1 ligne raster par "caractère"
0171  LD BC,#BC04 / OUT (C),C     ; sélection R4 (total vertical)
0176  LD BC,#BD00 / OUT (C),C     ; R4 = 0   → trame ultra-courte
```

**Correction finale (2026-09-17)**, après consultation du **PDF original**
du compendium (`compendium-crtc/source/ACCC1.11-FR.pdf`, fourni parce que la
conversion Markdown n'incluait pas les chapitres 10-29). J'avais affirmé à
tort dans un tour précédent que ce montage était *la* technique "RFD" —
c'était une déduction invalide (RFD marche sur CRTC 1 ⇏ tout ce qui marche
sur CRTC 1 est du RFD), comme tu l'as fait remarquer. Après lecture du
chapitre 11.6 (RFD) et 12.1-12.3 (comptages R4), les deux points sont
maintenant tranchés :

1. **La RFD est exclue.** Sa recette précise (chapitre 11.6, PDF p.89) est
   une transition de **R5** de 0 vers une valeur non nulle (`OUT R5,1` puis
   `OUT R5,0`) — un bug spécifique au CRTC 1 sur ce registre précis, sans
   rapport avec R4/R9. **Aucune écriture dans R5 n'existe nulle part dans le
   binaire** (recherche exhaustive dans le dump RAM complet des motifs
   `LD BC,#xx05` et `LD C,#05` — zéro résultat). Donc ce n'est pas de la RFD.

2. **C'est la technique documentée sous le nom R.L.A.L.** ("Rupture Ligne à
   Ligne", chapitre 12, PDF p.94-96 — le glossaire du compendium avait une
   coquille, "RHAL", corrigée). Citation exacte du chapitre **12.3 CRTC 1**
   (PDF p.96) :
   > "Créer une rupture ligne à ligne sur ce CRTC est trivial, car il suffit
   > de mettre R4 et R9 à 0 lorsque C4 et C9 sont à 0. Si vous souhaitez la
   > simplicité, utilisez ce circuit."

   C'est **exactement** ce que fait le code : `R9=0` puis `R4=0`, posés en
   une seule passe d'init (donc à `C4=C9=0`, en tout début de frame — la
   condition requise par le texte). Sur CRTC 1, contrairement à CRTC 0/2,
   aucune gestion de "dernière ligne" n'est nécessaire : c'est la voie la
   plus simple des trois, explicitement présentée comme telle par l'auteur.
   Détails complets, citations et contexte : `compendium-crtc/05-comptages-r9-r5-r4-ruptures.md`.

**⇒ Ça relie directement à la boucle du §5.8** : les 240 itérations qui
réécrivent R13 (`OUT (C),A` à `0x0252`) exploitent ce rechargement de MA à
chaque ligne, permis par la R.L.A.L. posée ici. La boucle de calibration
VSYNC (§5.7, `0x0510`) reste, elle, une routine séparée (utilitaire de
détection CRTC générique) — sans rapport avec ce mécanisme.

### 5.2 `0x017B` — Écriture Gate Array (port 0x7Fxx)
```
017B  LD BC,#7F00 / OUT (C),C     ; GA, valeur 0x00
0180  LD C,#54 / OUT (C),C        ; GA, valeur 0x54
```
`0x54` colle avec `ga.border_idx = 20` observé sur `/api/ga` (0x54 & 0x1F =
0x14 = 20). (TBD confirmer le format exact de commande GA utilisé ici.)

### 5.3 `0x0184` — Construction de 4 positions écran + copie de motif
```
0184  CALL 0x02DC          ; calcule une valeur de "pas" (stride) dans (0x0302)
0187  PUSH HL / LD DE,#C038 / CALL 0x02FD / POP HL   ; position écran #1
018F  LD DE,(0x0302) / ADD HL,DE ...                  ; position #2 = #1 + pas
       (répété pour DE=#C098 et DE=#C0F8, puis DE=#C158)
```
`0x02DC` calcule `HL = 0x8000 - 37 * n` (n lu dans une petite table
auto-générée) : un calcul d'adresse en "pas de 37 octets" — cohérent avec un
buffer/plan hors-écran de largeur 37, utilisé comme table d'offsets diagonale
pour les 2 traînées vues à l'écran.

### 5.3bis `0x02FD`–`0x04EA` — Matrice de temporisation cycle-exacte (SP détourné)

Appelée 3 fois depuis §5.3 (une par position d'écran). Désassemblage précis
(après correction, cf. §2) :
```
02FD  LD (0x04EB),SP     ; sauve le vrai SP dans une variable
0301  LD SP,#002D        ; charge une CONSTANTE dans SP (détournement : SP
                          ;   n'est plus un pointeur de pile ici, mais un
                          ;   opérande 16-bit qu'on va additionner)
0304  LD B,#10           ; compteur (16), rôle exact encore TBD
0306  ADD HL,SP           ; 11 T-states, ajoute la "constante" à HL
0307  LD C,H / LD A,(BC) / EX AF,AF'   ; suite du bloc unitaire (~variable)
       ... (bloc de ~12-13 octets répété, ADD HL,SP / LD C,H / LD A,(BC) /
            [EX AF,AF' | RRCA;LD C,A;EX AF,AF'] / OR C / LD (DE),A / INC DE)
       ... répété en continu jusqu'à ~0x04E5
04E6  LD SP,(0x04EB)     ; restaure le vrai SP
04EA  RET
```
**Pourquoi le bitmap `codemap` marque presque CHAQUE octet comme point de
départ d'instruction dans cette zone** (vérifié : de `0x300` à `0x4E5`,
quasiment 100% des adresses sont des débuts d'opcode observés) : ça ne peut
pas arriver en une seule passe d'exécution séquentielle (une instruction de
2-3 octets laisserait des trous). La seule explication cohérente est que
**le point d'entrée dans ce bloc change d'un appel à l'autre** (calculé,
probablement à partir de `n`/du "pas" de §5.3, ou de la valeur chargée en
`SP` à 0x0301) : sur de nombreuses frames cumulées, l'exécution est entrée à
des décalages différents dans ce bloc unitaire répété, ce qui finit par
marquer presque tous les octets comme point de départ au moins une fois.

**Hypothèse révisée (2026-09-17), après avoir localisé l'écriture réelle de
R13 ailleurs (§5.8) :** ce n'est **pas** une temporisation — c'est plus
probablement une **routine de tracé à longueur variable, entrée à un offset
calculé dans une séquence déroulée**. Le bloc unitaire répété fait
`LD (DE),A ; INC DE` (écrit un octet en `(DE)` et avance `DE`) : `DE` est un
pointeur écran passé par l'appelant (`#C038`, `#C098`, ... cf. §5.3), et la
valeur écrite (`A`) vient d'une table lue via `HL`/`SP` (probablement le
motif de dégradé recopié en §5.4). En entrant à un offset différent selon la
position (calculé à partir du "pas" `n`), on ne trace que la **fin** de la
séquence jusqu'à `0x04E6` — ça donne une longueur de tracé différente selon
la position verticale, ce qui **expliquerait la forme effilée/triangulaire**
des deux traînées visibles à l'écran (§4). Le rôle exact de `SP=#002D` et
`B=0x10` reste TBD — probablement liés au calcul de l'offset d'entrée
lui-même, ou à un pas de couleur. **À confirmer avec le vrai source** ou par
un `/api/step` ciblé sur un des 3 points d'appel.

### 5.4 `0x01CB` — Copie du motif de dégradé (6 octets, 2×3)
```
01CB  LD HL,#060C / LD DE,(0x0229) / PUSH HL
01D3  LDI / LDI / LDI            ; copie 3 octets vers (DE) — 1ère moitié
       EX DE,HL / LD BC,#02CD / ADD HL,BC / EX DE,HL
01E0  LDI / LDI / LDI            ; copie 3 octets — 2e moitié, décalée de 0x02CD
```
La source à `0x02CD` est une table cyclique de 16 octets qui ressemble à des
paires 16-bit (`45 4D`, `4F 47`, `43 4B`, ...) plutôt qu'à des index de
couleur directs — **à vérifier avec le vrai source** : ça pourrait être une
table de pointeurs (vecteurs de saut auto-relogés, cf. §5.5) plutôt que les
couleurs du dégradé elles-mêmes. Les vraies couleurs du dégradé visible à
l'écran sont probablement ailleurs (dans `ga.ink_rgb`, déjà 16 valeurs
cohérentes avec une palette CPC standard).

### 5.5 `0x0214`–`0x024D` — Écriture de vecteurs (table de saut / IX-IY)
```
0214  LD IXH,#BD
0217  LD DE,#0EF4 / INC E / LD (0x0218),DE     ; écrit un pointeur en 0x0218
021F  LD HL,#0E23 / DEC L / DEC L / LD (0x0220),HL  ; écrit un pointeur en 0x0220
```
Ressemble à la mise en place de vecteurs de saut/interruption personnalisés
(zone basse de mémoire, cohérent avec `IM 1` observé dans `/api/z80`) — mais
`IFF1=0` (interruptions masquées) au moment du snapshot, donc soit ce n'est
pas encore activé, soit ce n'est pas le mécanisme utilisé pour l'animation.
**À vérifier explicitement avec le source.**

### 5.6 `0x0295` — Chemin de sortie, **jamais pris** (confirmé)
```
0295  DI
0296  LD BC,#DF0A / OUT (C),C
0299  LD BC,#7F86 / OUT (C),C
02A2  JP #E006
```
Dump de `0xE006` (128 octets) : **entièrement à zéro**. Pas un bug de
désassemblage — en croisant avec `/api/codemap`, seules les adresses
`0x0290` (`BIT 2,A`) et `0x0292` (`JP NZ,#015F`) de ce bloc ont été
réellement exécutées ; `0x0295` et la suite (le `DI`/sortie vers `0xE006`)
**n'ont jamais été atteints**. Donc `BIT 2,A` est toujours vrai (bit 2 de A
mis par `CALL #04ED` juste avant) et la boucle ne fait jamais que revenir en
`0x015F` — ce chemin de sortie est du code mort dans l'état actuel (branche
de sortie conditionnelle, probablement liée à une touche/bouton, jamais
déclenchée depuis le chargement du SNA).

**⇒ Ceci révèle la vraie boucle principale de l'animation :**
```
0x015F  (ré-init CRTC/GA, reconstruction des positions/motif) ──┐
                                                                  │
0x028D  CALL #04ED        ; lit un état (clavier/joystick via PSG ?)
0x0290  BIT 2,A
0x0292  JP NZ,#015F   ────┘  (toujours pris jusqu'ici)
0x0295  DI ... JP #E006      (jamais pris — sortie non déclenchée)
```
Pas d'interruption utilisée pour l'affichage : c'est une **boucle de
polling qui refait tout le travail (CRTC, GA, tables, motif) à chaque
passage**, et sort seulement quand `CALL #04ED` renvoie un bit 2 à 0 dans
A (condition de sortie encore non observée). `0x04ED` mérite d'être creusé :
il fait des `OUT`/`IN` sur les ports `0xF4xx`/`0xF6xx`/`0xF7xx` (zone PSG/PPI
sur CPC), cohérent avec une lecture clavier/joystick via le port de données
du AY-3-8912.

### 5.7 `0x0510`–`0x0546` — Boucle de calibration VSYNC (forte confiance)
```
0510  LD B,#F5              ; port PPI B (0xF5xx) = bit0 = signal VSYNC
0512  LD HL,#4DEB / LD DE,#FFF5
0518  IN A,(C) / RRA / JR NC,#0518   ; attend front montant VSYNC
051D  IN A,(C) / RRA / JR C,#051D    ; attend front descendant
0522  IN A,(C) / RRA / JR NC,#0522
0527  ADD HL,DE                     ; accumule une mesure de largeur d'impulsion
0528  IN A,(C) / RRA / JR C,#0527
052D  EX DE,HL / CALL #0546         ; convertit la mesure via table (0x0546)
0546  LD HL,#0572 / ... / SBC HL,BC ; recherche dans une table indexée par
       (bits bas de E) — table de correspondance largeur→type de CRTC
```
Ceci est la signature classique de la **détection logicielle du type de
CRTC** sur CPC (mesurer la largeur du VSYNC via le port PPI B, comparer à des
seuils connus). Très probablement du code utilitaire générique
(bibliothèque), pas la partie "artistique" de l'animation — mais explique
pourquoi `crtc_type` apparaît correctement renseigné dans `/api/ping` malgré
`R4=0/R9=0` appliqués manuellement plus haut.

### 5.8 R12/R13 (adresse de départ écran) — confirmation par observation directe (2026-09-17)

Relancé depuis zéro (nouveau lancement de l'émulateur + rechargement du
`.SNA`), observation manuelle des registres CRTC par toi :
- **R12 = 0x30** → confirme un écran de base en `0xC000` (`0x30 = 0b00110000`,
  bits hauts de l'adresse écran ; cohérent avec les adresses `0xC0xx` déjà
  vues en §5.3).
- **R13 change "assez régulièrement"** — confirmé par échantillonnage :
  12 lectures de `/api/crtc` en ~2s donnent des valeurs de R13 très
  dispersées (107, 169, 11, 109, 159, 13, 64, 158, 13, 59, 153, 105), pas du
  tout un incrément lisse. Écrit dans le code via la même paire
  select/write que R7/R9/R4 (§5.1) : trouvé en `0x0205` (`LD BC,#BC0C /
  OUT(C),C` puis `LD A,#30 / OUT(C),A` → écrit R12=0x30 ; puis
  `INC C` → sélectionne R13, mais **la valeur écrite dans R13 elle-même n'a
  pas été localisée dans ce bloc d'init** — elle est réécrite ailleurs,
  probablement en sortie de la matrice de temporisation du §5.3bis, à un ou
  plusieurs instants précis de la trame).

**⇒ Écriture de R13 localisée et confirmée par breakpoint (2026-09-17).**
Méthode : `POST /api/z80_bp` avec la liste des 33 adresses `OUT (C),r`
trouvées dans l'empreinte de code (§2), puis boucle `POST /api/config
{"paused":false}` → attendre le prochain arrêt → lire `/api/z80`, répétée
~40 fois en inspectant `PC`/`B`/`C`/`A` à chaque arrêt.

**Résultat : `PC=0x0252` (`OUT (C),A`) s'arrête avec `B=0xBD` (port
d'écriture CRTC) et une valeur de `A` différente à chaque déclenchement**
(0, 111, 159, 64, 112, 160, 65, 112, 160, 64, 65, 160...) — c'est
l'instruction qui écrit R13. Elle vit dans une **vraie boucle** (pas un
déroulé), `0x024E`–`0x0275`, comptée par `IX` (`L` bas, i.e. IXL) de 240
(`0xF0`) à 0 :

```
0247  LD DE,#8C8F
024A  EXX                    ; bascule vers le jeu de registres alternatif
024B  LD IXL,#F0             ; compteur de boucle = 240 itérations
024E  LD A,(DE)              ; table 1, indexée par E (page 0x8C)
024F  ADD A,(HL)             ; + table 2, indexée par L
0250  LD C,A                 ; C = offset combiné (0-255)
0251  LD A,(BC)              ; lit RAM[0xBDxx + C]  ← table de 256 valeurs R13
0252  OUT (C),A              ; ★ écrit R13 (B toujours = 0xBD ici)
0254  INC E                  ; avance dans la table 1
0255  INC L                  ; avance dans la table 2
0256  EXX                    ; revient au jeu de registres principal
0257  LD BC,#7F05
025A  OUT (C),D / OUT (C),C  ; écriture(s) Gate Array (encre ?)
025E  OUTI                   ; + 3× OUTI (bloc de 3 octets, port GA, source HL)
0273  DEC IXL / JR NZ,#024E  ; boucle 240×
```

**⇒ Mécanisme confirmé : à chaque ligne (jusqu'à 240 lignes), le code
recalcule un nouveau départ écran (R13) ET pousse 3 octets de palette (GA)
via `OUTI`.** C'est un split CRTC ligne-par-ligne : R13 = table1[i]+table2[i]
(mod 256), ce qui explique la dispersion des valeurs de R13 observée à
l'échantillonnage (chaque lecture HTTP tombe sur une ligne différente de ce
balayage). Le décalage horizontal changeant à chaque ligne + les 3 octets de
palette avancés en parallèle (via le même index `L`/`HL` qui parcourt la
petite table copiée en §5.4) sont très probablement **le mécanisme complet
des deux traînées diagonales dégradées** : chaque ligne est légèrement
décalée horizontalement (R13) par rapport à la précédente (→ diagonale) et
prend sa couleur dans la palette dégradée avancée en parallèle (→ dégradé).

C'est une **R.L.A.L.** ("Rupture Ligne à Ligne", chapitre 12 du compendium
— confirmé, pas seulement une hypothèse, cf. §5.1) : le montage `R4=0`/`R9=0`
recharge MA depuis R12/R13 à chaque ligne raster (mécanisme trivial et
documenté sur CRTC 1, chapitre 12.3), et cette boucle de 240 itérations en
profite pour écrire une nouvelle valeur de R13 (+ 3 octets de palette) à
chaque ligne.

**Contenu des tables (dumpé) :**
- `0xBD00` (table 1, la table de R13 elle-même, page complète 256 octets) :
  motif très régulier `00 30 60 90 01 31 61 91 02 32 62 92 03 33 63 93 ...`
  soit `valeur(i) = (i mod 4)×0x30 + (i div 4)`, min 0, max 0xCF (207).
  Confirme totalement l'hypothèse : c'est une table généraliste de calcul
  d'adresse-écran "entrelacée" (le motif ×0x30 rappelle `R12=0x30`), le genre
  de table utilisée pour un effet de wobble/torus-scroll sur l'adresse de
  départ écran plutôt qu'un vrai décalage horizontal ligne à ligne classique.
- `0x8C8F` (table 2, censée porter l'autre moitié de l'offset) : **entièrement
  à zéro** sur les 200 octets lus. Soit ce n'est pas la bonne zone/banque
  (le mapping RAM en `0x8000-0xBFFF` peut changer de banque physique — à
  revérifier via `/api/memmap` au moment précis de l'exécution plutôt
  qu'après coup), soit cette table est réellement vide pour l'instant (peu
  probable si elle contribue à l'effet). **TBD**, à re-tester avec un
  breakpoint arrêté exactement à `0x024E` pour lire `DE`/`HL` réels au bon
  moment plutôt que de deviner l'adresse a posteriori.

## 6. Questions ouvertes (à trancher avec le vrai source)

- ~~R13 varie de manière erratique — pourquoi ?~~ **Résolu, mécanisme et nom
  de la technique confirmés** par le PDF source (chapitre 12.3) : R.L.A.L.
  via `R4=0`/`R9=0` posés à `C4=C9=0`, trivial et documenté sur CRTC 1. La
  RFD est explicitement exclue (elle passe par R5, jamais touché ici).
  Détails : §5.1 et `compendium-crtc/05-comptages-r9-r5-r4-ruptures.md`.
- Confirmer si 0x02CD est une table de couleurs ou une table de pointeurs.
- Reste à confirmer : la 2e table (`0x8C8F`, §5.8) lue à `0xFF` de zéros —
  mauvaise adresse/banque au moment du dump, ou vraiment vide ?
- Le point d'entrée variable dans le bloc `0x02FD`–`0x04E5` (§5.3bis) :
  confirmer qu'il s'agit bien d'un tracé à longueur variable et pas d'une
  temporisation.
- Vérifier le format exact des commandes Gate Array utilisées en §5.2/5.6.
- Dumper autour de `0xE006` (destination du `JP` en §5.6) et de la zone
  `0xC000`+ (buffer écran) pour confirmer l'hypothèse de traînée diagonale.
- Le compendium mentionne aussi **RV** (Rupture Verticale), **RVI**
  (Rupture Verticale Invisible, cas pratique confirmé au chapitre 13.3.1
  **CRTC 1** — donc potentiellement pertinent si on retrouve un jour un
  poke CRTC affectant le VBL/BORDER pas encore expliqué) et **RVLL**
  (chapitre 13.2.7/13.4.1, confirmé **CRTC 0/2 uniquement** — hors-sujet
  ici). Pas rencontrées dans le code étudié jusqu'ici, mais gardées en tête.

## 7. Pistes de variations/améliorations (préliminaires, à affiner avec le source)

- Le "pas" diagonal (`0x8000 - 37*n`) et le nombre de traînées (2) sont des
  paramètres candidats évidents à faire varier (plus de traînées, pas
  différent, direction inversée).
- La table de dégradé (6 octets par motif) pourrait être remplacée par une
  palette plus longue pour un dégradé plus doux, ou par une fonction
  (sinus/LUT) générée dynamiquement pour un effet "arc-en-ciel" animé plutôt
  que statique.
- La routine de détection CRTC (§5.7) est probablement à laisser intacte :
  c'est de la portabilité, pas de l'effet visuel.
- Maintenant qu'on sait que R13 est rechargé ligne par ligne (§5.1/§5.8) :
  la table `0xBD00` (motif `(i%4)×0x30 + i/4`) pilote directement la forme
  du décalage ligne-par-ligne — la remplacer par une table sinus donnerait
  une ondulation (wobble) au lieu d'une diagonale rectiligne, dans le même
  mécanisme, sans toucher au reste du code.

## 8. Dump complet de la RAM (0x0000–0xFFFF)

Récupéré en un seul appel `GET /api/ram?addr=0&len=65536&view=cpu` (le
paramètre `bank` n'est pas nécessaire : l'API bascule elle-même de banque
au-delà de `0x3FFF`, comme documenté). Sauvegardé dans
`scratchpad/ram_full_0000_ffff.bin` (65536 octets, vue `cpu` = mapping
mémoire courant appliqué). Servira de référence pour :
- désassembler à la demande n'importe quelle zone sans refaire d'appel HTTP,
- retrouver les tables de données (dégradé de couleur, table de stride,
  vecteurs) une fois leurs adresses exactes confirmées,
- comparer avec un futur re-dump si l'animation évolue (ex. avant/après
  avoir laissé tourner plus longtemps, ou après un patch de test via
  `POST /api/ram`).

Pour suivre l'effet ponctuellement sans tout re-dumper : `/api/ram?addr=…&len=…`
sur les zones déjà repérées (écran `0xC000+`, table stride `0x02CD`,
positions `0x0218/0x0220/0x0229/0x022C/0x0302`), ou `/api/history` /
`/api/codemap` pour voir ce qui a bougé depuis le dernier snapshot.

## 9. Reconstruction assembleur (`psy0.asm`) — recompilation vérifiée octet-à-octet (2026-09-17)

Point de départ : `PSZOOM.sna` (fourni), analysé au préalable via
`analyse_sna.pdf` (en-tête complet : `PC=#028D`, tous les registres Z80/GA/
CRTC/PSG au chargement). Rechargé dans l'émulateur (`POST /api/media`) avec
un breakpoint sur `#028D` pour figer un état de référence exact, confirmé
identique à l'en-tête du PDF (tous les registres, y compris les registres
alternatifs `DE'=#8C8F`, `HL'=#0C54`, correspondent).

### 9.1 Ce qu'on a pu établir en plus

- **`plot_gradient` (`#02FD`) est une séquence linéaire fixe, sans aucun
  saut** (vérifié par recherche exhaustive de tout opcode de saut/call/ret
  dans la plage `#02FD`–`#04EA` : zéro trouvé, hormis l'opérande `#10` d'un
  `LD B,n`). Elle est appelée 4 fois de suite à l'identique (même code,
  même durée) depuis `frame_start` ; ce n'est donc pas un "point d'entrée
  variable" comme je l'avais d'abord supposé, mais une routine à durée
  fixe qui **trace directement le dégradé sur l'écran** (`LD (DE),A` /
  `INC DE`), la couleur/valeur de chaque octet venant d'une table lue via
  `HL`+`SP` détourné en accumulateur 16 bits.
- **`calc_stride` (`#02DC`) s'auto-modifie elle-même** : elle écrit son
  propre opérande `LD HL,nn` (adresse `calc_stride+1`, donc `#02DD`) pour
  faire avancer sa "graine" d'une frame à l'autre, **et** modifie l'opérande
  du `LD SP,nn` de `plot_gradient` (adresse `plot_gradient+5` = `#0302`) —
  c'est ce "pas" auto-injecté qui pilote `plot_gradient`. Auto-modification
  de code à deux endroits différents, confirmée par comparaison de deux
  dumps RAM pris à des frames différentes (les opérandes changent).
- **`#02CA`–`#02DB`** (motif de dégradé, 18 octets) et **`#04EB`–`#04EC`**
  (variable scratch, sauvegarde temporaire de `SP`) sont des **données**,
  jamais marquées "opcode fetch" par `/api/codemap` — confirmé sur le
  snapshot `PSZOOM.sna` comme sur le tout premier.
- Le bloc `#0295`–`#02C9` (chemin de sortie + code orphelin après le
  `JP #E006`) reste **entièrement non exécuté** sur ce nouveau snapshot
  aussi — inclus dans la source en `db` brut, par prudence (fidélité
  octet-à-octet sans prétendre en comprendre le sens).

### 9.2 Pipeline de recompilation

1. Désassemblage complet et fiable de `#015F`–`#0572` à partir du dump RAM
   de `PSZOOM.sna` (`scratchpad/z80dis.py`), recoupé avec `/api/codemap`
   (reset puis 15 itérations de boucle) pour séparer code réel / données.
2. Génération automatique de `psy0.asm` (à la racine du projet) : mnémoniques
   réels pour tout le code confirmé, labels sur toutes les cibles de saut/
   appel réellement utilisées, `db` pour les deux zones de données et pour
   le bloc mort `#0295`–`#02C9`.
3. Assemblage : `fantams psy0.asm -o out.sna --target cpc6128 --base
   PSZOOM_expanded.sna`. **`--base` exige un SNA "à plat" non compressé**
   (256 octets d'en-tête + 65536 octets de mémoire) — `PSZOOM.sna` fourni
   est un SNA v3 avec chunk `MEM0` compressé (RLE, 6664 octets au total) que
   `fantams` refuse tel quel ("base tronquée"). Contournement : reconstruit
   un SNA "étendu" en gardant l'en-tête de 256 octets de `PSZOOM.sna` (donc
   tous les registres) mais en remplaçant la mémoire par notre dump complet
   64 Ko obtenu via `/api/ram` (`scratchpad/PSZOOM_expanded.sna`).
4. **Vérification octet-à-octet** : la mémoire assemblée (`#015F`–`#0572`,
   1044 octets) ne diffère de `PSZOOM.sna` que sur **2 octets**, exactement
   ceux de la variable scratch `saved_sp` (`#04EB`-`#04EC`) — sans
   conséquence, puisque cette variable est écrasée avant chaque lecture par
   `plot_gradient` lui-même. **1042/1044 octets identiques.**
5. **Vérification visuelle** : le `.sna` réassemblé, rechargé dans
   l'émulateur (`POST /api/media`), reproduit les deux traînées diagonales
   dégradées et la ligne violette (`scratchpad/screenshot_reassembled2.png`)
   — légère différence de phase par rapport aux captures précédentes,
   normal puisque l'effet est en mouvement continu, pas un bug de
   reconstruction.

### 9.3 Point d'entrée choisi

`fantams` fixe le `PC` du `.sna` de sortie sur l'adresse du premier `org`
(`#015F`, `frame_start`) quand aucun `run` n'est précisé — plus naturel
qu'hériter du `PC=#028D` (mi-boucle) de `PSZOOM.sna`. Base à conserver pour
les variantes, sauf besoin contraire.

### 9.4 Prochaine étape : les variations

`psy0.asm` est maintenant la base de travail pour créer des variantes
(cf. pistes du §7) : modifier `gradient_motif`, le nombre de traînées dans
`frame_start` (les 4 `call plot_gradient`), ou la table `#BD00` (à ajouter
en `db` dans la source si on veut la faire varier — actuellement héritée
telle quelle du `--base`, non présente dans `psy0.asm`).

---
*Fichiers de travail : `scratchpad/z80dis.py` (désassembleur),
`scratchpad/ram_0000.bin` (dump RAM 0x0000–0x0FFF, vue `cpu`, 1er lancement),
`scratchpad/ram_full_0000_ffff.bin` (dump complet 64 Ko, vue `cpu`, 1er lancement),
`scratchpad/ram_full_2.bin` (dump complet 64 Ko après relance émulateur + SNA,
2026-09-17 — même code trouvé en 0x015F–0x0572, confirme la reproductibilité),
`scratchpad/ram_pszoom.bin` (dump complet 64 Ko de `PSZOOM.sna` chargé, état de
référence pour `psy0.asm`), `scratchpad/codemap_pszoom.bin`,
`scratchpad/full_disasm_015f_573.txt` (listing complet généré),
`scratchpad/PSZOOM_expanded.sna` (SNA à plat pour `--base`),
`psy0.asm` (source fantams, à la racine du projet),
`scratchpad/screenshot{1,2,_reassembled,_reassembled2}.png`.*

## 10. Tentative de variante "4 traînées au lieu de 2" (2026-09-17) — échec instructif

### 10.1 Bugs latents trouvés et corrigés en cours de route

En dupliquant le bloc des 4 `call plot_gradient` de `frame_start` (pour
ajouter 2 traînées de plus), l'exécution **plantait et revenait au prompt
BASIC**. Cause : `psy0.asm` (généré automatiquement) contenait plusieurs
**adresses absolues codées en dur** qui sont en réalité des références à
l'intérieur du code lui-même (auto-modification), pas de vraies constantes
externes :
- `plot_gradient` sauvegarde `SP` dans une variable à une adresse fixe
  (`#04EB`) — j'avais gardé ce littéral au lieu de référencer le label
  `saved_sp`.
- Six autres emplacements sont en fait les **opérandes d'instructions
  voisines** (`ld hl,nn` / `ld a,n` / `ld de,nn`), que le code met à jour
  lui-même d'une frame à l'autre pour faire évoluer l'animation (graines
  auto-incrémentées). Corrigé en éclatant ces instructions en `db`
  opcode + label + `db`/`dw` valeur, et en référençant partout le label
  plutôt que l'adresse numérique.
- `crtc_type_lookup` calcule une adresse de saut (`JP (HL)`) à partir d'une
  constante `#0572` qui est en fait **l'adresse de son propre octet final**
  (un `NOP`-sled à délai variable, cf. §5.3bis pour la technique jumelle
  dans `plot_gradient`) — remplacé par `crtc_type_lookup+0x2C` (label-relatif).

Une fois ces 8 références rendues relatives à leurs labels plutôt
qu'absolues, la version *sans* les 2 traînées en plus repasse la
vérification octet-à-octet (1042/1044, identique à la section 9) — donc le
générateur/pipeline reste correct, et ces corrections sont un gain permanent
pour `psy0.asm`, indépendant de cette tentative de variante.

### 10.2 Le vrai obstacle : l'effet est verrouillé au cycle T-state près

Une fois le plantage réglé, les 2 traînées supplémentaires provoquaient un
**écran noir permanent** (confirmé sur 5 captures espacées, `mode` GA et
CRTC contrôlés — pas une histoire de photo prise au mauvais moment). Testé
à deux endroits : au milieu de `frame_start` (avant la boucle CRTC
par-ligne) et après elle (juste avant `call util_04ED`) — noir dans les
deux cas.

**Explication** : `plot_gradient` prend un nombre de cycles Z80 fixe et non
négligeable (~500 T-states, boucle déroulée). Le rechargement de MA à
chaque ligne (§5.1, `R4=0`/`R9=0`) n'est correct **que si le code repasse
par la réinitialisation CRTC de `frame_start` avec `C4=C9=0`** (chapitre
12.3 du compendium — condition explicite). Ajouter ~1000 T-states de
travail par passage **désynchronise ce timing** : soit la boucle
`per_line_loop` démarre trop tard par rapport au balayage réel (traînées
d'origine placées avant), soit c'est le retour à `frame_start` qui arrive
trop tard pour que `C4`/`C9` soient encore à 0 au moment de reposer
`R4=0`/`R9=0` (traînées supplémentaires placées après) — dans les deux cas,
le CRTC 1 tombe dans le cas d'erreur explicitement documenté : *"mettre
R4=0 sur la dernière ligne d'un frame va provoquer un débordement de C4"*
(chapitre 12.3), et l'affichage cesse d'être piloté correctement.

**⇒ Conclusion : on ne peut pas juste "ajouter du travail" dans cette
boucle sans recompter les cycles.** Ajouter des traînées supplémentaires de
cette façon nécessiterait soit de réduire ailleurs (moins d'itérations dans
`per_line_loop`, moins d'appels `plot_gradient` existants), soit une
technique qui ne coûte pas de temps CPU dans le chemin critique (par
exemple copier un motif déjà tracé par memcpy au lieu de le retracer avec
`plot_gradient`, ou dupliquer via l'entrelacement mémoire plutôt que par du
code supplémentaire). Piste non explorée faute de temps — cf. §7 pour
d'autres variantes moins risquées à tenter en premier (dégradé, pas
diagonal) qui ne touchent pas au volume de travail par frame.

*État actuel de l'émulateur : remis sur la version à 2 traînées qui
fonctionne (`/tmp/psy0_true_clean.sna`, byte-identique à `psy0.asm` sans la
tentative de duplication). Le brouillon à 4 traînées n'est pas resté dans
`psy0.asm` — à reprendre plus tard avec un vrai budget de cycles.*

## 11. Variante réussie : table `0xBD00` remplacée par une sinusoïde ("wobble")

Suite à la conclusion du §10 (l'effet est verrouillé au cycle T-state
près), tentative d'une variante qui **ne touche à aucun timing** : garder
exactement le même code (mêmes 240 itérations, mêmes instructions), et ne
changer que le **contenu de la table de correspondance `0xBD00`** lue par
`per_line_loop` pour convertir un octet scanné en valeur de R13 (cf. §5.8).

### 11.1 Mise en œuvre

- La table (256 octets, motif `(i%4)×0x30 + i/4`) a été rendue **explicite**
  dans `psy0.asm` (`org #BD00`, section `r13_wobble_table`) — jusque-là
  héritée telle quelle du `--base`, jamais définie dans notre source.
  Vérifié d'abord avec le contenu original inchangé : toujours
  octet-à-octet identique (`0x015F-0x0572` : 2 diffs inconséquentes comme au
  §9 ; `0xBD00-0xBDFF` : 0 diff).
- Remplacée ensuite par une sinusoïde calculée en Python puis figée en `db`
  (256 valeurs, `128 + 100×sin(2π×i/64)`, arrondies et bornées 0-255,
  période 64).
- **Aucune autre modification de code.**

### 11.2 Résultat

Chargé et laissé tourner plusieurs secondes (`frames` progresse
normalement, pas de plantage, pas d'écran noir — contrairement au §10).
Effet obtenu : au lieu des deux traînées diagonales continues, les mêmes
segments de couleur (magenta → blanc → cyan → rouge → jaune) apparaissent
**fragmentés en petits blocs dispersés** à des hauteurs et positions
horizontales variées sur toute la largeur de l'écran, et cette
fragmentation **évolue dans le temps** (l'animation continue de bouger).

**Pourquoi "dispersé" plutôt qu'une onde lisse et continue** : rappel du
§5.8/§10 — l'index utilisé pour lire `0xBD00` n'est **pas** le numéro de
ligne `i` directement, mais un octet *scanné en mémoire* (`ld a,(de) ; add
a,(hl)`) dans un buffer qui contient en fait des copies successives du motif
de dégradé (`gradient_motif`, cf. §9.1) accumulées frame après frame — donc
une séquence d'index qui n'est pas une rampe linéaire propre. Une sinusoïde
appliquée à cette séquence produit un mélange plausible mais pas une onde
visuellement lisse. **Piste pour un wobble plus "propre"** : remplacer
plutôt la fonction qui *génère l'index* (le buffer scanné) par un compteur
linéaire simple, ou appliquer la sinusoïde à un autre point de la chaîne —
non tenté ici, cf. §10 pour la prudence à observer sur tout ce qui touche au
volume de travail par ligne.

Fichier : `psy0.asm` contient actuellement cette variante "wobble" (table
`r13_wobble_table` avec les valeurs sinus). Le contenu original de la table
est conservé ci-dessus en commentaire/historique (§11.1) pour revenir en
arrière si besoin. Captures : `scratchpad/screenshot_wobble{1,2}.png`.
