// Digiblaster : conversion du flux d'écritures datées (T-states 4 MHz) en échantillons audio.
// Aucune dépendance SDL ni core : testable seul.
//
// Le producteur (fil d'émulation) appelle db_write / db_anchor ; le consommateur (fil audio)
// appelle db_render. File SPSC sans verrou entre les deux.
#pragma once
#include <stdint.h>
#include <stdatomic.h>

#define DB_CLOCK_HZ		4000000.0
#define DB_RING_SIZE	65536u				// échantillons (puissance de 2)

typedef struct DbDsp
{
	// --- configuration (fixée avant le démarrage du fil audio) ---
	uint32_t		rate;					// Hz de sortie
	double			cps;					// T-states par échantillon
	uint32_t		prefill;				// échantillons à accumuler avant de (re)démarrer la lecture
	uint32_t		maxfill;				// au-delà, la lecture saute vers le récent (turbo, pause) : latence bornée

	// --- producteur ---
	uint64_t		next;					// indice du prochain échantillon à produire
	double			t;						// T-states : début de la zone pas encore intégrée
	double			acc;					// intégrale de la valeur dans la fenêtre courante
	uint8_t			value;					// niveau courant du CNA (octet brut du port imprimante)
	uint64_t		produced, dropped, events, anchors;

	// --- consommateur ---
	float			hold;					// dernier échantillon sorti (maintenu hors lecture)
	float			hp_x, hp_y, hp_r;		// filtre passe-haut (couplage AC de la sortie réelle)
	uint64_t		underruns, skipped;
	uint32_t		wait;					// échantillons joués pendant qu'on attend le préremplissage
	_Atomic float	volume;					// 0..1

	// --- partagé ---
	_Atomic uint32_t	wr, rd;
	_Atomic int			buffering;			// 1 = le consommateur attend `prefill` échantillons
	float				ring[DB_RING_SIZE];
} DbDsp;

void db_init(DbDsp* d, uint32_t rate, uint32_t latency_ms, float volume);
// Réancre la chronologie (reset machine, retour en arrière du temps) sans produire d'échantillons.
void db_anchor(DbDsp* d, uint64_t cycle, uint8_t value);
// Le port reçoit `value` à l'instant `cycle`.
void db_write(DbDsp* d, uint64_t cycle, uint8_t value);
// Remplit `n` échantillons mono ; renvoie toujours n (maintient le dernier niveau si la file est vide).
void db_render(DbDsp* d, float* out, uint32_t n);
