# Plugin Digiblaster

CNA 8 bits sur le port imprimante du CPC (Digiblaster, Soundplayer), avec sortie audio SDL2 propre au plugin.
Sortie seule : pas de lecture, pas de ligne BUSY.

- L'échantillon est l'octet brut du port `&EFxx` (le bit 7, strobe, est le 8e bit), non signé, centré sur 128.
- `printer_out` (fil d'émulation) intègre les écritures datées en T-states et produit des échantillons
  (moyenne par fenêtre) dans une file sans verrou ; le fil audio SDL la vide.
- Passe-haut ~20 Hz côté lecture (couplage alternatif de la sortie réelle) : un niveau continu s'éteint.
- Préremplissage (`latency_ms`) avant de démarrer ; file vide = reprise de la lecture après préremplissage.
  Un silence prolongé n'ajoute pas de retard (réancrage de la chronologie).

## Paramètres

| Clé | Type | Application | Défaut |
|---|---|---|---|
| `volume` | INT 0-100 | à chaud | 80 |
| `sample_rate` | ENUM 44100 / 48000 | à l'attache | 44100 |
| `latency_ms` | INT 10-500 | à l'attache | 60 |

## Tests

- `meson test -C build` : DSP seul (cadence, carré, continu bloqué, préremplissage, trous, temps qui recule, débordement).
- De bout en bout contre le vrai core (programme Z80 qui joue un carré, pilote SDL `dummy`) :
  `DIGIBLASTER_PLUGIN=<chemin>/digiblaster.so amspirit-core-tests "[digiblaster]"` (test dans le dépôt du core,
  sauté si la variable est absente).
