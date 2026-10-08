#include "digiblaster_dsp.h"
#include <string.h>

static inline float db_level(uint8_t b) { return ((float)b - 128.0f) * (1.0f / 128.0f); }

static void db_push(DbDsp* d, float s)
{
	const uint32_t w = atomic_load_explicit(&d->wr, memory_order_relaxed);
	const uint32_t r = atomic_load_explicit(&d->rd, memory_order_acquire);
	if (w - r >= DB_RING_SIZE) { d->dropped++; return; }
	d->ring[w & (DB_RING_SIZE - 1)] = s;
	atomic_store_explicit(&d->wr, w + 1, memory_order_release);
	d->produced++;
}

static uint32_t db_fill(DbDsp* d)
{
	return atomic_load_explicit(&d->wr, memory_order_acquire) - atomic_load_explicit(&d->rd, memory_order_acquire);
}

void db_init(DbDsp* d, uint32_t rate, uint32_t latency_ms, float volume)
{
	memset(d, 0, sizeof *d);
	d->rate = rate;
	d->cps = DB_CLOCK_HZ / (double)rate;
	d->prefill = (uint32_t)((uint64_t)rate * latency_ms / 1000u);
	if (d->prefill > DB_RING_SIZE / 2) d->prefill = DB_RING_SIZE / 2;
	d->maxfill = d->prefill * 2 + rate / 10;
	if (d->maxfill > DB_RING_SIZE / 2) d->maxfill = DB_RING_SIZE / 2;
	d->hp_r = 1.0f - (6.2831853f * 20.0f) / (float)rate;		// coupure ~20 Hz
	atomic_store(&d->volume, volume);
	atomic_store(&d->buffering, 1);
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
	const float lv = db_level(d->value);
	while (d->t < to)
	{
		const double end = (double)(d->next + 1) * d->cps;
		const double stop = end <= to ? end : to;
		d->acc += (double)lv * (stop - d->t);
		d->t = stop;
		if (d->t >= end)
		{
			db_push(d, (float)(d->acc / d->cps));
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
	else if (c - d->t > (double)d->prefill * d->cps
			&& atomic_load_explicit(&d->buffering, memory_order_acquire) && db_fill(d) == 0)
		db_anchor(d, cycle, d->value);
	db_advance(d, c);
	d->value = value;
}

void db_render(DbDsp* d, float* out, uint32_t n)
{
	const float vol = atomic_load_explicit(&d->volume, memory_order_relaxed);
	uint32_t r = atomic_load_explicit(&d->rd, memory_order_relaxed);
	for (uint32_t i = 0; i < n; i++)
	{
		const uint32_t w = atomic_load_explicit(&d->wr, memory_order_acquire);
		if (w - r > d->maxfill)								// trop de retard accumulé : on saute vers le récent
		{
			const uint32_t keep = d->prefill ? d->prefill : 1;
			d->skipped += (w - r) - keep;
			r = w - keep;
			atomic_store_explicit(&d->rd, r, memory_order_release);
		}
		if (atomic_load_explicit(&d->buffering, memory_order_relaxed))
		{
			// Démarre au préremplissage, ou après l'avoir attendu en temps réel : un son plus court que
			// le préremplissage (un clic) doit être joué quand même, avec une latence constante.
			if (w != r && ((w - r) >= d->prefill || ++d->wait >= d->prefill))
			{
				atomic_store_explicit(&d->buffering, 0, memory_order_release);
				d->wait = 0;
			}
		}
		else
			d->wait = 0;
		if (!atomic_load_explicit(&d->buffering, memory_order_relaxed))
		{
			if (w == r)
			{
				d->underruns++;
				atomic_store_explicit(&d->buffering, 1, memory_order_release);
			}
			else
			{
				d->hold = d->ring[r & (DB_RING_SIZE - 1)];
				r++;
				atomic_store_explicit(&d->rd, r, memory_order_release);
			}
		}
		// Passe-haut : la Digiblaster réelle est couplée en alternatif, le niveau continu s'éteint
		const float y = d->hold - d->hp_x + d->hp_r * d->hp_y;
		d->hp_x = d->hold;
		d->hp_y = y;
		out[i] = y * vol;
	}
}
