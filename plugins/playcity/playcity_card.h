// La carte PlayCity : Z84C30 + 2 x YMZ294, décodage des ports, câblage entre puces. Sans ABI ni SDL.
//
// Ports (oldwiki.cpcwiki.eu/index.php/PlayCity, recoupé avec le Verilog MiSTer) :
//   &F880-&F883  CTC canaux 0-3 (lecture : compteur descendant)
//   &F884 / &F984  YMZ « droite » : écriture de donnée / sélection de registre
//   &F888 / &F988  YMZ « gauche »
//   &F8FF        reset (toute sortie)
// Le MiSTer inverse gauche/droite par rapport au wiki et à ACE : paramètre swap_channels.
// Décodage matériel (MiSTer) : A15-A9 = 1111100, A7-A4 = 8 ; A2 = puce « droite », A3 = puce « gauche »
// (une adresse comme &F88C les sélectionne toutes les deux), A8 = 1 -> sélection de registre.
#pragma once
#include <stdint.h>
#include "ctc.h"
#include "ymz294.h"
#include "plugin_audio.h"
#include "plugin_clock.h"

typedef struct PcLines
{
	void*	user;
	void	(*set_int)(void* user, int level);		// 0 = LOW (actif), 1 = HIGH
	void	(*set_nmi)(void* user, int level);
} PcLines;

typedef struct PlayCity
{
	Ctc				ctc;
	Ymz				ymz[2];						// 0 = droite (&F884), 1 = gauche (&F888), avant swap
	GfSampleClock	clock;
	GfAudioStream*	stream;						// sortie stéréo (L, R)
	PcLines			lines;
	uint64_t		last_cycle;
	uint32_t		cursor_pending;				// impulsions CURSOR reçues depuis le dernier avancement du CTC
	int				int_level, nmi_level;
	int				swap_channels;
	float			hp_x[2], hp_y[2], hp_r;		// couplage alternatif de la sortie
} PlayCity;

#define PC_CLOCK_HZ		4000000u

void		pc_init(PlayCity* p, GfAudioStream* stream, const PcLines* lines, int swap_channels);
void		pc_reset(PlayCity* p, uint64_t cycle);
// Fait avancer la carte jusqu'à `cycle` (CTC, horloge des YMZ, audio, lignes INT/NMI).
void		pc_tick(PlayCity* p, uint64_t cycle);
// Renvoie 1 si le port est répondu par la carte (et écrit *data), 0 sinon (bus libre).
int			pc_io_in(PlayCity* p, uint16_t port, uint64_t cycle, uint8_t* data);
void		pc_io_out(PlayCity* p, uint16_t port, uint8_t data, uint64_t cycle);
// Acquittement d'interruption : renvoie 1 et le vecteur si la carte demandait l'interruption.
int			pc_int_ack(PlayCity* p, uint64_t cycle, uint8_t* vector);
// Impulsion du signal CURSOR du CRTC (entrée du canal 1, dont la sortie déclenche la NMI).
void		pc_cursor(PlayCity* p, uint64_t cycle);
// Horloge de l'AY équivalent CPC déduite du canal 0 du CTC (1 MHz CPC, 2 MHz « ST » par défaut).
double		pc_ay_hz(const PlayCity* p);
