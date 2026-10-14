# Plugins AmspiriT

Extensions matérielles émulées, chargées dynamiquement par le core (ABI : `include/Core_Plugin.h`).
Chaque plugin est un projet Meson autonome qui n'inclut que cet en-tête.

| Plugin | Connecteur | Rôle |
|---|---|---|
| [`digiblaster/`](digiblaster/) | imprimante | CNA 8 bits, sortie audio SDL2 autonome |
| [`playcity/`](playcity/) | extension | Z84C30 (CTC) + 2 x YMZ294, IM 2 / NMI, sortie SDL2 |
| [`common/`](common/) | — | tronc commun (pas un plugin) : paramètres, horloge d'échantillons, flux audio, sortie SDL2 optionnelle |

## En-tête d'ABI

`include/` est un lien vers `common/include/` ; `Core_Plugin.h` y est une **copie** de `amspirit-core/amspirit-core/inc/public/Core_Plugin.h`.
La source de vérité reste le core : recopier le fichier à chaque évolution de l'ABI (`CORE_PLUGIN_ABI_MAJOR`
différent = le core refuse le plugin).

## Construire

```bash
make                       # tous les plugins, Linux natif (build/ par plugin)
make test                  # tests (Linux natif uniquement)
make dist PLATFORM=windows # MinGW-w64 -> build_windows/, dist/windows/*.dll
make dist PLATFORM=arm     # aarch64 -> build_rpi5/, dist/arm/*.so
make digiblaster-all       # un seul plugin (ou : make -C digiblaster)
```

Chaque plugin a son `Makefile` ; les réglages par plateforme sont dans `mk/platform.mk` et `cross/*.ini`
(pas de lien avec distrobox : lancer `make` dans l'environnement qui a la chaîne d'outils voulue).
Prérequis : `meson`, `ninja`, SDL2 (version cible pour windows/arm).

## Tronc commun (`common/`)

Projet Meson autonome, C11, **sans dépendance au core** : `plugin_params` (paramètres déclaratifs validés par type),
`plugin_clock` (T-states -> échantillons dus, sans dérive), `plugin_audio` (file SPSC 1-2 canaux avec préremplissage),
et `sdl/plugin_sdl_audio` (seul fichier qui dépend de SDL2, optionnel). Un plugin le consomme en sous-projet Meson :
`playcity/subprojects/plugin-common` est un lien vers `../../common`. `meson test` dans `common/` lance ses tests.
Digiblaster l'utilise aussi (paramètres, file audio, sortie SDL) ; seul son filtre passe-haut reste local.
