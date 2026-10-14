// Flux audio entre le fil d'émulation (producteur) et le fil audio du client (consommateur) :
// file SPSC sans verrou, préremplissage, saut vers le récent quand le retard s'accumule.
// Aucune dépendance SDL : le périphérique audio est branché par ailleurs (plugin_sdl_audio.h).
//
// Le producteur pousse des trames (1 ou 2 flottants) à la cadence `rate` ; le consommateur
// (gf_audio_render) en réclame autant qu'il veut et reçoit toujours le nombre demandé.
#pragma once
#include <stdint.h>
#include <stdatomic.h>

#define GF_AUDIO_RING_FRAMES	65536u			// trames (puissance de 2)
#define GF_AUDIO_MAX_CHANNELS	2

typedef struct GfAudioStream
{
	// --- configuration (fixée avant le démarrage du fil audio) ---
	uint32_t		rate;
	uint32_t		channels;
	uint32_t		prefill;					// trames à accumuler avant de (re)démarrer la lecture
	uint32_t		maxfill;					// au-delà, la lecture saute vers le récent : latence bornée

	// --- statistiques ---
	uint64_t		pushed, dropped, underruns, skipped;

	// --- consommateur ---
	float			hold[GF_AUDIO_MAX_CHANNELS];	// dernière trame sortie (maintenue hors lecture)
	uint32_t		wait;
	_Atomic float	volume;						// 0..1

	// --- partagé ---
	_Atomic uint32_t	wr, rd;
	_Atomic int			buffering;				// 1 = le consommateur attend `prefill` trames
	float				ring[GF_AUDIO_RING_FRAMES * GF_AUDIO_MAX_CHANNELS];
} GfAudioStream;

void		gf_audio_init(GfAudioStream* s, uint32_t rate, uint32_t channels, uint32_t latency_ms, float volume);
// Producteur : une trame (`channels` flottants). Renvoie 0 (et compte `dropped`) si la file est pleine.
int			gf_audio_push(GfAudioStream* s, const float* frame);
// Producteur : trames en attente de lecture.
uint32_t	gf_audio_buffered(const GfAudioStream* s);
// Consommateur : remplit `frames` trames entrelacées ; en l'absence de données, maintient la dernière trame.
void		gf_audio_render(GfAudioStream* s, float* out, uint32_t frames);
