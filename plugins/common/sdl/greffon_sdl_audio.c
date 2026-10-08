#include "greffon_sdl_audio.h"
#include <string.h>

static void SDLCALL audio_cb(void* user, Uint8* stream, int len)
{
	GfAudioStream* s = (GfAudioStream*)user;
	gf_audio_render(s, (float*)stream, (uint32_t)len / (sizeof(float) * s->channels));
}

static void host_log(const CoreGreffonHost* h, uint32_t level, const char* msg)
{
	if (h && h->log)
		h->log(h->host_ctx, level, msg);
}

int32_t gf_sdl_audio_open(GfSdlAudio* a, GfAudioStream* stream, const CoreGreffonHost* host)
{
	memset(a, 0, sizeof *a);
	if (!SDL_WasInit(SDL_INIT_AUDIO))
	{
		if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0)
		{
			host_log(host, 0, SDL_GetError());
			return CORE_GREFFON_ERR_IO;
		}
		a->sdl_owned = 1;
	}
	SDL_AudioSpec want, have;
	SDL_zero(want);
	want.freq = (int)stream->rate;
	want.format = AUDIO_F32SYS;
	want.channels = (Uint8)stream->channels;
	want.samples = 512;
	want.callback = audio_cb;
	want.userdata = stream;
	a->dev = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);		// 0 : SDL convertit vers `want` si besoin
	if (!a->dev)
	{
		host_log(host, 0, SDL_GetError());
		if (a->sdl_owned)
			SDL_QuitSubSystem(SDL_INIT_AUDIO);
		memset(a, 0, sizeof *a);
		return CORE_GREFFON_ERR_IO;
	}
	SDL_PauseAudioDevice(a->dev, 0);
	return CORE_GREFFON_OK;
}

void gf_sdl_audio_close(GfSdlAudio* a)
{
	if (a->dev)
		SDL_CloseAudioDevice(a->dev);
	if (a->sdl_owned)
		SDL_QuitSubSystem(SDL_INIT_AUDIO);
	memset(a, 0, sizeof *a);
}
