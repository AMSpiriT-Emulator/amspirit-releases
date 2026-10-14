// ============================================================================
// Plugin Digiblaster (AmspiriT) : CNA 8 bits sur le port imprimante, sortie audio SDL2 autonome.
//
//   - Connecteur : imprimante (CORE_PLUGIN_CONN_PRINTER). Le bit 7 du port, la ligne strobe, sert de
//     8e bit du CNA : l'échantillon est l'octet brut, non signé, centré sur 128.
//   - Pas de ligne BUSY (callback absent = toujours prête), pas de lecture.
//   - Le son est produit ici : le core ne sait rien d'audio (ADR 0003). Les paramètres et la sortie SDL
//     viennent du tronc commun ; seul printer_out (fil d'émulation) écrit dans la file.
//
// N'inclut que l'en-tête public de l'ABI et le tronc commun.
// ============================================================================
#include "Core_Plugin.h"
#include "plugin_params.h"
#include "plugin_sdl_audio.h"
#include "digiblaster_dsp.h"
#include <stdlib.h>
#include <string.h>

typedef struct DbStats				// Lisible par les tests via Digiblaster_Stats() (dlsym)
{
	uint64_t	events, produced, dropped, underruns, anchors;
	uint32_t	rate;
	uint8_t		last_value;
} DbStats;

typedef struct Digiblaster
{
	const CorePluginHost*	host;
	GfParams				params;
	GfSdlAudio				sdl;
	DbDsp					dsp;			// gros (file) : alloué avec la structure
} Digiblaster;

static Digiblaster* s_inst;					// pour Digiblaster_Stats

static const char* const k_rates[] = { "44100", "48000" };
static const CorePluginParam p_volume = { sizeof(CorePluginParam), "volume", "Volume (%)", CORE_PLUGIN_PARAM_INT,
	CORE_PLUGIN_APPLY_LIVE, "80", 0, 100, NULL, 0, NULL };
static const CorePluginParam p_rate = { sizeof(CorePluginParam), "sample_rate", "Frequence d'echantillonnage (Hz)", CORE_PLUGIN_PARAM_ENUM,
	CORE_PLUGIN_APPLY_AT_ATTACH, "44100", 0, 0, k_rates, 2, NULL };
static const CorePluginParam p_latency = { sizeof(CorePluginParam), "latency_ms", "Latence audio (ms)", CORE_PLUGIN_PARAM_INT,
	CORE_PLUGIN_APPLY_AT_ATTACH, "60", 10, 500, NULL, 0, NULL };
static const CorePluginParam* const k_params[] = { &p_volume, &p_rate, &p_latency };

static const CorePluginDesc k_desc = { sizeof(CorePluginDesc), CORE_PLUGIN_ABI_MAJOR, CORE_PLUGIN_ABI_MINOR,
	"Digiblaster", "0.1.0", "CNA 8 bits sur le port imprimante (Digiblaster / Soundplayer), sortie SDL2",
	CORE_PLUGIN_CONN_PRINTER, 0, NULL, 0, 0, k_params, 3 };

CORE_PLUGIN_EXPORT const CorePluginDesc* CorePlugin_Describe(void) { return &k_desc; }

static void host_log(const CorePluginHost* h, uint32_t level, const char* msg)
{
	if (h && h->log) h->log(h->host_ctx, level, msg);
}

static void render_cb(void* user, float* out, uint32_t frames)
{
	db_render((DbDsp*)user, out, frames);
}

static void cb_printer_out(void* ctx, uint8_t data, uint64_t cycle)
{
	db_write(&((Digiblaster*)ctx)->dsp, cycle, data);
}

static void cb_reset(void* ctx, uint64_t cycle)
{
	db_anchor(&((Digiblaster*)ctx)->dsp, cycle, 0x80);
}

static void cb_detach(void* ctx)
{
	Digiblaster* g = (Digiblaster*)ctx;
	gf_sdl_audio_close(&g->sdl);					// attend la fin du callback : après, plus aucun accès à dsp
	if (s_inst == g) s_inst = NULL;
	free(g);
}

static int32_t cb_set_param(void* ctx, const char* key, const char* value)
{
	Digiblaster* g = (Digiblaster*)ctx;
	const int32_t rc = gf_params_set(&g->params, key, value, 1);
	if (rc == CORE_PLUGIN_OK && strcmp(key, "volume") == 0)
		atomic_store(&g->dsp.volume, (float)gf_params_int(&g->params, "volume") / 100.0f);
	return rc;
}

// Seul l'état du CNA (dernier octet écrit) fait partie de la machine ; la file audio est éphémère.
static int32_t cb_save_state(void* ctx, uint8_t* buffer, uint32_t capacity, uint32_t* size_out)
{
	Digiblaster* g = (Digiblaster*)ctx;
	if (size_out) *size_out = 1;
	if (capacity < 1) return CORE_PLUGIN_ERR_BUFFER;
	buffer[0] = g->dsp.value;
	return CORE_PLUGIN_OK;
}

static int32_t cb_load_state(void* ctx, const uint8_t* buffer, uint32_t size)
{
	Digiblaster* g = (Digiblaster*)ctx;
	if (size != 1) return CORE_PLUGIN_ERR_BAD_VALUE;
	g->dsp.value = buffer[0];
	return CORE_PLUGIN_OK;
}

CORE_PLUGIN_EXPORT int32_t CorePlugin_Attach(const CorePluginHost* host, const CorePluginKV* initial,
	uint32_t initial_count, CorePluginCallbacks* callbacks, void** ctx)
{
	if (!host || !callbacks || !ctx) return CORE_PLUGIN_ERR_ARG;
	if (host->abi_major != CORE_PLUGIN_ABI_MAJOR) return CORE_PLUGIN_ERR_ABI;

	Digiblaster* g = (Digiblaster*)calloc(1, sizeof *g);
	if (!g) return CORE_PLUGIN_ERR_IO;
	g->host = host;
	gf_params_init(&g->params, k_params, 3);
	int32_t rc = gf_params_load_initial(&g->params, initial, initial_count);
	if (rc != CORE_PLUGIN_OK) { free(g); return rc; }

	const uint32_t rate = (uint32_t)gf_params_int(&g->params, "sample_rate");
	db_init(&g->dsp, rate, (uint32_t)gf_params_int(&g->params, "latency_ms"),
		(float)gf_params_int(&g->params, "volume") / 100.0f);
	rc = gf_sdl_audio_open(&g->sdl, rate, 1, render_cb, &g->dsp, host);
	if (rc != CORE_PLUGIN_OK) { free(g); return rc; }

	memset(callbacks, 0, sizeof *callbacks);
	callbacks->size = sizeof *callbacks;
	callbacks->reset = cb_reset;
	callbacks->detach = cb_detach;
	callbacks->printer_out = cb_printer_out;			// printer_busy absent : jamais occupée
	callbacks->set_param = cb_set_param;
	callbacks->save_state = cb_save_state;
	callbacks->load_state = cb_load_state;
	*ctx = g;
	s_inst = g;
	host_log(host, 2, "Digiblaster attachee");
	return CORE_PLUGIN_OK;
}

CORE_PLUGIN_EXPORT int32_t Digiblaster_Stats(DbStats* out)
{
	if (!out || !s_inst) return CORE_PLUGIN_ERR_STATE;
	const DbDsp* d = &s_inst->dsp;
	out->events = d->events; out->produced = d->stream.pushed; out->dropped = d->stream.dropped;
	out->underruns = d->stream.underruns; out->anchors = d->anchors;
	out->rate = d->rate; out->last_value = d->value;
	return CORE_PLUGIN_OK;
}
