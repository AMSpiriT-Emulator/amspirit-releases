// YMZ294 (compatible YM2149) : 3 voix, bruit, enveloppe à 32 pas. Registres 0-13 en écriture seule.
// Aucune dépendance au core ni à SDL : testable seul.
//
// L'horloge fournie à ymz_render est celle de l'AY « équivalent CPC » (1 MHz sur un CPC, 2 MHz « ST ») :
// fréquence d'un son = horloge / (16 * période). Le rendu moyenne le signal sur la fenêtre de chaque
// échantillon (filtre boîte) pour éviter le repliement des aigus.
#pragma once
#include <stdint.h>

typedef struct Ymz
{
	uint8_t		reg[16];
	uint8_t		sel;							// registre sélectionné
	uint16_t	tone_cnt[3];
	uint8_t		tone_out[3];
	uint16_t	noise_cnt;
	uint32_t	lfsr;							// bruit : registre à décalage 17 bits
	uint8_t		noise_out;
	uint32_t	env_cnt;
	int8_t		env_step;						// 0..31
	int8_t		env_dir;						// +1 / -1
	uint8_t		env_hold;
	double		tick_left;						// fraction du tick interne en cours restant à consommer
} Ymz;

void		ymz_reset(Ymz* y);
void		ymz_select(Ymz* y, uint8_t reg);				// registre >= 16 : ignoré (sélection invalide)
void		ymz_write(Ymz* y, uint8_t value);				// registre sélectionné ; 14 et 15 n'existent pas
// `n` échantillons mono dans [0,1] (somme des 3 voix / 3), pour une horloge AY de `ay_hz` Hz.
void		ymz_render(Ymz* y, double ay_hz, uint32_t rate, float* out, uint32_t n);
