// Tests du DSP Digiblaster, sans SDL ni core.
#include "../digiblaster_dsp.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>

static int fails;
#define CHECK(c) do { if (!(c)) { printf("ECHEC l.%d : %s\n", __LINE__, #c); fails++; } } while (0)

// Avance par pas de 5 ms (< préremplissage) : un flux continu d'événements ne déclenche pas le réancrage
static void run_to(DbDsp* d, uint64_t from, uint64_t to, uint8_t v)
{
	for (uint64_t c = from; c < to; c += 20000) db_write(d, c, v);
	db_write(d, to, v);
}

static DbDsp* mk(uint32_t rate, uint32_t latency_ms)
{
	DbDsp* d = malloc(sizeof *d);
	db_init(d, rate, latency_ms, 1.0f);
	return d;
}

// Le nombre d'échantillons produits suit le temps émulé : 1 s de T-states = `rate` échantillons
static void test_cadence(void)
{
	DbDsp* d = mk(44100, 10);
	db_anchor(d, 0, 0x80);
	run_to(d, 0, 4000000, 0x80);
	CHECK(d->stream.pushed >= 44099 && d->stream.pushed <= 44100 + 1);
	free(d);
}

// Carré 1 kHz (période 4000 T-states) : l'énergie passe, ~1 kHz en sortie
static void test_square(void)
{
	DbDsp* d = mk(44100, 10);
	db_anchor(d, 0, 0x80);
	for (uint64_t c = 0; c < 400000; c += 2000)
		db_write(d, c, ((c / 2000) & 1) ? 0xFF : 0x00);
	db_write(d, 400000, 0x80);
	static float out[8192];
	db_render(d, out, 4096);
	float pk = 0; int crossings = 0;
	for (int i = 1000; i < 4000; i++) { if (fabsf(out[i]) > pk) pk = fabsf(out[i]); if ((out[i-1] < 0) != (out[i] < 0)) crossings++; }
	CHECK(pk > 0.5f);
	// 3000 échantillons = 68 ms -> ~68 périodes -> ~136 passages par zéro
	CHECK(crossings > 110 && crossings < 160);
	free(d);
}

// Un niveau continu s'éteint (couplage alternatif) au lieu de sortir un décalage permanent
static void test_dc_blocked(void)
{
	DbDsp* d = mk(44100, 10);
	db_anchor(d, 0, 0x00);
	db_write(d, 0, 0x00);
	db_write(d, 4000000, 0x00);
	static float out[44100];
	db_render(d, out, 44100);
	CHECK(fabsf(out[44099]) < 0.05f);
	free(d);
}

// Pas de lecture tant que le préremplissage n'est pas atteint ; ensuite lecture ; file vide => rebuffering
static void test_prefill_and_underrun(void)
{
	DbDsp* d = mk(44100, 100);							// 4410 échantillons
	db_anchor(d, 0, 0x80);
	db_write(d, 0, 0xFF);
	db_write(d, 400000, 0xFF);							// 100 ms = ~4410 échantillons
	static float out[256];
	db_render(d, out, 256);
	// juste assez ou presque : on tolère les deux, mais jamais de lecture sous le préremplissage
	DbDsp* e = mk(44100, 100);
	db_anchor(e, 0, 0x80);
	db_write(e, 0, 0xFF);
	db_write(e, 200000, 0xFF);							// 50 ms seulement
	db_render(e, out, 256);
	CHECK(atomic_load(&e->stream.rd) == 0);					// rien consommé
	CHECK(atomic_load(&e->stream.buffering) == 1);
	free(d); free(e);
}

// Un long silence quand le consommateur a tout lu ne s'ajoute pas à la latence
static void test_gap_reanchor(void)
{
	DbDsp* d = mk(44100, 20);
	db_anchor(d, 0, 0x80);
	db_write(d, 0, 0xC0);
	db_write(d, 100000, 0xC0);							// 25 ms : préremplissage atteint
	static float out[4096];
	db_render(d, out, 4096);							// tout consommé, rebuffering
	CHECK(atomic_load(&d->stream.buffering) == 1);
	const uint64_t before = d->stream.pushed;
	db_write(d, 100000 + 8000000, 0x40);				// 2 s plus tard
	CHECK(d->stream.pushed - before < 100);					// pas 88200 échantillons de remplissage
	CHECK(d->anchors >= 2);
	free(d);
}

// Temps qui revient en arrière (reset) : pas de boucle ni de production aberrante
static void test_time_backwards(void)
{
	DbDsp* d = mk(44100, 20);
	db_anchor(d, 0, 0x80);
	run_to(d, 0, 4000000, 0x10);
	const uint64_t p = d->stream.pushed;
	db_write(d, 1000, 0x20);
	CHECK(d->stream.pushed == p);
	db_write(d, 5000, 0x30);
	CHECK(d->stream.pushed - p >= 43 && d->stream.pushed - p <= 45);	// 4000 T-states depuis 1000 = ~44 echantillons
	free(d);
}

// File pleine : les échantillons sont jetés, jamais d'écrasement du non lu
static void test_overflow(void)
{
	DbDsp* d = mk(44100, 20);
	db_anchor(d, 0, 0x80);
	run_to(d, 0, 4000000ull * 5, 0x80);					// 5 s sans consommateur
	CHECK(d->stream.dropped > 0);
	CHECK(atomic_load(&d->stream.wr) - atomic_load(&d->stream.rd) <= GF_AUDIO_RING_FRAMES);
	free(d);
}

// Un son plus court que le préremplissage (clic de 40 ms, préremplissage 60 ms) est joué quand même,
// et le trou de 1 s qui suit n'ajoute pas de retard
static void test_short_burst(void)
{
	DbDsp* d = mk(44100, 60);
	db_anchor(d, 0, 0x80);
	run_to(d, 0, 0, 0x80);
	db_write(d, 0, 0xFF);
	run_to(d, 0, 160000, 0xFF);							// 40 ms
	db_write(d, 160000, 0x80);
	static float out[8192];
	db_render(d, out, 4096);							// ~93 ms réels : le préremplissage est dépassé
	CHECK(atomic_load(&d->stream.rd) > 0);						// la lecture a démarré
	db_render(d, out, 4096);							// le reste est lu, file vide
	CHECK(atomic_load(&d->stream.buffering) == 1);
	const uint64_t before = d->stream.pushed;
	db_write(d, 160000 + 4000000, 0xFF);				// 1 s plus tard
	CHECK(d->stream.pushed - before < 100);
	free(d);
}

// Turbo : la production va bien plus vite que le temps réel, la latence reste bornée
static void test_turbo_bounded(void)
{
	DbDsp* d = mk(44100, 60);
	db_anchor(d, 0, 0x80);
	run_to(d, 0, 4000000ull * 1, 0x80);					// 1 s émulée d'un coup
	static float out[512];
	db_render(d, out, 512);
	CHECK(atomic_load(&d->stream.wr) - atomic_load(&d->stream.rd) <= d->stream.maxfill);
	CHECK(d->stream.skipped > 0);
	free(d);
}

int main(void)
{
	test_cadence(); test_square(); test_dc_blocked(); test_prefill_and_underrun();
	test_gap_reanchor(); test_time_backwards(); test_overflow(); test_short_burst(); test_turbo_bounded();
	printf(fails ? "%d echec(s)\n" : "OK\n", fails);
	return fails != 0;
}
