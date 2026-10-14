// Sortie audio SDL2 : ouvre un périphérique et appelle `render` sur le fil audio pour chaque bloc.
// Seul fichier de la lib commune qui dépend de SDL : un plugin qui produit du son l'utilise ; les autres
// (et les tests) s'en passent. `render` est le producteur côté consommateur : un flux du tronc commun
// (gf_audio_render) ou un plugin qui ajoute son propre traitement (filtre, volume).
#pragma once
#include "Core_Plugin.h"
#include <stdint.h>
#include <SDL.h>

typedef void (*GfAudioRenderFn)(void* user, float* out, uint32_t frames);

typedef struct GfSdlAudio
{
	SDL_AudioDeviceID	dev;
	int					sdl_owned;		// SDL_INIT_AUDIO initialisé par nous (à refermer)
	uint32_t			channels;
	GfAudioRenderFn		render;
	void*				user;
} GfSdlAudio;

// Ouvre un périphérique en flottants (`channels`, `rate`) et démarre la lecture.
// Renvoie CORE_PLUGIN_OK ou CORE_PLUGIN_ERR_IO (message SDL transmis à host->log).
int32_t		gf_sdl_audio_open(GfSdlAudio* a, uint32_t rate, uint32_t channels,
				GfAudioRenderFn render, void* user, const CorePluginHost* host);
// Ferme le périphérique : attend la fin du callback ; après, `render` n'est plus appelé.
void		gf_sdl_audio_close(GfSdlAudio* a);
