#include "greffon_clock.h"
#include "check.h"

static void one_second_gives_rate_samples(void)
{
	GfSampleClock c;
	gf_clock_init(&c, 4000000, 44100, 0);
	CHECK(gf_clock_due(&c, 4000000) == 44100);
	CHECK(gf_clock_due(&c, 4000000) == 0);				// déjà rendu
}

static void no_drift_with_small_steps(void)
{
	GfSampleClock c;
	gf_clock_init(&c, 4000000, 44100, 0);
	uint64_t total = 0;
	for (uint64_t t = 7; t <= 4000000 * 5ull; t += 7)		// pas irrégulier par rapport à 4e6/44100 = 90,7
		total += gf_clock_due(&c, t);
	// dernier t = 19 999 994 T-states = 4,9999985 s -> 220 499 échantillons (valeur calculée à la main)
	CHECK(total == 220499);
}

static void anchor_offsets_the_origin(void)
{
	GfSampleClock c;
	gf_clock_init(&c, 4000000, 48000, 1000000);
	CHECK(gf_clock_due(&c, 1000000) == 0);
	CHECK(gf_clock_due(&c, 1000000 + 4000000) == 48000);
	gf_clock_anchor(&c, 50);
	CHECK(gf_clock_due(&c, 50 + 83) == 0);				// 83 T-states < 1 échantillon (83,33)
	CHECK(gf_clock_due(&c, 50 + 84) == 1);
}

static void backward_time_reanchors(void)
{
	GfSampleClock c;
	gf_clock_init(&c, 4000000, 44100, 0);
	gf_clock_due(&c, 400000);
	CHECK(gf_clock_due(&c, 1000) == 0);					// retour en arrière (reset, snapshot)
	CHECK(gf_clock_due(&c, 1000 + 4000000) == 44100);		// repart de 1000
}

int main(void)
{
	one_second_gives_rate_samples();
	no_drift_with_small_steps();
	anchor_offsets_the_origin();
	backward_time_reanchors();
	return CHECK_DONE();
}
