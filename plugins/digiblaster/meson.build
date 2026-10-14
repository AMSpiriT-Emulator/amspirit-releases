project('amspirit-digiblaster', 'c',
  version : '0.1.0',
  default_options : ['c_std=gnu11', 'warning_level=2', 'buildtype=release'])

# Tronc commun (../common, via subprojects/plugin-common) : paramètres, flux audio, sortie SDL2.
# En-tête d'ABI : copie dans common/include (voir ../README.md).
common = subproject('plugin-common')
common_dep = common.get_variable('plugin_common_dep')
sdl_dep = common.get_variable('plugin_sdl_dep')
if not sdl_dep.found()
  error('SDL2 requis pour le plugin Digiblaster')
endif

# DSP (temps -> échantillons) : sans SDL ni core, testable seul
dsp = static_library('digiblaster_dsp', 'digiblaster_dsp.c', dependencies : common_dep, pic : true)
dsp_dep = declare_dependency(link_with : dsp, dependencies : common_dep,
  include_directories : include_directories('.'))

ext = (host_machine.system() == 'windows') ? 'dll' : 'so'
shared_module('digiblaster', 'digiblaster.c',
  dependencies : [dsp_dep, common_dep, sdl_dep],
  name_prefix : '',
  name_suffix : ext,
  gnu_symbol_visibility : 'hidden')   # seuls les CORE_PLUGIN_EXPORT sortent

m = meson.get_compiler('c').find_library('m', required : false)
test('dsp', executable('test_dsp', 'tests/test_dsp.c', dependencies : [dsp_dep, m]))
