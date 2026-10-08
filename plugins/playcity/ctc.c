#include "ctc.h"
#include <string.h>

#define CTRL_INT		0x80
#define CTRL_COUNTER	0x40
#define CTRL_PRESC256	0x20
#define CTRL_TRIGGER	0x08
#define CTRL_TC_FOLLOWS	0x04
#define CTRL_RESET		0x02

static unsigned count_period(const CtcChannel* h) { return h->count_max ? h->count_max : 256u; }
static unsigned prescaler(const CtcChannel* h)    { return (h->ctrl & CTRL_COUNTER) ? 1u : ((h->ctrl & CTRL_PRESC256) ? 256u : 16u); }

void ctc_reset(Ctc* c) { memset(c, 0, sizeof *c); }

void ctc_write(Ctc* c, unsigned channel, uint8_t value)
{
	CtcChannel* h = &c->ch[channel & 3];
	if (h->wait_tc)
	{
		h->wait_tc = 0;
		h->tc_loaded = 1;
		h->count_max = value;
		if (!(h->ctrl & CTRL_COUNTER) && !h->count_ena)		// timer arrêté : (re)démarrage
		{
			if (h->ctrl & CTRL_TRIGGER)
				h->wait_trig = 1;
			else
				h->start_delay = 2;
		}
		if (h->ctrl & CTRL_COUNTER)							// compteur : rechargé tout de suite
		{
			h->ph = 0;
			h->dc = value;
		}
		return;
	}
	if (value & 1)											// mot de contrôle
	{
		h->ctrl = value;
		h->wait_tc = (value & CTRL_TC_FOLLOWS) ? 1 : 0;
		h->start_delay = 0;
		h->wait_trig = 0;
		if (value & CTRL_RESET)
		{
			h->count_ena = 0;
			h->tc_loaded = 0;
		}
	}
	else if ((channel & 3) == 0)							// mot de vecteur (canal 0 seulement)
		c->vector = value & 0xF8;
}

uint8_t ctc_read(const Ctc* c, unsigned channel) { return c->ch[channel & 3].dc; }

// Applique k pas du compteur descendant : il y a échéance (ZC/TO) quand le compteur vaut 1 ; il est alors rechargé.
static uint32_t count_steps(CtcChannel* h, uint64_t k)
{
	const unsigned n = h->dc ? h->dc : 256u;				// pas jusqu'à la prochaine échéance
	if (k < n)
	{
		h->dc = (uint8_t)(h->dc - k);
		return 0;
	}
	k -= n;
	const unsigned per = count_period(h);
	h->dc = (uint8_t)(h->count_max - (k % per));
	return 1 + (uint32_t)(k / per);
}

static void emit(CtcChannel* h, uint32_t zc, const uint8_t* blocked)
{
	if (!zc)
		return;
	h->zc += zc;
	if ((h->ctrl & CTRL_INT) && !*blocked)
		h->int_reg = 1;
}

// Un canal sur `n` cycles Phi ; `ext` = impulsions actives sur son CLK/TRG hors horloge Phi. Renvoie les échéances.
static uint32_t run_channel(CtcChannel* h, uint32_t n, uint64_t ext, int phi_trg)
{
	if (!h->tc_loaded)
		return 0;
	if (h->ctrl & CTRL_COUNTER)
		return count_steps(h, phi_trg ? n : ext);

	// timer : démarrage par CLK/TRG, ou retard de démarrage
	if (h->wait_trig)
	{
		if (phi_trg ? 1 : (ext != 0))
		{
			h->wait_trig = 0;
			h->start_delay = 2;
		}
		else
			return 0;
	}
	if (h->start_delay)
	{
		const uint32_t d = (n < h->start_delay) ? n : h->start_delay;
		h->start_delay = (uint8_t)(h->start_delay - d);
		n -= d;
		if (!h->start_delay)
		{
			h->count_ena = 1;
			h->dc = h->count_max;
			h->ph = 0;
		}
	}
	if (!h->count_ena || !n)
		return 0;
	const unsigned presc = prescaler(h);
	const uint64_t total = (uint64_t)h->ph + n;
	h->ph = (uint16_t)(total % presc);
	return count_steps(h, total / presc);
}

void ctc_advance(Ctc* c, uint32_t phi_cycles, uint32_t trg1_events)
{
	uint32_t zc2 = 0;
	for (unsigned i = 0; i < CTC_CHANNELS; ++i)
	{
		CtcChannel* h = &c->ch[i];
		uint32_t zc;
		if (i == 1)       zc = run_channel(h, phi_cycles, trg1_events, 0);
		else if (i == 3)  zc = run_channel(h, phi_cycles, zc2, 0);
		else              zc = run_channel(h, phi_cycles, 0, 1);
		if (i == 2)
			zc2 = zc;
		uint8_t blocked = 0;								// priorité : un canal ≤ i en service bloque la demande
		for (unsigned j = 0; j <= i; ++j)
			if (c->ch[j].in_service)
				blocked = 1;
		emit(h, zc, &blocked);
	}
}

unsigned ctc_int_pending(const Ctc* c)
{
	unsigned m = 0;
	for (unsigned i = 0; i < CTC_CHANNELS; ++i)
		if (c->ch[i].int_reg)
			m |= 1u << i;
	return m;
}

int ctc_ack(Ctc* c, uint8_t* vector)
{
	for (unsigned i = 0; i < CTC_CHANNELS; ++i)
		if (c->ch[i].int_reg)
		{
			c->ch[i].int_reg = 0;
			c->ch[i].in_service = 1;
			*vector = (uint8_t)(c->vector | (i << 1));
			return 1;
		}
	return 0;
}

void ctc_reti(Ctc* c)
{
	for (unsigned i = 0; i < CTC_CHANNELS; ++i)
		if (c->ch[i].in_service)
		{
			c->ch[i].in_service = 0;
			return;
		}
}

uint32_t ctc_take_zc(Ctc* c, unsigned channel)
{
	const uint32_t z = c->ch[channel & 3].zc;
	c->ch[channel & 3].zc = 0;
	return z;
}

unsigned ctc_ch0_period(const Ctc* c)
{
	const CtcChannel* h = &c->ch[0];
	if (!h->tc_loaded)
		return 0;
	if (h->ctrl & CTRL_COUNTER)
		return count_period(h);
	return h->count_ena ? prescaler(h) * count_period(h) : 0;
}
