#include "playcity_card.h"
#include "check.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define RATE 44100

typedef struct Fixture
{
	PlayCity		pc;
	GfAudioStream*	stream;
	int				int_level, nmi_level;
	unsigned		nmi_falls;
} Fixture;

static void set_int(void* u, int l) { ((Fixture*)u)->int_level = l; }
static void set_nmi(void* u, int l) { Fixture* f = u; if (f->nmi_level && !l) ++f->nmi_falls; f->nmi_level = l; }

static Fixture* make(int swap)
{
	Fixture* f = calloc(1, sizeof *f);
	f->stream = calloc(1, sizeof *f->stream);
	gf_audio_init(f->stream, RATE, 2, 10, 1.0f);
	f->stream->maxfill = GF_AUDIO_RING_FRAMES;					// test : lecture différée, pas de saut vers le récent
	f->int_level = f->nmi_level = 1;
	PcLines l = { f, set_int, set_nmi };
	pc_init(&f->pc, f->stream, &l, swap);
	return f;
}

static void done(Fixture* f) { free(f->stream); free(f); }

// Avance par pas de `step` T-states jusqu'à `until`
static uint64_t run(Fixture* f, uint64_t from, uint64_t until, unsigned step)
{
	for (uint64_t t = from + step; t <= until; t += step) pc_tick(&f->pc, t);
	return until;
}

static void ay_write(Fixture* f, uint16_t sel_port, uint16_t data_port, uint8_t reg, uint8_t v, uint64_t cyc)
{
	pc_io_out(&f->pc, sel_port, reg, cyc);
	pc_io_out(&f->pc, data_port, v, cyc);
}
#define RIGHT(f, reg, v, c) ay_write(f, 0xF984, 0xF884, reg, v, c)
#define LEFT(f, reg, v, c)  ay_write(f, 0xF988, 0xF888, reg, v, c)

// Lit toutes les trames disponibles : renvoie le nombre, remplit L/R
static uint32_t drain(Fixture* f, float* l, float* r, uint32_t max)
{
	uint32_t n = gf_audio_buffered(f->stream);
	if (n > max) n = max;
	float fr[2];
	GfAudioStream* s = f->stream;
	atomic_store(&s->buffering, 0);							// lecture directe, sans préremplissage
	for (uint32_t i = 0; i < n; ++i)
	{
		gf_audio_render(s, fr, 1);
		l[i] = fr[0]; r[i] = fr[1];
	}
	return n;
}

static double peak(const float* b, uint32_t n)
{
	double m = 0;
	for (uint32_t i = 0; i < n; ++i) if (fabs(b[i]) > m) m = fabs(b[i]);
	return m;
}

static unsigned crossings(const float* b, uint32_t n)
{
	double mean = 0;
	for (uint32_t i = 0; i < n; ++i) mean += b[i];
	mean /= n;
	unsigned c = 0;
	for (uint32_t i = 1; i < n; ++i) if (b[i - 1] < mean && b[i] >= mean) ++c;
	return c;
}

static float L[RATE * 2], R[RATE * 2];

static void right_chip_is_right_channel(void)
{
	Fixture* f = make(0);
	RIGHT(f, 0, 0x1C, 0); RIGHT(f, 1, 0x01, 0); RIGHT(f, 7, 0x3E, 0); RIGHT(f, 8, 15, 0);
	run(f, 0, 4000000, 20);
	const uint32_t n = drain(f, L, R, RATE * 2);
	CHECK(n >= RATE - 2);
	CHECK(peak(L, n) < 1e-6);
	CHECK(peak(R, n) > 0.01);
	done(f);
}

static void left_chip_and_swap_option(void)
{
	Fixture* f = make(0);
	LEFT(f, 0, 0x1C, 0); LEFT(f, 1, 0x01, 0); LEFT(f, 7, 0x3E, 0); LEFT(f, 8, 15, 0);
	run(f, 0, 4000000, 20);
	uint32_t n = drain(f, L, R, RATE * 2);
	CHECK(peak(L, n) > 0.01);
	CHECK(peak(R, n) < 1e-6);
	done(f);

	f = make(1);											// swap : &F884 devient la gauche
	RIGHT(f, 0, 0x1C, 0); RIGHT(f, 1, 0x01, 0); RIGHT(f, 7, 0x3E, 0); RIGHT(f, 8, 15, 0);
	run(f, 0, 4000000, 20);
	n = drain(f, L, R, RATE * 2);
	CHECK(peak(L, n) > 0.01);
	CHECK(peak(R, n) < 1e-6);
	done(f);
}

static void ymz_clock_follows_ctc_channel_0(void)
{
	Fixture* f = make(0);
	CHECK(fabs(pc_ay_hz(&f->pc) - 2e6) < 1);				// non programmé : 4 MHz / 2 = « ST »
	RIGHT(f, 0, 0x1C, 0); RIGHT(f, 1, 0x01, 0); RIGHT(f, 7, 0x3E, 0); RIGHT(f, 8, 15, 0);
	run(f, 0, 4000000, 20);
	uint32_t n = drain(f, L, R, RATE * 2);
	unsigned c = crossings(R, n);
	CHECK(c >= 438 && c <= 442);							// 2 MHz / (16 * 284) = 440 Hz

	pc_io_out(&f->pc, 0xF880, 0x7F, 4000000);				// canal 0 : compteur, TC = 1 -> 1 MHz (CPC)
	pc_io_out(&f->pc, 0xF880, 0x01, 4000000);
	CHECK(fabs(pc_ay_hz(&f->pc) - 1e6) < 1);
	run(f, 4000000, 8000000, 20);
	n = drain(f, L, R, RATE * 2);
	c = crossings(R, n);
	CHECK(c >= 218 && c <= 222);							// 220 Hz
	done(f);
}

static void ay_clock_matches_the_wiki_table(void)
{
	static const struct { unsigned tc; double ymz_mhz; } t[] = {
		{ 2, 1.50 }, { 3, 1.667 }, { 4, 1.75 }, { 0x0F, 1.9333 }, { 0, 1.9961 } };
	for (unsigned i = 0; i < sizeof t / sizeof *t; ++i)
	{
		Fixture* f = make(0);
		pc_io_out(&f->pc, 0xF880, 0x7F, 0);
		pc_io_out(&f->pc, 0xF880, (uint8_t)t[i].tc, 0);
		CHECK(fabs(pc_ay_hz(&f->pc) / 1e6 - t[i].ymz_mhz) < 0.005);
		done(f);
	}
}

static void ctc_ports_are_readable_and_writable(void)
{
	Fixture* f = make(0);
	pc_io_out(&f->pc, 0xF882, 0xA5, 0);						// timer, prédiv. 256, int, TC suit
	pc_io_out(&f->pc, 0xF882, 100, 0);
	uint8_t v = 0;
	pc_tick(&f->pc, 2);
	CHECK(pc_io_in(&f->pc, 0xF882, 2, &v) == 1);
	CHECK(v == 100);
	CHECK(pc_io_in(&f->pc, 0xF884, 2, &v) == 0);			// registres YMZ en écriture seule
	CHECK(pc_io_in(&f->pc, 0xF981, 2, &v) == 0);			// A8 = 1 : pas le CTC
	CHECK(pc_io_in(&f->pc, 0x1234, 2, &v) == 0);
	done(f);
}

static void ctc_timer_raises_int_and_ack_gives_vector(void)
{
	Fixture* f = make(0);
	pc_io_out(&f->pc, 0xF880, 0x20, 0);						// vecteur de base &20
	pc_io_out(&f->pc, 0xF882, 0x85, 0);						// timer 16, int
	pc_io_out(&f->pc, 0xF882, 100, 0);						// période 1600 cycles
	run(f, 0, 1500, 10);
	CHECK(f->int_level == 1);
	run(f, 1500, 1700, 10);
	CHECK(f->int_level == 0);								// INT demandée
	uint8_t v = 0;
	CHECK(pc_int_ack(&f->pc, 1700, &v) == 1);
	CHECK(v == 0x24);										// base | canal 2 << 1
	CHECK(f->int_level == 1);								// plus rien en attente : INT relâchée
	CHECK(pc_int_ack(&f->pc, 1700, &v) == 0);
	done(f);
}

static void nmi_from_cursor_on_channel_1(void)
{
	Fixture* f = make(0);
	pc_io_out(&f->pc, 0xF881, 0x45, 0);						// compteur, TC suit (sans interruption : NMI seule)
	pc_io_out(&f->pc, 0xF881, 2, 0);						// 2 impulsions CURSOR
	pc_cursor(&f->pc, 100);
	pc_tick(&f->pc, 200);
	CHECK(f->nmi_falls == 0);
	pc_cursor(&f->pc, 300);
	pc_tick(&f->pc, 400);
	CHECK(f->nmi_falls == 1);
	CHECK(f->nmi_level == 0);								// maintenue tant que le Z80 n'a pas pu la voir
	pc_tick(&f->pc, 500);
	CHECK(f->nmi_level == 1);								// puis relâchée
	CHECK(f->int_level == 1);								// pas d'IT : bit 7 non armé
	done(f);
}

static void soft_reset_port(void)
{
	Fixture* f = make(0);
	RIGHT(f, 8, 15, 0); RIGHT(f, 7, 0xFF, 0);
	pc_io_out(&f->pc, 0xF882, 0x85, 0);
	pc_io_out(&f->pc, 0xF882, 1, 0);
	run(f, 0, 100, 10);
	CHECK(f->int_level == 0);
	pc_io_out(&f->pc, 0xF8FF, 0, 100);						// reset
	CHECK(f->int_level == 1);
	CHECK(f->pc.ymz[0].reg[8] == 0);
	pc_tick(&f->pc, 5000);
	CHECK(f->int_level == 1);								// le timer ne tourne plus
	done(f);
}

static void audio_is_produced_at_the_emulated_rate(void)
{
	Fixture* f = make(0);
	run(f, 0, 4000000, 23);									// 1 s émulée
	CHECK(f->stream->pushed >= RATE - 2 && f->stream->pushed <= RATE + 2);
	done(f);
}

static void backward_time_does_not_flood_audio(void)
{
	Fixture* f = make(0);
	run(f, 0, 400000, 23);
	const uint64_t before = f->stream->pushed;
	pc_tick(&f->pc, 1000);									// retour en arrière (snapshot, reset)
	CHECK(f->stream->pushed == before);
	done(f);
}

int main(void)
{
	right_chip_is_right_channel();
	left_chip_and_swap_option();
	ymz_clock_follows_ctc_channel_0();
	ay_clock_matches_the_wiki_table();
	ctc_ports_are_readable_and_writable();
	ctc_timer_raises_int_and_ack_gives_vector();
	nmi_from_cursor_on_channel_1();
	soft_reset_port();
	audio_is_produced_at_the_emulated_rate();
	backward_time_does_not_flood_audio();
	return CHECK_DONE();
}
