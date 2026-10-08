project('amspirit-digiblaster', 'c',
  version : '0.1.0',
  default_options : ['c_std=gnu11', 'warning_level=2', 'buildtype=release'])

# Entête d'ABI : copie de amspirit-core/amspirit-core/inc/public/Core_Greffon.h (voir ../README.md)
abi_inc = include_directories('../include')

dsp = static_library('digiblaster_dsp', 'digiblaster_dsp.c', c_args : ['-fPIC'])

sdl2 = dependency('sdl2')
ext = (host_machine.system() == 'windows') ? 'dll' : 'so'
shared_module('digiblaster', 'digiblaster.c',
  include_directories : abi_inc,
  link_with : dsp,
  dependencies : sdl2,
  name_prefix : '',
  name_suffix : ext,
  gnu_symbol_visibility : 'hidden')   # seuls les CORE_GREFFON_EXPORT sortent

test_dsp = executable('test_dsp', 'tests/test_dsp.c', link_with : dsp, dependencies : meson.get_compiler('c').find_library('m'))
test('dsp', test_dsp)
