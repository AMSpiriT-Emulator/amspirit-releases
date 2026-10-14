// ============================================================================
// Plugin PlayCity (AmspiriT) : Z84C30 (CTC) + 2 x YMZ294 sur le connecteur d'extension, son SDL2.
//
//   - Connecteur : extension. &F880-&F88F / &F980-&F98F (CTC, YMZ) et &F8FF (reset), cf. playcity_card.h.
//   - Lignes : INT (CTC, vecteur IM 2 via int_ack), NMI (canal 1, dont l'entrée est le signal CURSOR du CRTC).
//   - Le temps vient de tick() : le CTC et les timbres avancent à chaque instruction du Z80.
//   - Le son est produit ici (le core ne sait rien d'audio, ADR 0003) ; SDL2 ouvre son propre périphérique.
//
// N'inclut que l'en-tête public de l'ABI et le tronc commun des plugins.
// ============================================================================
#include "Core_Plugin.h"
#include "plugin_params.h"
#include "plugin_sdl_audio.h"
#include "playcity_card.h"
#include <stdlib.h>
#include <string.h>

typedef struct PcStats					// Lisible par les tests via PlayCity_Stats() (dlsym)
{
	uint64_t	pushed, dropped, underruns, int_acks;
	uint32_t	rate, int_level, nmi_level;
	uint32_t	ay_hz;
} PcStats;

typedef struct Plugin
{
	const CorePluginHost*	host;
	GfParams				params;
	GfSdlAudio				sdl;
	uint64_t				int_acks;
	PlayCity				pc;
	GfAudioStream			stream;		// gros (file) : alloué avec la structure
} Plugin;

static Plugin* s_inst;					// pour PlayCity_Stats

static const char* const k_rates[] = { "44100", "48000" };
static const CorePluginParam p_volume = { sizeof(CorePluginParam), "volume", "Volume (%)", CORE_PLUGIN_PARAM_INT,
	CORE_PLUGIN_APPLY_LIVE, "80", 0, 100, NULL, 0, NULL };
static const CorePluginParam p_rate = { sizeof(CorePluginParam), "sample_rate", "Frequence d'echantillonnage (Hz)", CORE_PLUGIN_PARAM_ENUM,
	CORE_PLUGIN_APPLY_AT_ATTACH, "44100", 0, 0, k_rates, 2, NULL };
static const CorePluginParam p_latency = { sizeof(CorePluginParam), "latency_ms", "Latence audio (ms)", CORE_PLUGIN_PARAM_INT,
	CORE_PLUGIN_APPLY_AT_ATTACH, "60", 10, 500, NULL, 0, NULL };
static const CorePluginParam p_swap = { sizeof(CorePluginParam), "swap_channels", "Inverser gauche/droite", CORE_PLUGIN_PARAM_BOOL,
	CORE_PLUGIN_APPLY_AT_ATTACH, "0", 0, 1, NULL, 0, NULL };
static const CorePluginParam* const k_params[] = { &p_volume, &p_rate, &p_latency, &p_swap };

// &F880-&F88F et &F980-&F98F : CTC et YMZ (le décodage fin est dans pc_io_*) ; &F8FF : reset
static const CorePluginIORange k_io[] = {
	{ 0xFEF0, 0xF880, CORE_PLUGIN_DIR_IN | CORE_PLUGIN_DIR_OUT },
	{ 0xFFFF, 0xF8FF, CORE_PLUGIN_DIR_OUT },
};

static const CorePluginDesc k_desc = { sizeof(CorePluginDesc), CORE_PLUGIN_ABI_MAJOR, CORE_PLUGIN_ABI_MINOR,
	"PlayCity", "0.1.0", "Z84C30 (CTC) + 2 x YMZ294 : 6 voix stereo, interruptions IM 2 / NMI, sortie SDL2",
	CORE_PLUGIN_CONN_EXPANSION | CORE_PLUGIN_CONN_CURSOR, 0, k_io, 2, 0, k_params, 4 };

CORE_PLUGIN_EXPORT const CorePluginDesc* CorePlugin_Describe(void) { return &k_desc; }

static void line_int(void* user, int level)
{
	const Plugin* g = (const Plugin*)user;
	g->host->set_line(g->host->host_ctx, CORE_PLUGIN_LINE_INT, (uint32_t)level);
}

static void line_nmi(void* user, int level)
{
	const Plugin* g = (const Plugin*)user;
	g->host->set_line(g->host->host_ctx, CORE_PLUGIN_LINE_NMI, (uint32_t)level);
}

static int32_t cb_io_in(void* ctx, uint16_t port, uint64_t cycle, uint8_t* data)
{
	return pc_io_in(&((Plugin*)ctx)->pc, port, cycle, data);
}

static void cb_io_out(void* ctx, uint16_t port, uint8_t data, uint64_t cycle)
{
	pc_io_out(&((Plugin*)ctx)->pc, port, data, cycle);
}

static int32_t cb_int_ack(void* ctx, uint64_t cycle, uint8_t* vector)
{
	Plugin* g = (Plugin*)ctx;
	const int r = pc_int_ack(&g->pc, cycle, vector);
	g->int_acks += (uint64_t)(r != 0);
	return r;
}

static void cb_cursor(void* ctx, uint64_t cycle) { pc_cursor(&((Plugin*)ctx)->pc, cycle); }

static void cb_tick(void* ctx, uint64_t cycle) { pc_tick(&((Plugin*)ctx)->pc, cycle); }

static void cb_reset(void* ctx, uint64_t cycle) { pc_reset(&((Plugin*)ctx)->pc, cycle); }

static void render_stream(void* user, float* out, uint32_t frames)
{
	gf_audio_render((GfAudioStream*)user, out, frames);
}

static void cb_detach(void* ctx)
{
	Plugin* g = (Plugin*)ctx;
	gf_sdl_audio_close(&g->sdl);			// attend la fin du callback : après, plus aucun accès au flux
	if (s_inst == g) s_inst = NULL;
	free(g);
}

static int32_t cb_set_param(void* ctx, const char* key, const char* value)
{
	Plugin* g = (Plugin*)ctx;
	const int32_t rc = gf_params_set(&g->params, key, value, 1);
	if (rc == CORE_PLUGIN_OK && strcmp(key, "volume") == 0)
		atomic_store(&g->stream.volume, (float)gf_params_int(&g->params, "volume") / 100.0f);
	return rc;
}

// État : la carte entière (CTC, registres YMZ, noms de ports) ; la file audio est éphémère.
#define STATE_VERSION	1u
typedef struct SavedState { uint32_t version; Ctc ctc; Ymz ymz[2]; } SavedState;

static int32_t cb_save_state(void* ctx, uint8_t* buffer, uint32_t capacity, uint32_t* size_out)
{
	const Plugin* g = (const Plugin*)ctx;
	if (size_out) *size_out = sizeof(SavedState);
	if (capacity < sizeof(SavedState)) return CORE_PLUGIN_ERR_BUFFER;
	SavedState st;
	memset(&st, 0, sizeof st);
	st.version = STATE_VERSION;
	st.ctc = g->pc.ctc;
	st.ymz[0] = g->pc.ymz[0];
	st.ymz[1] = g->pc.ymz[1];
	memcpy(buffer, &st, sizeof st);
	return CORE_PLUGIN_OK;
}

static int32_t cb_load_state(void* ctx, const uint8_t* buffer, uint32_t size)
{
	Plugin* g = (Plugin*)ctx;
	SavedState st;
	if (size != sizeof st) return CORE_PLUGIN_ERR_BAD_VALUE;
	memcpy(&st, buffer, sizeof st);
	if (st.version != STATE_VERSION) return CORE_PLUGIN_ERR_BAD_VALUE;
	g->pc.ctc = st.ctc;
	g->pc.ymz[0] = st.ymz[0];
	g->pc.ymz[1] = st.ymz[1];
	g->pc.ymz[0].tick_left = g->pc.ymz[1].tick_left = 0.0;
	return CORE_PLUGIN_OK;
}

CORE_PLUGIN_EXPORT int32_t CorePlugin_Attach(const CorePluginHost* host, const CorePluginKV* initial,
	uint32_t initial_count, CorePluginCallbacks* callbacks, void** ctx)
{
	if (!host || !callbacks || !ctx) return CORE_PLUGIN_ERR_ARG;
	if (host->abi_major != CORE_PLUGIN_ABI_MAJOR) return CORE_PLUGIN_ERR_ABI;
	if (host->abi_minor < 2 || !host->set_line) return CORE_PLUGIN_ERR_ABI;		// int_ack / tick : ABI 1.1, cursor : 1.2

	Plugin* g = (Plugin*)calloc(1, sizeof *g);
	if (!g) return CORE_PLUGIN_ERR_IO;
	g->host = host;
	gf_params_init(&g->params, k_params, 4);
	int32_t rc = gf_params_load_initial(&g->params, initial, initial_count);
	if (rc != CORE_PLUGIN_OK) { free(g); return rc; }

	gf_audio_init(&g->stream, (uint32_t)gf_params_int(&g->params, "sample_rate"), 2,
		(uint32_t)gf_params_int(&g->params, "latency_ms"), (float)gf_params_int(&g->params, "volume") / 100.0f);
	const PcLines lines = { g, line_int, line_nmi };
	pc_init(&g->pc, &g->stream, &lines, (int)gf_params_int(&g->params, "swap_channels"));
	pc_reset(&g->pc, host->now(host->host_ctx));

	rc = gf_sdl_audio_open(&g->sdl, g->stream.rate, 2, render_stream, &g->stream, host);
	if (rc != CORE_PLUGIN_OK) { free(g); return rc; }

	memset(callbacks, 0, sizeof *callbacks);
	callbacks->size = sizeof *callbacks;
	callbacks->reset = cb_reset;
	callbacks->detach = cb_detach;
	callbacks->io_in = cb_io_in;
	callbacks->io_out = cb_io_out;
	callbacks->int_ack = cb_int_ack;
	callbacks->tick = cb_tick;
	callbacks->cursor = cb_cursor;
	callbacks->set_param = cb_set_param;
	callbacks->save_state = cb_save_state;
	callbacks->load_state = cb_load_state;
	*ctx = g;
	s_inst = g;
	if (host->log) host->log(host->host_ctx, 2, "PlayCity attachee");
	return CORE_PLUGIN_OK;
}

CORE_PLUGIN_EXPORT int32_t PlayCity_Stats(PcStats* out)
{
	if (!out || !s_inst) return CORE_PLUGIN_ERR_STATE;
	out->pushed = s_inst->stream.pushed; out->dropped = s_inst->stream.dropped;
	out->underruns = s_inst->stream.underruns; out->int_acks = s_inst->int_acks;
	out->rate = s_inst->stream.rate;
	out->int_level = (uint32_t)s_inst->pc.int_level; out->nmi_level = (uint32_t)s_inst->pc.nmi_level;
	out->ay_hz = (uint32_t)pc_ay_hz(&s_inst->pc);
	return CORE_PLUGIN_OK;
}
