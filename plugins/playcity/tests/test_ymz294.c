#include "ymz294.h"
#include "check.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define RATE 44100

static void wr(Ymz* y, uint8_t reg, uint8_t v) { ymz_select(y, reg); ymz_write(y, v); }

static double mean(const float* b, uint32_t n)
{
	double s = 0;
	for (uint32_t i = 0; i < n; ++i) s += b[i];
	return s / n;
}

// Nombre de montées à travers la moyenne : fréquence d'un signal périodique rendu pendant 1 s
static unsigned rising_crossings(const float* b, uint32_t n)
{
	const double m = mean(b, n);
	unsigned c = 0;
	for (uint32_t i = 1; i < n; ++i)
		if (b[i - 1] < m && b[i] >= m) ++c;
	return c;
}

static void tone_a(Ymz* y, unsigned period, uint8_t vol)
{
	wr(y, 0, (uint8_t)(period & 0xFF));
	wr(y, 1, (uint8_t)(period >> 8));
	wr(y, 7, 0x3E);										// tonalité A seule
	wr(y, 8, vol);
}

static void silent_after_reset(void)
{
	Ymz y; ymz_reset(&y);
	float out[1000];
	ymz_render(&y, 1e6, RATE, out, 1000);
	for (int i = 0; i < 1000; ++i) CHECK(out[i] == 0.0f);
}

static void tone_frequency_follows_period_and_clock(void)
{
	static float out[RATE];
	Ymz y; ymz_reset(&y);
	tone_a(&y, 284, 15);								// 1 MHz / (16 * 284) = 220,07 Hz
	ymz_render(&y, 1e6, RATE, out, RATE);
	const unsigned f1 = rising_crossings(out, RATE);
	CHECK(f1 >= 219 && f1 <= 221);

	ymz_render(&y, 2e6, RATE, out, RATE);				// horloge doublée : une octave plus haut
	const unsigned f2 = rising_crossings(out, RATE);
	CHECK(f2 >= 439 && f2 <= 442);
}

static void volume_steps_are_3db(void)
{
	static float a[RATE / 2], b[RATE / 2];
	Ymz y; ymz_reset(&y);
	tone_a(&y, 284, 15);
	ymz_render(&y, 1e6, RATE, a, RATE / 2);
	wr(&y, 8, 13);										// deux pas de moins : -6 dB = moitié
	ymz_render(&y, 1e6, RATE, b, RATE / 2);
	const double r = mean(b, RATE / 2) / mean(a, RATE / 2);
	CHECK(fabs(r - 0.5) < 0.02);
}

static void max_level_is_one_third_per_voice(void)
{
	static float out[RATE / 2];
	Ymz y; ymz_reset(&y);
	wr(&y, 7, 0xFF);									// tout coupé : la sortie vaut 1 en continu (comme l'AY réel)
	wr(&y, 8, 15);
	ymz_render(&y, 1e6, RATE, out, RATE / 2);
	for (int i = 100; i < 200; ++i) CHECK(fabsf(out[i] - 1.0f / 3.0f) < 1e-4f);
	wr(&y, 9, 15); wr(&y, 10, 15);
	ymz_render(&y, 1e6, RATE, out, RATE / 2);
	CHECK(fabsf(out[150] - 1.0f) < 1e-4f);
}

static void noise_is_irregular_with_expected_level(void)
{
	static float out[RATE];
	Ymz y; ymz_reset(&y);
	wr(&y, 6, 1);
	wr(&y, 7, 0x37);									// bruit A seul
	wr(&y, 8, 15);
	ymz_render(&y, 1e6, RATE, out, RATE);
	const double m = mean(out, RATE);
	CHECK(fabs(m - 1.0 / 6.0) < 0.02);					// ~ la moitié du temps à 1/3
	unsigned changes = 0;
	for (uint32_t i = 1; i < RATE; ++i)
		if (fabsf(out[i] - out[i - 1]) > 0.01f) ++changes;
	CHECK(changes > 5000);
	const unsigned f = rising_crossings(out, RATE);
	CHECK(f > 3000);									// bruit large bande, pas une note
	// reproductible : même état de départ, même séquence
	Ymz y2; ymz_reset(&y2);
	wr(&y2, 6, 1); wr(&y2, 7, 0x37); wr(&y2, 8, 15);
	static float out2[RATE];
	ymz_render(&y2, 1e6, RATE, out2, RATE);
	CHECK(memcmp(out, out2, sizeof out) == 0);
}

static void envelope_ramp_up_then_hold(void)			// forme 13 : /‾‾‾
{
	static float out[4410];
	Ymz y; ymz_reset(&y);
	wr(&y, 7, 0xFF);
	wr(&y, 8, 0x10);									// amplitude = enveloppe
	wr(&y, 11, 2); wr(&y, 12, 0);						// période 2 : 32 pas en 64 ticks internes (~0,5 ms)
	wr(&y, 13, 0x0D);
	ymz_render(&y, 1e6, RATE, out, 4410);
	CHECK(out[0] < 0.05f);
	for (int i = 1; i < 4410; ++i) CHECK(out[i] >= out[i - 1] - 1e-6f);
	CHECK(fabsf(out[4409] - 1.0f / 3.0f) < 1e-4f);
}

static void envelope_ramp_down_then_zero(void)			// forme 9 : \___
{
	static float out[4410];
	Ymz y; ymz_reset(&y);
	wr(&y, 7, 0xFF); wr(&y, 8, 0x10);
	wr(&y, 11, 2); wr(&y, 12, 0);
	wr(&y, 13, 0x09);
	ymz_render(&y, 1e6, RATE, out, 4410);
	CHECK(out[0] > 0.2f);
	CHECK(out[4409] == 0.0f);
}

static void envelope_triangle_goes_down_then_up(void)	// forme 10 : \/\/ (période longue pour observer)
{
	static float out[RATE];
	Ymz y; ymz_reset(&y);
	wr(&y, 7, 0xFF); wr(&y, 8, 0x10);
	wr(&y, 11, 0x20); wr(&y, 12, 0);					// 32 pas de 32 ticks internes ~ 8 ms
	wr(&y, 13, 0x0A);
	ymz_render(&y, 1e6, RATE, out, RATE);
	float mn = 1, mx = 0; uint32_t imin = 0;
	for (uint32_t i = 0; i < RATE / 2; ++i) { if (out[i] < mn) { mn = out[i]; imin = i; } if (out[i] > mx) mx = out[i]; }
	CHECK(mx > 0.30f && mn < 0.01f);
	CHECK(imin > 100 && imin < RATE / 2 - 100);			// le minimum est au milieu : descente puis remontée
}

static void registers_are_masked_and_write_only(void)
{
	Ymz y; ymz_reset(&y);
	wr(&y, 1, 0xFF);	CHECK(y.reg[1] == 0x0F);			// période haute : 4 bits
	wr(&y, 6, 0xFF);	CHECK(y.reg[6] == 0x1F);			// bruit : 5 bits
	wr(&y, 13, 0xFF);	CHECK(y.reg[13] == 0x0F);
	wr(&y, 8, 0xFF);	CHECK(y.reg[8] == 0x1F);
	const uint8_t before14 = y.reg[14];
	wr(&y, 14, 0x55);	CHECK(y.reg[14] == before14);		// pas de port E/S sur le YMZ294
	wr(&y, 15, 0x55);	CHECK(y.reg[15] == 0);
	ymz_select(&y, 200); ymz_write(&y, 0x77);				// sélection invalide : ignorée
	for (int i = 0; i < 14; ++i) CHECK(y.reg[i] != 0x77);
}

static void reset_clears_registers(void)
{
	static float out[100];
	Ymz y; ymz_reset(&y);
	tone_a(&y, 100, 15);
	ymz_reset(&y);
	ymz_render(&y, 1e6, RATE, out, 100);
	for (int i = 0; i < 100; ++i) CHECK(out[i] == 0.0f);
}

int main(void)
{
	silent_after_reset();
	tone_frequency_follows_period_and_clock();
	volume_steps_are_3db();
	max_level_is_one_third_per_voice();
	noise_is_irregular_with_expected_level();
	envelope_ramp_up_then_hold();
	envelope_ramp_down_then_zero();
	envelope_triangle_goes_down_then_up();
	registers_are_masked_and_write_only();
	reset_clears_registers();
	return CHECK_DONE();
}
