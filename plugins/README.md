# Greffons AmspiriT

Extensions matérielles émulées, chargées dynamiquement par le core (ABI : `include/Core_Greffon.h`).
Chaque greffon est un projet Meson autonome qui n'inclut que cet en-tête.

| Greffon | Connecteur | Rôle |
|---|---|---|
| [`digiblaster/`](digiblaster/) | imprimante | CNA 8 bits, sortie audio SDL2 autonome |
| [`playcity/`](playcity/) | extension | Z84C30 (CTC) + 2 x YMZ294, IM 2 / NMI, sortie SDL2 |
| [`common/`](common/) | — | tronc commun (pas un greffon) : paramètres, horloge d'échantillons, flux audio, sortie SDL2 optionnelle |

## En-tête d'ABI

`include/` est un lien vers `common/include/` ; `Core_Greffon.h` y est une **copie** de `amspirit-core/amspirit-core/inc/public/Core_Greffon.h`.
La source de vérité reste le core : recopier le fichier à chaque évolution de l'ABI (`CORE_GREFFON_ABI_MAJOR`
différent = le core refuse le greffon).

## Construire

```bash
cd digiblaster && meson setup build && ninja -C build && meson test -C build
```

## Tronc commun (`common/`)

Projet Meson autonome, C11, **sans dépendance au core** : `greffon_params` (paramètres déclaratifs validés par type),
`greffon_clock` (T-states -> échantillons dus, sans dérive), `greffon_audio` (file SPSC 1-2 canaux avec préremplissage),
et `sdl/greffon_sdl_audio` (seul fichier qui dépend de SDL2, optionnel). Un greffon le consomme en sous-projet Meson :
`playcity/subprojects/greffon-common` est un lien vers `../../common`. `meson test` dans `common/` lance ses tests.
Digiblaster n'a pas encore été migré dessus.
