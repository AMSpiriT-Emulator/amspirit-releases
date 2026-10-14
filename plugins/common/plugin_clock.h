// Horloge d'échantillons : convertit le temps émulé (T-states) en nombre d'échantillons audio dus,
// sans dérive (arithmétique entière exacte). Un plugin audio l'interroge depuis tick().
#pragma once
#include <stdint.h>

typedef struct GfSampleClock
{
	uint32_t	clock_hz;		// fréquence de l'unité de temps (4000000)
	uint32_t	rate;			// échantillons par seconde
	uint64_t	anchor;			// cycle d'origine
	uint64_t	emitted;		// échantillons déjà rendus depuis l'ancre
	uint64_t	last;			// dernier cycle vu (détecte un retour en arrière)
} GfSampleClock;

void		gf_clock_init(GfSampleClock* c, uint32_t clock_hz, uint32_t rate, uint64_t cycle);
// Repart de `cycle` (reset machine, retour en arrière du temps) : rien n'est dû avant.
void		gf_clock_anchor(GfSampleClock* c, uint64_t cycle);
// Nombre d'échantillons à produire pour couvrir le temps jusqu'à `cycle` (et le compte comme rendu).
// Un cycle antérieur à ce qui est déjà couvert ré-ancre et renvoie 0.
uint32_t	gf_clock_due(GfSampleClock* c, uint64_t cycle);
