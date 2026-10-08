project('amspirit-greffon-common', 'c',
  version : '0.1.0',
  default_options : ['c_std=gnu11', 'warning_level=2', 'buildtype=release'])

# Tronc commun des greffons : paramètres, journal, flux audio. Aucune dépendance SDL ni core.
abi_inc = include_directories('include')

common_lib = static_library('greffon_common',
  ['greffon_params.c', 'greffon_clock.c', 'greffon_audio.c'],
  include_directories : abi_inc,
  pic : true)

greffon_common_dep = declare_dependency(
  link_with : common_lib,
  include_directories : [include_directories('.'), abi_inc])
meson.override_dependency('greffon-common', greffon_common_dep)

# Sortie audio SDL2 (optionnelle) : dépendance « greffon-sdl », non trouvée si SDL2 est absent.
sdl2 = dependency('sdl2', required : false)
greffon_sdl_dep = dependency('', required : false)
if sdl2.found()
  sdl_lib = static_library('greffon_sdl', 'sdl/greffon_sdl_audio.c',
    dependencies : [greffon_common_dep, sdl2], pic : true)
  greffon_sdl_dep = declare_dependency(link_with : sdl_lib,
    dependencies : [greffon_common_dep, sdl2], include_directories : include_directories('sdl'))
  meson.override_dependency('greffon-sdl', greffon_sdl_dep)
endif

m = meson.get_compiler('c').find_library('m', required : false)
foreach t : ['params', 'clock', 'audio']
  test(t, executable('test_' + t, 'tests/test_' + t + '.c',
    dependencies : [greffon_common_dep, m], include_directories : include_directories('tests')))
endforeach
