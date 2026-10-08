#include "greffon_clock.h"

void gf_clock_init(GfSampleClock* c, uint32_t clock_hz, uint32_t rate, uint64_t cycle)
{
	c->clock_hz = clock_hz;
	c->rate = rate;
	gf_clock_anchor(c, cycle);
}

void gf_clock_anchor(GfSampleClock* c, uint64_t cycle)
{
	c->anchor = cycle;
	c->last = cycle;
	c->emitted = 0;
}

uint32_t gf_clock_due(GfSampleClock* c, uint64_t cycle)
{
	if (cycle < c->last)
	{
		gf_clock_anchor(c, cycle);
		return 0;
	}
	c->last = cycle;
	const uint64_t total = (cycle - c->anchor) * c->rate / c->clock_hz;
	const uint64_t due = total - c->emitted;
	c->emitted = total;
	return (uint32_t)due;
}
