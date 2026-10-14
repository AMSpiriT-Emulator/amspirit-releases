project('amspirit-playcity', 'c',
  version : '0.1.0',
  default_options : ['c_std=gnu11', 'warning_level=2', 'buildtype=release'])

# Tronc commun des plugins (../common) : paramètres, horloge d'échantillons, flux audio.
common = subproject('plugin-common').get_variable('plugin_common_dep')
m = meson.get_compiler('c').find_library('m', required : false)

chips = static_library('playcity_chips', ['ctc.c', 'ymz294.c', 'playcity_card.c'], dependencies : common, pic : true)
chips_dep = declare_dependency(link_with : chips, dependencies : common, include_directories : include_directories('.'))

foreach t : ['ctc', 'ymz294', 'card']
  test(t, executable('test_' + t, 'tests/test_' + t + '.c',
    dependencies : [chips_dep, common, m],
    include_directories : include_directories('../common/tests')))
endforeach

# Le plugin : module dynamique, son SDL2 (dépendance « plugin-sdl » du tronc commun)
sdl = subproject('plugin-common').get_variable('plugin_sdl_dep')
if sdl.found()
  ext = (host_machine.system() == 'windows') ? 'dll' : 'so'
  shared_module('playcity', 'playcity.c',
    dependencies : [chips_dep, common, sdl, m],
    name_prefix : '',
    name_suffix : ext,
    gnu_symbol_visibility : 'hidden')   # seuls les CORE_PLUGIN_EXPORT sortent
else
  warning('SDL2 introuvable : le plugin PlayCity n\'est pas construit (les tests le sont)')
endif
