#include "plugin_sdl_audio.h"
#include <string.h>

static void SDLCALL audio_cb(void* user, Uint8* stream, int len)
{
	GfSdlAudio* a = (GfSdlAudio*)user;
	a->render(a->user, (float*)stream, (uint32_t)len / (sizeof(float) * a->channels));
}

static void host_log(const CorePluginHost* h, uint32_t level, const char* msg)
{
	if (h && h->log)
		h->log(h->host_ctx, level, msg);
}

int32_t gf_sdl_audio_open(GfSdlAudio* a, uint32_t rate, uint32_t channels,
	GfAudioRenderFn render, void* user, const CorePluginHost* host)
{
	memset(a, 0, sizeof *a);
	a->channels = channels;
	a->render = render;
	a->user = user;
	if (!SDL_WasInit(SDL_INIT_AUDIO))
	{
		if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0)
		{
			host_log(host, 0, SDL_GetError());
			return CORE_PLUGIN_ERR_IO;
		}
		a->sdl_owned = 1;
	}
	SDL_AudioSpec want, have;
	SDL_zero(want);
	want.freq = (int)rate;
	want.format = AUDIO_F32SYS;
	want.channels = (Uint8)channels;
	want.samples = 512;
	want.callback = audio_cb;
	want.userdata = a;
	a->dev = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);		// 0 : SDL convertit vers `want` si besoin
	if (!a->dev)
	{
		host_log(host, 0, SDL_GetError());
		if (a->sdl_owned)
			SDL_QuitSubSystem(SDL_INIT_AUDIO);
		memset(a, 0, sizeof *a);
		return CORE_PLUGIN_ERR_IO;
	}
	SDL_PauseAudioDevice(a->dev, 0);
	return CORE_PLUGIN_OK;
}

void gf_sdl_audio_close(GfSdlAudio* a)
{
	if (a->dev)
		SDL_CloseAudioDevice(a->dev);
	if (a->sdl_owned)
		SDL_QuitSubSystem(SDL_INIT_AUDIO);
	memset(a, 0, sizeof *a);
}
