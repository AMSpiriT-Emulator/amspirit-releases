#include "ctc.h"
#include "check.h"

// Mots de contrôle (bits : 7 int, 6 compteur, 5 prédiv. 256, 4 front, 3 déclenchement CLK/TRG, 2 TC suit, 1 reset, 0 =1)
#define TIMER16_INT		0x85		// timer, prédiviseur 16, démarrage auto, interruption, TC suit
#define TIMER256_INT	0xA5		// idem, prédiviseur 256
#define TIMER16_NOINT	0x05
#define COUNTER_INT		0xC5		// compteur, interruption, TC suit
#define COUNTER_NOINT	0x45

static void start(Ctc* c, unsigned ch, uint8_t ctrl, uint8_t tc)
{
	ctc_write(c, ch, ctrl);
	ctc_write(c, ch, tc);
}

static void timer_period_includes_two_cycle_start_delay(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 2, TIMER16_INT, 3);				// période = 16 * 3 = 48 cycles Phi, démarrage au 2e front
	ctc_advance(&c, 49, 0);
	CHECK(ctc_take_zc(&c, 2) == 0);
	CHECK(ctc_int_pending(&c) == 0);
	ctc_advance(&c, 1, 0);						// 50 cycles : première échéance
	CHECK(ctc_int_pending(&c) == (1u << 2));
	CHECK(ctc_take_zc(&c, 2) == 1);
}

static void timer_is_periodic(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 2, TIMER16_NOINT, 3);
	ctc_advance(&c, 2 + 48 * 5 + 10, 0);		// 5 périodes complètes + 10 cycles
	CHECK(ctc_take_zc(&c, 2) == 5);
	CHECK(ctc_take_zc(&c, 2) == 0);				// repris
	CHECK(ctc_int_pending(&c) == 0);			// interruption non autorisée : jamais de demande
}

static void prescaler_256_and_tc_zero_means_256(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 2, TIMER256_INT, 0);				// TC 0 = 256 : 256 * 256 = 65536 cycles
	ctc_advance(&c, 2 + 65535, 0);
	CHECK(ctc_take_zc(&c, 2) == 0);
	ctc_advance(&c, 1, 0);
	CHECK(ctc_take_zc(&c, 2) == 1);
}

static void split_advances_give_same_result(void)
{
	Ctc a, b; ctc_reset(&a); ctc_reset(&b);
	start(&a, 2, TIMER16_INT, 7); start(&b, 2, TIMER16_INT, 7);
	ctc_advance(&a, 1000, 0);
	for (int i = 0; i < 1000; ++i) ctc_advance(&b, 1, 0);
	CHECK(ctc_take_zc(&a, 2) == ctc_take_zc(&b, 2));
	CHECK(ctc_read(&a, 2) == ctc_read(&b, 2));
}

static void read_returns_down_counter(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 2, TIMER16_NOINT, 10);
	ctc_advance(&c, 2, 0);						// démarrage effectif : le compteur est chargé
	CHECK(ctc_read(&c, 2) == 10);
	ctc_advance(&c, 16 * 3, 0);					// trois pas du compteur
	CHECK(ctc_read(&c, 2) == 7);
}

static void counter_mode_counts_trg_events(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 1, COUNTER_INT, 3);				// canal 1 : CURSOR
	ctc_advance(&c, 5000, 2);
	CHECK(ctc_take_zc(&c, 1) == 0);
	ctc_advance(&c, 10, 1);						// 3e impulsion
	CHECK(ctc_take_zc(&c, 1) == 1);
	CHECK(ctc_int_pending(&c) == (1u << 1));
	ctc_advance(&c, 10, 7);						// 7 impulsions : 2 échéances (3 + 3) et 1 en cours
	CHECK(ctc_take_zc(&c, 1) == 2);
	CHECK(ctc_read(&c, 1) == 2);
}

static void channel0_counter_on_phi_clock(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 0, COUNTER_NOINT, 4);				// TRG0 = 4 MHz : une échéance tous les 4 cycles
	ctc_advance(&c, 40, 0);
	CHECK(ctc_take_zc(&c, 0) == 10);
	CHECK(ctc_ch0_period(&c) == 4);
}

static void channel3_is_triggered_by_zc2(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 2, TIMER16_NOINT, 1);				// ZC2 tous les 16 cycles
	start(&c, 3, COUNTER_INT, 4);				// ZC3 tous les 4 ZC2 = 64 cycles
	ctc_advance(&c, 2 + 64 * 3, 0);
	CHECK(ctc_take_zc(&c, 3) == 3);
	CHECK(ctc_int_pending(&c) & (1u << 3));
}

static void interrupt_vector_and_priority(void)
{
	Ctc c; ctc_reset(&c);
	ctc_write(&c, 0, 0x28);						// mot de vecteur (bit 0 = 0) : base &28
	start(&c, 3, COUNTER_INT, 1);
	start(&c, 1, COUNTER_INT, 1);
	ctc_advance(&c, 10, 1);						// CURSOR -> canal 1 ; canal 3 : jamais déclenché ici
	uint8_t v = 0;
	CHECK(ctc_ack(&c, &v) == 1);
	CHECK(v == 0x28 + 2);						// base | (canal 1 << 1)
	CHECK(ctc_int_pending(&c) == 0);
	CHECK(ctc_ack(&c, &v) == 0);				// plus rien

	ctc_reti(&c);								// RETI : le canal 1 n'est plus en service

	// canaux 0 et 2 demandent en même temps : le plus prioritaire d'abord
	start(&c, 0, COUNTER_INT, 1);
	start(&c, 2, COUNTER_INT, 1);
	ctc_advance(&c, 3, 0);
	CHECK(ctc_ack(&c, &v) == 1); CHECK(v == 0x28);
	CHECK(ctc_ack(&c, &v) == 1); CHECK(v == 0x28 + 4);	// la demande du canal 2, déjà retenue, reste servable
}

static void in_service_blocks_lower_priority_but_not_higher(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 1, COUNTER_INT, 1);
	start(&c, 2, COUNTER_INT, 1);
	start(&c, 0, COUNTER_INT, 1);
	uint8_t v;
	ctc_advance(&c, 1, 1);						// 0, 1 et 2 échoient ensemble
	CHECK(ctc_ack(&c, &v) == 1); CHECK(v == 0);			// canal 0 servi ; 1 et 2 restent demandées
	CHECK(ctc_int_pending(&c) == ((1u << 1) | (1u << 2)));
	ctc_advance(&c, 1, 1);						// canal 0 en service : sa propre impulsion est perdue
	CHECK((ctc_int_pending(&c) & 1u) == 0);
	CHECK(ctc_ack(&c, &v) == 1); CHECK(v == 2);			// le canal 1 est déjà demandé : servi (imbriqué)
}

static void vector_word_only_on_channel_0(void)
{
	Ctc c; ctc_reset(&c);
	ctc_write(&c, 1, 0x40);						// bit 0 = 0 sur le canal 1 : pas un vecteur
	ctc_write(&c, 0, 0x10);
	start(&c, 0, COUNTER_INT, 1);
	ctc_advance(&c, 1, 0);
	uint8_t v = 0xFF;
	CHECK(ctc_ack(&c, &v) == 1);
	CHECK(v == 0x10);
}

static void software_reset_stops_the_channel(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 2, TIMER16_NOINT, 1);
	ctc_advance(&c, 100, 0);
	ctc_take_zc(&c, 2);
	ctc_write(&c, 2, 0x03);						// reset logiciel (bits 1 et 0)
	ctc_advance(&c, 1000, 0);
	CHECK(ctc_take_zc(&c, 2) == 0);
}

static void hardware_reset_clears_everything(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 0, COUNTER_INT, 1);
	ctc_advance(&c, 4, 0);
	CHECK(ctc_int_pending(&c) != 0);
	ctc_reset(&c);
	CHECK(ctc_int_pending(&c) == 0);
	ctc_advance(&c, 1000, 5);
	CHECK(ctc_take_zc(&c, 0) == 0);
	CHECK(ctc_ch0_period(&c) == 0);
}

static void trigger_mode_waits_for_clk_trg(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 1, 0x8D, 2);						// timer, prédiv. 16, déclenchement par CLK/TRG (bit 3), int
	ctc_advance(&c, 1000, 0);
	CHECK(ctc_take_zc(&c, 1) == 0);				// attend l'impulsion CURSOR
	ctc_advance(&c, 2 + 32, 1);
	CHECK(ctc_take_zc(&c, 1) == 1);
}

static void new_tc_without_reset_applies_at_next_reload(void)
{
	Ctc c; ctc_reset(&c);
	start(&c, 2, TIMER16_NOINT, 2);				// période 32
	ctc_advance(&c, 2 + 10, 0);
	ctc_write(&c, 2, TIMER16_NOINT);			// TC suit, sans reset
	ctc_write(&c, 2, 4);						// nouvelle période 64 dès le prochain rechargement
	ctc_advance(&c, 22, 0);						// fin de la période en cours (32)
	CHECK(ctc_take_zc(&c, 2) == 1);
	ctc_advance(&c, 63, 0);
	CHECK(ctc_take_zc(&c, 2) == 0);
	ctc_advance(&c, 1, 0);
	CHECK(ctc_take_zc(&c, 2) == 1);
}

int main(void)
{
	timer_period_includes_two_cycle_start_delay();
	timer_is_periodic();
	prescaler_256_and_tc_zero_means_256();
	split_advances_give_same_result();
	read_returns_down_counter();
	counter_mode_counts_trg_events();
	channel0_counter_on_phi_clock();
	channel3_is_triggered_by_zc2();
	interrupt_vector_and_priority();
	in_service_blocks_lower_priority_but_not_higher();
	vector_word_only_on_channel_0();
	software_reset_stops_the_channel();
	hardware_reset_clears_everything();
	trigger_mode_waits_for_clk_trg();
	new_tc_without_reset_applies_at_next_reload();
	return CHECK_DONE();
}
