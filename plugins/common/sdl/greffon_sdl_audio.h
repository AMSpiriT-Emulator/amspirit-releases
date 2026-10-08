// Sortie audio SDL2 d'un GfAudioStream. Seul fichier de la lib commune qui dépend de SDL : un greffon qui
// produit du son l'utilise ; les autres (et les tests) s'en passent.
#pragma once
#include "Core_Greffon.h"
#include "greffon_audio.h"
#include <SDL.h>

typedef struct GfSdlAudio
{
	SDL_AudioDeviceID	dev;
	int					sdl_owned;		// SDL_INIT_AUDIO initialisé par nous (à refermer)
} GfSdlAudio;

// Ouvre un périphérique en flottants (stream->channels, stream->rate) et démarre la lecture.
// Renvoie CORE_GREFFON_OK ou CORE_GREFFON_ERR_IO (message SDL transmis à host->log).
int32_t		gf_sdl_audio_open(GfSdlAudio* a, GfAudioStream* stream, const CoreGreffonHost* host);
// Ferme le périphérique : attend la fin du callback ; après, le flux n'est plus lu.
void		gf_sdl_audio_close(GfSdlAudio* a);
