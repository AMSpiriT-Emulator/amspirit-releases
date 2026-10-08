#include "greffon_audio.h"
#include <string.h>

#define MASK	(GF_AUDIO_RING_FRAMES - 1)

void gf_audio_init(GfAudioStream* s, uint32_t rate, uint32_t channels, uint32_t latency_ms, float volume)
{
	memset(s, 0, sizeof *s);
	s->rate = rate;
	s->channels = channels;
	s->prefill = (uint32_t)((uint64_t)rate * latency_ms / 1000u);
	if (s->prefill > GF_AUDIO_RING_FRAMES / 2) s->prefill = GF_AUDIO_RING_FRAMES / 2;
	s->maxfill = s->prefill * 2 + rate / 10;
	if (s->maxfill > GF_AUDIO_RING_FRAMES / 2) s->maxfill = GF_AUDIO_RING_FRAMES / 2;
	atomic_store(&s->volume, volume);
	atomic_store(&s->buffering, 1);
}

int gf_audio_push(GfAudioStream* s, const float* frame)
{
	const uint32_t w = atomic_load_explicit(&s->wr, memory_order_relaxed);
	const uint32_t r = atomic_load_explicit(&s->rd, memory_order_acquire);
	if (w - r >= GF_AUDIO_RING_FRAMES) { s->dropped++; return 0; }
	memcpy(&s->ring[(size_t)(w & MASK) * s->channels], frame, sizeof(float) * s->channels);
	atomic_store_explicit(&s->wr, w + 1, memory_order_release);
	s->pushed++;
	return 1;
}

uint32_t gf_audio_buffered(const GfAudioStream* s)
{
	return atomic_load_explicit(&s->wr, memory_order_acquire) - atomic_load_explicit(&s->rd, memory_order_acquire);
}

void gf_audio_render(GfAudioStream* s, float* out, uint32_t frames)
{
	const float vol = atomic_load_explicit(&s->volume, memory_order_relaxed);
	uint32_t r = atomic_load_explicit(&s->rd, memory_order_relaxed);
	for (uint32_t i = 0; i < frames; i++)
	{
		const uint32_t w = atomic_load_explicit(&s->wr, memory_order_acquire);
		if (w - r > s->maxfill)								// trop de retard accumulé : on saute vers le récent
		{
			const uint32_t keep = s->prefill ? s->prefill : 1;
			s->skipped += (w - r) - keep;
			r = w - keep;
			atomic_store_explicit(&s->rd, r, memory_order_release);
		}
		if (atomic_load_explicit(&s->buffering, memory_order_relaxed))
		{
			// Démarre au préremplissage, ou après l'avoir attendu en temps réel : un son plus court que
			// le préremplissage (un clic) doit être joué quand même, avec une latence constante.
			if (w != r && ((w - r) >= s->prefill || ++s->wait >= s->prefill))
			{
				atomic_store_explicit(&s->buffering, 0, memory_order_release);
				s->wait = 0;
			}
		}
		else
			s->wait = 0;
		if (!atomic_load_explicit(&s->buffering, memory_order_relaxed))
		{
			if (w == r)
			{
				s->underruns++;
				atomic_store_explicit(&s->buffering, 1, memory_order_release);
			}
			else
			{
				memcpy(s->hold, &s->ring[(size_t)(r & MASK) * s->channels], sizeof(float) * s->channels);
				r++;
				atomic_store_explicit(&s->rd, r, memory_order_release);
			}
		}
		for (uint32_t c = 0; c < s->channels; c++)
			out[(size_t)i * s->channels + c] = s->hold[c] * vol;
	}
}
