// Digiblaster : conversion du flux d'écritures datées (T-states 4 MHz) en échantillons audio.
// Aucune dépendance SDL ni core : testable seul.
//
// Le producteur (fil d'émulation) appelle db_write / db_anchor ; le consommateur (fil audio)
// appelle db_render. La file, le préremplissage, le saut vers le récent et le maintien sur
// underrun viennent du tronc commun (plugin_audio) ; ce module ne garde que la conversion
// temps -> échantillons et le couplage alternatif de la sortie.
#pragma once
#include <stdint.h>
#include <stdatomic.h>
#include "plugin_audio.h"

#define DB_CLOCK_HZ		4000000.0

typedef struct DbDsp
{
	// --- file (tronc commun), mono, volume 1 : le volume est appliqué par db_render ---
	GfAudioStream	stream;
	uint32_t		rate;					// Hz de sortie
	double			cps;					// T-states par échantillon

	// --- producteur ---
	uint64_t		next;					// indice du prochain échantillon à produire
	double			t;						// T-states : début de la zone pas encore intégrée
	double			acc;					// intégrale de la valeur dans la fenêtre courante
	uint8_t			value;					// niveau courant du CNA (octet brut du port imprimante)
	uint64_t		events, anchors;

	// --- consommateur ---
	float			hp_x, hp_y, hp_r;		// filtre passe-haut (couplage AC de la sortie réelle)
	_Atomic float	volume;					// 0..1
} DbDsp;

void db_init(DbDsp* d, uint32_t rate, uint32_t latency_ms, float volume);
// Réancre la chronologie (reset machine, retour en arrière du temps) sans produire d'échantillons.
void db_anchor(DbDsp* d, uint64_t cycle, uint8_t value);
// Le port reçoit `value` à l'instant `cycle`.
void db_write(DbDsp* d, uint64_t cycle, uint8_t value);
// Remplit `n` échantillons mono ; renvoie toujours n (maintient le dernier niveau si la file est vide).
void db_render(DbDsp* d, float* out, uint32_t n);
