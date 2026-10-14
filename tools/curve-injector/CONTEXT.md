# Curve Injector

Outil web autonome (`wobble_editor.html`) qui dessine une courbe d'octets et l'écrit en direct dans la RAM de l'émulateur AMSpiriT via son API REST locale.

## Language

**Courbe**:
Le tableau d'octets (0–255) actuellement édité, de longueur configurable, destiné à être écrit en RAM.
_Avoid_: table, buffer, tampon

**Injection**:
L'écriture de la courbe en RAM émulée à une adresse donnée, via `POST /api/ram`.
_Avoid_: envoi, application, écriture (sauf dans un sens générique hors contexte RAM)

**Mode paramétrique**:
Mode de génération de la courbe à partir d'une forme d'onde et de ses paramètres numériques (centre, amplitude, période, phase, rapport cyclique). C'est le seul mode pilotable au MIDI.
_Avoid_: mode courbe, mode standard

**Forme d'onde**:
Le type de générateur utilisé en mode paramétrique pour produire la courbe (sinus, triangle, dents de scie, carré, impulsion, bruit, rampe entrelacée). Ne pas confondre avec le **type de contrôleur** (ci-dessous), qui est un concept propre au MIDI.
_Avoid_: type (seul, sans qualificatif — ambigu avec type de contrôleur), type de courbe

**Plage de paramètre**:
Les bornes min/max propres à un paramètre du mode paramétrique (centre, amplitude, période, phase, rapport cyclique), fixées librement par l'utilisateur. Sans rapport avec l'**encodage** (ci-dessous) : la plage d'un paramètre ajuste son domaine d'édition, pas la façon dont la courbe est écrite en RAM.
_Avoid_: range (seul, sans qualificatif), bornes

**Encodage**:
La configuration régissant la conversion des valeurs de la courbe en octets écrits en RAM lors de l'injection. Deux types, mutuellement exclusifs : **Data** (ci-dessous) et **Gate Array** (ci-dessous). Indépendant des **plages de paramètre** : ces dernières ajustent le domaine d'édition d'un paramètre, l'encodage ajuste la façon dont la courbe résultante est écrite en RAM.
_Avoid_: range de sortie (seul), format d'injection

**Encodage Data**:
Type d'encodage pour des valeurs numériques brutes : une taille (1 ou 2 octets), une plage de sortie avec un mode de bornage (saturation par défaut, ou modulo), un masque « and » optionnel et un masque « or » optionnel, appliqués dans cet ordre : valeur générée → bornage → and → or → encodage (1 ou 2 octets, little-endian). Exemple : forcer des valeurs paires entre 64 et 95 via `and 30, or 64`.
_Avoid_: encodage (seul, sans qualificatif, une fois l'encodage Gate Array introduit)

**Encodage Gate Array**:
Type d'encodage pour des séquences de couleurs CPC : une valeur générée est bornée (saturation ou modulo, présélectionné automatiquement selon le **dégradé** choisi mais modifiable) sur une plage de sortie représentant une position dans le dégradé, arrondie à l'encre la plus proche, puis convertie en son **code Gate Array**. Toujours 1 octet ; ni taille ni masques « and »/« or » (non applicables — un masque pourrait produire un code Gate Array invalide). À ne pas confondre avec un mode « palette » générique : c'est bien le code matériel Gate Array qui est écrit, jamais le numéro d'encre BASIC.
_Avoid_: encodage palette, mode couleur, mode palette

### Couleurs CPC

**Encre (ink)**:
Le numéro de couleur BASIC du CPC (0 à 26), encodage arithmétique `B + 3R + 9V`
des trois niveaux R/V/B (0, 1 ou 2 chacun). Référence complète :
`Les couleurs du CPC.md`.
_Avoid_: couleur (seul, ambigu avec code Gate Array), pen, index de couleur

**Code Gate Array**:
La valeur matérielle (`0x40`–`0x5F`) à écrire sur le port du Gate Array pour
sélectionner une encre physique. Distinct de l'**encre** : la correspondance
encre→code Gate Array n'est pas arithmétique (table de conversion nécessaire),
et 5 des 32 codes possibles sont redondants (même encre physique qu'un autre
code). C'est ce code, et non le numéro d'encre, qu'un programme Z80 écrit
réellement via `OUT` pour changer une couleur à l'écran.
_Avoid_: code couleur, valeur GA (seul, sans contexte)

**Dégradé (gradient)**:
Une séquence ordonnée d'encres CPC, éventuellement cyclique (dernière valeur
suivie à nouveau de la première), destinée à convertir une courbe en séquence
de couleurs plutôt qu'en valeurs numériques brutes.
_Avoid_: palette (trop générique — une palette CPC désigne d'ordinaire
l'ensemble des encres assignées aux stylos actifs à l'écran, pas un dégradé)

### Contrôle MIDI

**Mapping**:
Association entre un contrôleur MIDI identifié (device + canal + numéro de CC) et un paramètre du mode paramétrique, avec un type de contrôleur et, le cas échéant, des valeurs de préréglage.
_Avoid_: association, binding, assignation

**Apprentissage (Learn)**:
Action de capturer automatiquement le device, le canal et le numéro de CC d'un mapping en écoutant le prochain message MIDI reçu, plutôt que de les saisir manuellement.
_Avoid_: capture, détection, assignation automatique

**Type de contrôleur**:
Classification d'un mapping MIDI déterminant comment une valeur MIDI entrante affecte le paramètre borné qu'elle contrôle. Trois valeurs : **Absolu** (le CC 0–127 est mis à l'échelle linéairement sur toute la plage du paramètre), **Relatif** (encodeur sans fin ; convention 63 = −1 / 65 = +1 autour de 64, accumulé par pas configurable), **Momentané** (bouton poussoir ; bascule le paramètre entre deux valeurs prédéfinies). Concept propre au MIDI — à ne pas confondre avec la **forme d'onde** (ci-dessus), qui est le type de générateur de la courbe.
_Avoid_: mode de contrôleur, comportement, type (seul, sans qualificatif)

**Valeurs de bascule (toggle)**:
Les deux valeurs prédéfinies entre lesquelles un mapping de type Momentané fait basculer son paramètre à chaque appui.
_Avoid_: presets, valeurs prédéfinies (au singulier générique)
