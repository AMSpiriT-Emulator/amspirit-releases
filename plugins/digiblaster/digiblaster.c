// ============================================================================
// Greffon Digiblaster (AmspiriT) : CNA 8 bits sur le port imprimante, sortie audio SDL2 autonome.
//
//   - Connecteur : imprimante (CORE_GREFFON_CONN_PRINTER). Le bit 7 du port, la ligne strobe, sert de
//     8e bit du CNA : l'échantillon est l'octet brut, non signé, centré sur 128.
//   - Pas de ligne BUSY (callback absent = toujours prête), pas de lecture.
//   - Le son est produit ici : le core ne sait rien d'audio (ADR 0003). SDL2 ouvre son propre
//     périphérique ; seul printer_out (fil d'émulation) écrit dans la file, le fil audio SDL la lit.
//
// N'inclut que l'en-tête public de l'ABI.
// ============================================================================
#include "Core_Greffon.h"
#include "digiblaster_dsp.h"
#include <SDL.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

typedef struct DbStats				// Lisible par les tests via Digiblaster_Stats() (dlsym)
{
	uint64_t	events, produced, dropped, underruns, anchors;
	uint32_t	rate;
	uint8_t		last_value;
} DbStats;

typedef struct Digiblaster
{
	const CoreGreffonHost*	host;
	SDL_AudioDeviceID		dev;
	int						sdl_owned;		// SDL_INIT_AUDIO initialisé par nous
	DbDsp					dsp;			// gros (file) : alloué avec la structure
} Digiblaster;

static Digiblaster* s_inst;					// pour Digiblaster_Stats

static const char* const k_rates[] = { "44100", "48000" };
static const CoreGreffonParam p_volume = { sizeof(CoreGreffonParam), "volume", "Volume (%)", CORE_GREFFON_PARAM_INT,
	CORE_GREFFON_APPLY_LIVE, "80", 0, 100, NULL, 0, NULL };
static const CoreGreffonParam p_rate = { sizeof(CoreGreffonParam), "sample_rate", "Frequence d'echantillonnage (Hz)", CORE_GREFFON_PARAM_ENUM,
	CORE_GREFFON_APPLY_AT_ATTACH, "44100", 0, 0, k_rates, 2, NULL };
static const CoreGreffonParam p_latency = { sizeof(CoreGreffonParam), "latency_ms", "Latence audio (ms)", CORE_GREFFON_PARAM_INT,
	CORE_GREFFON_APPLY_AT_ATTACH, "60", 10, 500, NULL, 0, NULL };
static const CoreGreffonParam* const k_params[] = { &p_volume, &p_rate, &p_latency };

static const CoreGreffonDesc k_desc = { sizeof(CoreGreffonDesc), CORE_GREFFON_ABI_MAJOR, CORE_GREFFON_ABI_MINOR,
	"Digiblaster", "0.1.0", "CNA 8 bits sur le port imprimante (Digiblaster / Soundplayer), sortie SDL2",
	CORE_GREFFON_CONN_PRINTER, 0, NULL, 0, 0, k_params, 3 };

CORE_GREFFON_EXPORT const CoreGreffonDesc* CoreGreffon_Describe(void) { return &k_desc; }

static void host_log(const CoreGreffonHost* h, uint32_t level, const char* msg)
{
	if (h && h->log) h->log(h->host_ctx, level, msg);
}

static int parse_int(const char* s, long lo, long hi, long* out)
{
	char* end = NULL;
	const long v = strtol(s, &end, 10);
	if (!s[0] || *end || v < lo || v > hi) return 0;
	*out = v;
	return 1;
}

static void SDLCALL audio_cb(void* user, Uint8* stream, int len)
{
	Digiblaster* g = (Digiblaster*)user;
	db_render(&g->dsp, (float*)stream, (uint32_t)len / sizeof(float));
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
	if (g->dev) SDL_CloseAudioDevice(g->dev);		// attend la fin du callback : après, plus aucun accès à dsp
	if (g->sdl_owned) SDL_QuitSubSystem(SDL_INIT_AUDIO);
	if (s_inst == g) s_inst = NULL;
	free(g);
}

static int32_t cb_set_param(void* ctx, const char* key, const char* value)
{
	Digiblaster* g = (Digiblaster*)ctx;
	if (strcmp(key, "volume") == 0)
	{
		long v;
		if (!parse_int(value, 0, 100, &v)) return CORE_GREFFON_ERR_BAD_VALUE;
		atomic_store(&g->dsp.volume, (float)v / 100.0f);
		return CORE_GREFFON_OK;
	}
	return CORE_GREFFON_ERR_UNKNOWN_KEY;
}

// Seul l'état du CNA (dernier octet écrit) fait partie de la machine ; la file audio est éphémère.
static int32_t cb_save_state(void* ctx, uint8_t* buffer, uint32_t capacity, uint32_t* size_out)
{
	Digiblaster* g = (Digiblaster*)ctx;
	if (size_out) *size_out = 1;
	if (capacity < 1) return CORE_GREFFON_ERR_BUFFER;
	buffer[0] = g->dsp.value;
	return CORE_GREFFON_OK;
}

static int32_t cb_load_state(void* ctx, const uint8_t* buffer, uint32_t size)
{
	Digiblaster* g = (Digiblaster*)ctx;
	if (size != 1) return CORE_GREFFON_ERR_BAD_VALUE;
	g->dsp.value = buffer[0];
	return CORE_GREFFON_OK;
}

CORE_GREFFON_EXPORT int32_t CoreGreffon_Attach(const CoreGreffonHost* host, const CoreGreffonKV* initial,
	uint32_t initial_count, CoreGreffonCallbacks* callbacks, void** ctx)
{
	if (!host || !callbacks || !ctx) return CORE_GREFFON_ERR_ARG;
	if (host->abi_major != CORE_GREFFON_ABI_MAJOR) return CORE_GREFFON_ERR_ABI;

	long volume = 80, rate = 44100, latency = 60;
	for (uint32_t i = 0; i < initial_count; i++)
	{
		const char *k = initial[i].key, *v = initial[i].value;
		int ok = 1;
		if      (strcmp(k, "volume") == 0)		ok = parse_int(v, 0, 100, &volume);
		else if (strcmp(k, "sample_rate") == 0)	ok = parse_int(v, 1, 1000000, &rate) && (rate == 44100 || rate == 48000);
		else if (strcmp(k, "latency_ms") == 0)	ok = parse_int(v, 10, 500, &latency);
		if (!ok) return CORE_GREFFON_ERR_BAD_VALUE;
	}

	Digiblaster* g = (Digiblaster*)calloc(1, sizeof *g);
	if (!g) return CORE_GREFFON_ERR_IO;
	g->host = host;
	db_init(&g->dsp, (uint32_t)rate, (uint32_t)latency, (float)volume / 100.0f);

	if (!SDL_WasInit(SDL_INIT_AUDIO))
	{
		if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0)
		{
			host_log(host, 0, SDL_GetError());
			free(g);
			return CORE_GREFFON_ERR_IO;
		}
		g->sdl_owned = 1;
	}
	SDL_AudioSpec want, have;
	SDL_zero(want);
	want.freq = (int)rate;
	want.format = AUDIO_F32SYS;
	want.channels = 1;
	want.samples = 512;
	want.callback = audio_cb;
	want.userdata = g;
	g->dev = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);	// 0 : SDL convertit vers `want` si besoin
	if (!g->dev)
	{
		host_log(host, 0, SDL_GetError());
		if (g->sdl_owned) SDL_QuitSubSystem(SDL_INIT_AUDIO);
		free(g);
		return CORE_GREFFON_ERR_IO;
	}

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
	SDL_PauseAudioDevice(g->dev, 0);
	host_log(host, 2, "Digiblaster attachee");
	return CORE_GREFFON_OK;
}

CORE_GREFFON_EXPORT int32_t Digiblaster_Stats(DbStats* out)
{
	if (!out || !s_inst) return CORE_GREFFON_ERR_STATE;
	const DbDsp* d = &s_inst->dsp;
	out->events = d->events; out->produced = d->produced; out->dropped = d->dropped;
	out->underruns = d->underruns; out->anchors = d->anchors;
	out->rate = d->rate; out->last_value = d->value;
	return CORE_GREFFON_OK;
}
