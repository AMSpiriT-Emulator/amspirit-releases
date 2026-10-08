# PlayCity (greffon AmspiriT)

Carte d'extension de TotO : un **Z84C30** (CTC) et **deux YMZ294** (6 voix stéréo). Connecteur d'extension.

| Port | Fonction |
|---|---|
| `&F880-&F883` | CTC canaux 0-3 (lecture : compteur descendant ; écriture sur le canal 0 avec bit 0 = 0 : base du vecteur IM 2) |
| `&F884` / `&F984` | YMZ « droite » : donnée / sélection de registre |
| `&F888` / `&F988` | YMZ « gauche » |
| `&F8FF` | reset (toute sortie) |

Câblage : TRG0 = TRG2 = 4 MHz, TRG1 = CURSOR, TRG3 = ZC/TO2 ; ZC/TO0 = horloge des YMZ, ZC/TO1 = NMI.
Sources : [oldwiki CPCWiki](https://oldwiki.cpcwiki.eu/index.php/PlayCity), plugin ACE
([framagit](https://framagit.org/offset/playcity-acepansion)), implémentation MiSTer
([Amstrad_MiSTer/rtl/playcity](https://github.com/MiSTer-devel/Amstrad_MiSTer/tree/master/rtl/playcity)).
Le CTC est réécrit d'après le comportement du MK3882 (priorités, « en service »), pas copié.

## Organisation

- `ctc.{c,h}`, `ymz294.{c,h}`, `playcity_card.{c,h}` : la carte, sans ABI ni SDL (testée seule).
- `playcity.c` : glue ABI du core (ABI 1.1 : `int_ack`, `tick`) + sortie SDL2.
- `tests/` : `meson test`. Test de bout en bout contre le core : `PLAYCITY_PLUGIN=.../playcity.so` dans `amspirit-core-tests "[playcity]"`.

## Approximations connues

- **RETI** : le vrai CTC la surveille sur le bus (`ED 4D`) pour libérer son canal « en service ». L'ABI ne la
  montre pas : le canal est libéré dès l'acquittement (`pc_int_ack`). Conséquence : les impulsions d'un canal
  pendant son propre handler sont retenues au lieu d'être perdues.
- **Horloge des YMZ** : débit des fronts = 4 MHz x (1 - 0,5 / période de ZC/TO0), qui reproduit la table du wiki ;
  la gigue réelle des fronts n'est pas modélisée.
- **Gauche/droite** : le wiki et ACE disent `&F884` = droite, le MiSTer l'inverse. Paramètre `swap_channels`.
- **CURSOR** (canal 1 -> NMI) : la carte sait le traiter (`pc_cursor`), mais le core ne fournit pas encore le signal.
- La polarité du front (bit 4 du mot de contrôle) est ignorée ; non validé à l'oreille ni sur Windows/macOS.
