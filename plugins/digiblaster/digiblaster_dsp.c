#include "digiblaster_dsp.h"
#include <string.h>

void db_init(DbDsp* d, uint32_t rate, uint32_t latency_ms, float volume)
{
	memset(d, 0, sizeof *d);
	gf_audio_init(&d->stream, rate, 1, latency_ms, 1.0f);
	d->rate = rate;
	d->cps = DB_CLOCK_HZ / (double)rate;
	d->hp_r = 1.0f - (6.2831853f * 20.0f) / (float)rate;		// coupure ~20 Hz
	atomic_store(&d->volume, volume);
	d->value = 0x80;
}

void db_anchor(DbDsp* d, uint64_t cycle, uint8_t value)
{
	d->next = (uint64_t)((double)cycle / d->cps) + 1;
	d->t = (double)d->next * d->cps;
	d->acc = 0.0;
	d->value = value;
	d->anchors++;
}

// Intègre la valeur courante jusqu'à `to`, en produisant un échantillon par fenêtre complète
// (moyenne sur la fenêtre = filtre boîte, évite le repliement des écritures rapides).
static void db_advance(DbDsp* d, double to)
{
	const float level = ((float)d->value - 128.0f) * (1.0f / 128.0f);
	while (d->t < to)
	{
		const double end = (double)(d->next + 1) * d->cps;
		const double stop = end <= to ? end : to;
		d->acc += (double)level * (stop - d->t);
		d->t = stop;
		if (d->t >= end)
		{
			const float s = (float)(d->acc / d->cps);
			gf_audio_push(&d->stream, &s);
			d->acc = 0.0;
			d->next++;
		}
	}
}

void db_write(DbDsp* d, uint64_t cycle, uint8_t value)
{
	const double c = (double)cycle;
	d->events++;
	if (c + d->cps < d->t)						// temps revenu en arrière : on se réancre
		db_anchor(d, cycle, d->value);
	// Silence prolongé alors que le consommateur a tout lu et attend : il a déjà joué le niveau
	// maintenu en temps réel pendant ce trou. Le remplir ajouterait ce retard à la latence.
	else if (c - d->t > (double)d->stream.prefill * d->cps
			&& atomic_load_explicit(&d->stream.buffering, memory_order_acquire) && gf_audio_buffered(&d->stream) == 0)
		db_anchor(d, cycle, d->value);
	db_advance(d, c);
	d->value = value;
}

void db_render(DbDsp* d, float* out, uint32_t n)
{
	// File, préremplissage, saut et maintien : tronc commun, volume 1 (la sortie est la valeur brute)
	gf_audio_render(&d->stream, out, n);
	const float vol = atomic_load_explicit(&d->volume, memory_order_relaxed);
	// Passe-haut : la Digiblaster réelle est couplée en alternatif, le niveau continu s'éteint
	for (uint32_t i = 0; i < n; i++)
	{
		const float x = out[i];
		const float y = x - d->hp_x + d->hp_r * d->hp_y;
		d->hp_x = x;
		d->hp_y = y;
		out[i] = y * vol;
	}
}
