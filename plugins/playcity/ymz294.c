#include "ymz294.h"
#include <math.h>
#include <string.h>

static float s_amp[32];							// niveau linéaire par pas de 1,5 dB (0 = muet, 31 = 1,0)
static int s_amp_ready;

static void build_amp(void)
{
	s_amp[0] = 0.0f;
	for (int i = 1; i < 32; ++i)
		s_amp[i] = (float)pow(10.0, (i - 31) * 1.5 / 20.0);
	s_amp_ready = 1;
}

void ymz_reset(Ymz* y)
{
	memset(y, 0, sizeof *y);
	y->lfsr = 1;
}

void ymz_select(Ymz* y, uint8_t reg) { y->sel = reg; }

static void env_restart(Ymz* y)
{
	const int attack = y->reg[13] & 4;
	y->env_step = attack ? 0 : 31;
	y->env_dir = attack ? 1 : -1;
	y->env_hold = 0;
	y->env_cnt = 0;
}

void ymz_write(Ymz* y, uint8_t value)
{
	static const uint8_t mask[14] = { 0xFF, 0x0F, 0xFF, 0x0F, 0xFF, 0x0F, 0x1F, 0xFF, 0x1F, 0x1F, 0x1F, 0xFF, 0xFF, 0x0F };
	if (y->sel >= 14)								// 14 et 15 : pas de ports d'E/S sur le YMZ294
		return;
	y->reg[y->sel] = (uint8_t)(value & mask[y->sel]);
	if (y->sel == 13)
		env_restart(y);
}

// Un pas de l'enveloppe (32 niveaux, forme R13 : bit 3 continue, 2 attaque, 1 alternance, 0 maintien)
static void env_tick(Ymz* y)
{
	if (y->env_hold)
		return;
	const uint8_t shape = y->reg[13];
	int step = y->env_step + y->env_dir;
	if (step >= 0 && step <= 31)
	{
		y->env_step = (int8_t)step;
		return;
	}
	const int up = y->env_dir > 0;
	if (!(shape & 8))								// pas continue : retombe à 0 et y reste
	{
		y->env_step = 0;
		y->env_hold = 1;
	}
	else if (shape & 1)								// maintien : sur le niveau de fin, ou son opposé si alternance
	{
		y->env_step = (int8_t)(((shape & 2) ? !up : up) ? 31 : 0);
		y->env_hold = 1;
	}
	else if (shape & 2)								// alternance : on repart dans l'autre sens
	{
		y->env_dir = (int8_t)-y->env_dir;
		y->env_step = (int8_t)((up ? 31 : 0) + y->env_dir);
	}
	else											// dent de scie : on recommence la rampe
		y->env_step = (int8_t)(up ? 0 : 31);
}

// Un tick interne (horloge AY / 8)
static void step(Ymz* y)
{
	for (int i = 0; i < 3; ++i)
	{
		unsigned p = y->reg[2 * i] | ((unsigned)y->reg[2 * i + 1] << 8);
		if (p == 0) p = 1;
		if (++y->tone_cnt[i] >= p)
		{
			y->tone_cnt[i] = 0;
			y->tone_out[i] ^= 1;
		}
	}
	unsigned np = y->reg[6];
	if (np == 0) np = 1;
	if (++y->noise_cnt >= np * 2)
	{
		y->noise_cnt = 0;
		const uint32_t fb = (y->lfsr ^ (y->lfsr >> 3)) & 1;
		y->lfsr = (y->lfsr >> 1) | (fb << 16);
		y->noise_out = (uint8_t)(y->lfsr & 1);
	}
	unsigned ep = y->reg[11] | ((unsigned)y->reg[12] << 8);
	if (ep == 0) ep = 1;
	if (++y->env_cnt >= ep)
	{
		y->env_cnt = 0;
		env_tick(y);
	}
}

static float level(const Ymz* y)
{
	const uint8_t mix = y->reg[7];
	float sum = 0.0f;
	for (int i = 0; i < 3; ++i)
	{
		const int tone = y->tone_out[i] | ((mix >> i) & 1);
		const int noise = y->noise_out | ((mix >> (i + 3)) & 1);
		if (!(tone & noise))
			continue;
		const uint8_t v = y->reg[8 + i];
		const int idx = (v & 0x10) ? y->env_step : ((v & 0x0F) ? (v & 0x0F) * 2 + 1 : 0);
		sum += s_amp[idx];
	}
	return sum / 3.0f;
}

void ymz_render(Ymz* y, double ay_hz, uint32_t rate, float* out, uint32_t n)
{
	if (!s_amp_ready)
		build_amp();
	if (y->tick_left <= 0.0)
		y->tick_left = 1.0;
	const double per_sample = ay_hz / 8.0 / (double)rate;		// ticks internes par échantillon
	float lv = level(y);
	for (uint32_t i = 0; i < n; ++i)
	{
		double need = per_sample, acc = 0.0;
		while (need > 0.0)
		{
			const double take = need < y->tick_left ? need : y->tick_left;
			acc += (double)lv * take;
			need -= take;
			y->tick_left -= take;
			if (y->tick_left <= 1e-12)
			{
				step(y);
				lv = level(y);
				y->tick_left = 1.0;
			}
		}
		out[i] = (float)(acc / per_sample);
	}
}
