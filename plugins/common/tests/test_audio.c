#include "plugin_audio.h"
#include "check.h"
#include <stdlib.h>
#include <math.h>

// 44100 Hz, latence 10 ms -> préremplissage 441 trames
static GfAudioStream* make(uint32_t channels, float volume)
{
	GfAudioStream* s = calloc(1, sizeof *s);
	gf_audio_init(s, 44100, channels, 10, volume);
	return s;
}

static void push_ramp(GfAudioStream* s, int from, int n)			// mono : valeur = indice / 1000
{
	for (int i = 0; i < n; ++i)
	{
		const float f = (float)(from + i) / 1000.0f;
		CHECK(gf_audio_push(s, &f));
	}
}

static void plays_in_order_once_prefilled(void)
{
	GfAudioStream* s = make(1, 1.0f);
	CHECK(s->prefill == 441);
	push_ramp(s, 1, 500);
	CHECK(gf_audio_buffered(s) == 500);
	float out[500];
	gf_audio_render(s, out, 500);
	for (int i = 0; i < 500; ++i)
		CHECK(fabsf(out[i] - (float)(i + 1) / 1000.0f) < 1e-6f);
	free(s);
}

static void short_sound_is_played_after_waiting_prefill(void)		// un clic plus court que le préremplissage
{
	GfAudioStream* s = make(1, 1.0f);
	push_ramp(s, 1, 10);
	float out[460];
	gf_audio_render(s, out, 460);
	for (int i = 0; i < 440; ++i)
		CHECK(out[i] == 0.0f);										// attente en temps réel : silence maintenu
	for (int i = 0; i < 10; ++i)
		CHECK(fabsf(out[440 + i] - (float)(i + 1) / 1000.0f) < 1e-6f);	// puis le clic, latence constante
	free(s);
}

static void stereo_frames_stay_interleaved(void)
{
	GfAudioStream* s = make(2, 1.0f);
	for (int i = 0; i < 500; ++i)
	{
		const float f[2] = { (float)(i + 1), -(float)(i + 1) };
		CHECK(gf_audio_push(s, f));
	}
	float out[2 * 500];
	gf_audio_render(s, out, 500);
	for (int i = 0; i < 500; ++i)
	{
		CHECK(out[2 * i] == (float)(i + 1));
		CHECK(out[2 * i + 1] == -(float)(i + 1));
	}
	free(s);
}

static void underrun_holds_last_frame_and_rebuffers(void)
{
	GfAudioStream* s = make(1, 1.0f);
	push_ramp(s, 1000, 500);										// dernière valeur : 1,499
	float out[600];
	gf_audio_render(s, out, 600);
	CHECK(fabsf(out[499] - 1.499f) < 1e-6f);
	for (int i = 500; i < 600; ++i)
		CHECK(fabsf(out[i] - 1.499f) < 1e-6f);						// maintenu
	CHECK(s->underruns == 1);
	free(s);
}

static void far_behind_jumps_to_recent(void)
{
	GfAudioStream* s = make(1, 1.0f);
	push_ramp(s, 0, 30000);											// bien au-delà de maxfill (= 2*441 + 4410)
	float out[1];
	gf_audio_render(s, out, 1);
	CHECK(s->skipped > 0);
	CHECK(gf_audio_buffered(s) <= s->prefill);						// ne garde que le préremplissage
	CHECK(out[0] > 29.0f);											// valeur récente (index > 29000)
	free(s);
}

static void full_ring_drops_and_counts(void)
{
	GfAudioStream* s = make(1, 1.0f);
	const float f = 0.5f;
	int refused = 0;
	for (uint32_t i = 0; i < GF_AUDIO_RING_FRAMES + 10; ++i)
		if (!gf_audio_push(s, &f)) ++refused;
	CHECK(refused == 10);
	CHECK(s->dropped == 10);
	free(s);
}

static void volume_scales_output(void)
{
	GfAudioStream* s = make(1, 0.5f);
	push_ramp(s, 2000, 500);
	float out[1];
	gf_audio_render(s, out, 1);
	CHECK(fabsf(out[0] - 1.0f) < 1e-6f);							// 2,000 * 0,5
	atomic_store(&s->volume, 0.25f);
	gf_audio_render(s, out, 1);
	CHECK(fabsf(out[0] - 0.50025f) < 1e-6f);						// 2,001 * 0,25
	free(s);
}

int main(void)
{
	plays_in_order_once_prefilled();
	short_sound_is_played_after_waiting_prefill();
	stereo_frames_stay_interleaved();
	underrun_holds_last_frame_and_rebuffers();
	far_behind_jumps_to_recent();
	full_ring_drops_and_counts();
	volume_scales_output();
	return CHECK_DONE();
}
