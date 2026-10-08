#include "playcity_card.h"
#include <string.h>

#define CHUNK 512u

void pc_init(PlayCity* p, GfAudioStream* stream, const PcLines* lines, int swap_channels)
{
	memset(p, 0, sizeof *p);
	p->stream = stream;
	p->lines = *lines;
	p->swap_channels = swap_channels;
	p->int_level = p->nmi_level = 1;
	p->hp_r = 1.0f - (6.2831853f * 20.0f) / (float)stream->rate;	// coupure ~20 Hz
	gf_clock_init(&p->clock, PC_CLOCK_HZ, stream->rate, 0);
	ctc_reset(&p->ctc);
	ymz_reset(&p->ymz[0]);
	ymz_reset(&p->ymz[1]);
}

double pc_ay_hz(const PlayCity* p)
{
	// ZC/TO0 masque un front de l'horloge 4 MHz par période (en moyenne une demi-période de Phi) :
	// débit des fronts = 4 MHz * (1 - 0,5 / période) ; le YMZ294 divise par 2 en interne.
	const unsigned period = ctc_ch0_period(&p->ctc);
	const double ce = period ? (double)PC_CLOCK_HZ * (1.0 - 0.5 / (double)period) : (double)PC_CLOCK_HZ;
	return ce / 2.0;
}

static void set_int(PlayCity* p, int level)
{
	if (level == p->int_level)
		return;
	p->int_level = level;
	if (p->lines.set_int)
		p->lines.set_int(p->lines.user, level);
}

static void set_nmi(PlayCity* p, int level)
{
	if (level == p->nmi_level)
		return;
	p->nmi_level = level;
	if (p->lines.set_nmi)
		p->lines.set_nmi(p->lines.user, level);
}

static void produce_audio(PlayCity* p, uint32_t n)
{
	float l[CHUNK], r[CHUNK];
	const double ay = pc_ay_hz(p);
	const unsigned first = p->swap_channels ? 1 : 0;			// puce « droite » (&F884) = ymz[0] avant swap
	while (n)
	{
		const uint32_t k = n < CHUNK ? n : CHUNK;
		ymz_render(&p->ymz[0], ay, p->stream->rate, (first == 0) ? r : l, k);
		ymz_render(&p->ymz[1], ay, p->stream->rate, (first == 0) ? l : r, k);
		for (uint32_t i = 0; i < k; ++i)
		{
			const float x[2] = { l[i], r[i] };
			float f[2];
			for (int c = 0; c < 2; ++c)
			{
				f[c] = x[c] - p->hp_x[c] + p->hp_r * p->hp_y[c];
				p->hp_x[c] = x[c];
				p->hp_y[c] = f[c];
			}
			gf_audio_push(p->stream, f);
		}
		n -= k;
	}
}

void pc_tick(PlayCity* p, uint64_t cycle)
{
	if (cycle < p->last_cycle)									// temps revenu en arrière : on repart d'ici
	{
		p->last_cycle = cycle;
		gf_clock_anchor(&p->clock, cycle);
		return;
	}
	const uint64_t delta = cycle - p->last_cycle;
	p->last_cycle = cycle;

	const uint32_t cursor = p->cursor_pending;
	p->cursor_pending = 0;
	ctc_advance(&p->ctc, delta > 0xFFFFFFFFu ? 0xFFFFFFFFu : (uint32_t)delta, cursor);

	produce_audio(p, gf_clock_due(&p->clock, cycle));

	// NMI : front descendant tenu jusqu'au tick suivant (le Z80 la verrouille sur le front)
	if (p->nmi_level == 0)
		set_nmi(p, 1);
	if (ctc_take_zc(&p->ctc, 1))
		set_nmi(p, 0);
	ctc_take_zc(&p->ctc, 0); ctc_take_zc(&p->ctc, 2); ctc_take_zc(&p->ctc, 3);

	set_int(p, ctc_int_pending(&p->ctc) ? 0 : 1);
}

void pc_reset(PlayCity* p, uint64_t cycle)
{
	ctc_reset(&p->ctc);
	ymz_reset(&p->ymz[0]);
	ymz_reset(&p->ymz[1]);
	p->cursor_pending = 0;
	p->last_cycle = cycle;
	gf_clock_anchor(&p->clock, cycle);
	memset(p->hp_x, 0, sizeof p->hp_x);
	memset(p->hp_y, 0, sizeof p->hp_y);
	set_int(p, 1);
	set_nmi(p, 1);
}

int pc_io_in(PlayCity* p, uint16_t port, uint64_t cycle, uint8_t* data)
{
	if ((port & 0xFFFC) != 0xF880)								// seul le CTC se lit
		return 0;
	pc_tick(p, cycle);
	*data = ctc_read(&p->ctc, port & 3);
	return 1;
}

void pc_io_out(PlayCity* p, uint16_t port, uint8_t data, uint64_t cycle)
{
	if (port == 0xF8FF)
	{
		pc_reset(p, cycle);
		return;
	}
	if ((port & 0xFFFC) == 0xF880)
	{
		pc_tick(p, cycle);
		ctc_write(&p->ctc, port & 3, data);
		set_int(p, ctc_int_pending(&p->ctc) ? 0 : 1);
		return;
	}
	// YMZ : A15-A9 = 1111100, A7-A4 = 8 ; A2 = puce 0, A3 = puce 1 ; A8 = sélection de registre
	if ((port & 0xFE00) == 0xF800 && (port & 0x00F0) == 0x0080 && (port & 0x000C))
	{
		pc_tick(p, cycle);
		for (int chip = 0; chip < 2; ++chip)
		{
			if (!(port & (chip ? 0x0008 : 0x0004)))
				continue;
			if (port & 0x0100)
				ymz_select(&p->ymz[chip], data);
			else
				ymz_write(&p->ymz[chip], data);
		}
	}
}

int pc_int_ack(PlayCity* p, uint64_t cycle, uint8_t* vector)
{
	pc_tick(p, cycle);
	if (!ctc_ack(&p->ctc, vector))
		return 0;
	// RETI non observable par l'ABI : on libère le canal tout de suite (approximation documentée,
	// docs/extensions.md) ; INT reste basse si une autre demande est déjà retenue.
	ctc_reti(&p->ctc);
	set_int(p, ctc_int_pending(&p->ctc) ? 0 : 1);
	return 1;
}

void pc_cursor(PlayCity* p, uint64_t cycle)
{
	pc_tick(p, cycle);
	++p->cursor_pending;
}
