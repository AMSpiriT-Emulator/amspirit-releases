// Z84C30 (Z80 CTC) tel que câblé sur la PlayCity : horloge Phi = 4 MHz.
//   CLK/TRG0 = 4 MHz          ZC/TO0 -> horloge des YMZ294
//   CLK/TRG1 = CURSOR (CRTC)  ZC/TO1 -> NMI
//   CLK/TRG2 = 4 MHz          ZC/TO2 -> CLK/TRG3
//   CLK/TRG3 = ZC/TO2         (ZC/TO3 n'existe pas)
// Aucun appel à l'ABI du core : testable seul. Le temps avance par paquets de cycles Phi
// (arithmétique exacte, pas de boucle par cycle). La polarité du front (bit 4) est ignorée : le
// câblage ne fournit que des fronts actifs.
#pragma once
#include <stdint.h>

#define CTC_CHANNELS	4

typedef struct CtcChannel
{
	uint8_t		ctrl;				// dernier mot de contrôle
	uint8_t		count_max;			// constante de temps (0 = 256)
	uint8_t		dc;					// compteur descendant (lu par le Z80)
	uint16_t	ph;					// cycles Phi écoulés dans la période du prédiviseur
	uint8_t		start_delay;		// cycles Phi avant le démarrage (2e front de Phi)
	uint8_t		count_ena;			// le timer tourne
	uint8_t		tc_loaded;			// une constante de temps a été chargée depuis le dernier reset
	uint8_t		wait_tc;			// le prochain octet écrit est la constante de temps
	uint8_t		wait_trig;			// timer à démarrage par CLK/TRG : attend l'impulsion
	uint8_t		int_reg;			// demande d'interruption en attente d'acquittement
	uint8_t		in_service;			// acquittée, RETI pas encore vu
	uint32_t	zc;					// impulsions ZC/TO non encore reprises
} CtcChannel;

typedef struct Ctc
{
	uint8_t		vector;				// bits 7-3 : base du vecteur
	CtcChannel	ch[CTC_CHANNELS];
} Ctc;

void		ctc_reset(Ctc* c);										// reset matériel (mise sous tension, &F8FF)
void		ctc_write(Ctc* c, unsigned channel, uint8_t value);
uint8_t		ctc_read(const Ctc* c, unsigned channel);				// compteur descendant courant
// Fait avancer de `phi_cycles` ; `trg1_events` = impulsions CURSOR reçues pendant l'intervalle.
void		ctc_advance(Ctc* c, uint32_t phi_cycles, uint32_t trg1_events);

// Interruptions (daisy-chain interne, comme le MK3882) : une impulsion ZC/TO d'un canal n'est retenue que si
// aucun canal de priorité supérieure ou égale n'est « en service » ; sinon elle est perdue.
unsigned	ctc_int_pending(const Ctc* c);							// masque des canaux demandant une interruption
// Acquittement : sert le canal le plus prioritaire (0 > 3), le met « en service », renvoie 1 et le vecteur.
int			ctc_ack(Ctc* c, uint8_t* vector);
// RETI exécuté : libère le canal en service le plus prioritaire.
void		ctc_reti(Ctc* c);

// Impulsions ZC/TO du canal depuis le dernier appel (NMI pour le canal 1).
uint32_t	ctc_take_zc(Ctc* c, unsigned channel);
// Période de ZC/TO0 en cycles Phi (TC en mode compteur, prédiviseur * TC en mode timer) ; 0 si le canal
// 0 ne tourne pas (l'horloge des YMZ est alors libre).
unsigned	ctc_ch0_period(const Ctc* c);
