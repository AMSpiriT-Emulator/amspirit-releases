project('amspirit-plugin-common', 'c',
  version : '0.1.0',
  default_options : ['c_std=gnu11', 'warning_level=2', 'buildtype=release'])

# Tronc commun des plugins : paramètres, journal, flux audio. Aucune dépendance SDL ni core.
abi_inc = include_directories('include')

common_lib = static_library('plugin_common',
  ['plugin_params.c', 'plugin_clock.c', 'plugin_audio.c'],
  include_directories : abi_inc,
  pic : true)

plugin_common_dep = declare_dependency(
  link_with : common_lib,
  include_directories : [include_directories('.'), abi_inc])
meson.override_dependency('plugin-common', plugin_common_dep)

# Sortie audio SDL2 (optionnelle) : dépendance « plugin-sdl », non trouvée si SDL2 est absent.
sdl2 = dependency('sdl2', required : false)
plugin_sdl_dep = dependency('', required : false)
if sdl2.found()
  sdl_lib = static_library('plugin_sdl', 'sdl/plugin_sdl_audio.c',
    dependencies : [plugin_common_dep, sdl2], pic : true)
  plugin_sdl_dep = declare_dependency(link_with : sdl_lib,
    dependencies : [plugin_common_dep, sdl2], include_directories : include_directories('sdl'))
  meson.override_dependency('plugin-sdl', plugin_sdl_dep)
endif

m = meson.get_compiler('c').find_library('m', required : false)
foreach t : ['params', 'clock', 'audio']
  test(t, executable('test_' + t, 'tests/test_' + t + '.c',
    dependencies : [plugin_common_dep, m], include_directories : include_directories('tests')))
endforeach
