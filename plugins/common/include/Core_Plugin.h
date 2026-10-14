/////////////////////////////////////////////////////////////////////////////////
// Amstrad CPC emulator - plugin ABI (dynamically loaded hardware extensions)  //
//                                                                             //
// See docs/adr/0002-*.md, docs/adr/0003-*.md and docs/extensions.md.          //
/////////////////////////////////////////////////////////////////////////////////
#pragma once

// =============================================================================
//  Vocabulary (see CONTEXT.md)
//    Extension : the emulated peripheral (PicoGX, Digiblaster, M4 Board...).
//    Connector : the place it plugs into (expansion connector, cartridge slot,
//                printer port, joystick port).
//    Plugin    : the dynamic library (.so/.dll/.dylib) that emulates it.
//
//  ABI rules
//    - Pure C: this file only depends on <stdint.h> and <stddef.h>. A plugin
//      includes nothing else from the core. No wchar_t, no C++ type, no
//      exception crossing the boundary. Strings are UTF-8.
//    - Every structure starts with `size` (sizeof on the sender's side): the
//      receiver only reads a field covered by `size`, which allows appending
//      fields at the end of a structure without breaking the ABI.
//    - OPAQUE: the plugin never receives a pointer to the core's state. It sees
//      the Z80 lines and the connectors, and nothing of the internal state of
//      the CRTC, the Gate Array or the ASIC (ADR 0003).
//    - Every call (core -> plugin and plugin -> host) happens on the emulation
//      thread. A plugin that creates its own threads never calls the host
//      from them.
//    - Time: Z80 T-states (4 MHz), 64 bits, since the machine's reset.
// =============================================================================

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CORE_PLUGIN_ABI_MAJOR		1		// Incompatible: the core refuses a plugin whose major differs
#define CORE_PLUGIN_ABI_MINOR		2		// Compatible: added fields/capabilities

// Names of the entry points a plugin exports (resolved with dlsym/GetProcAddress)
#define CORE_PLUGIN_SYM_DESCRIBE	"CorePlugin_Describe"
#define CORE_PLUGIN_SYM_ATTACH		"CorePlugin_Attach"

#if defined(_WIN32)
  #define CORE_PLUGIN_EXPORT		__declspec(dllexport)
#elif defined(__GNUC__) || defined(__clang__)
  #define CORE_PLUGIN_EXPORT		__attribute__ ((visibility ("default")))
#else
  #define CORE_PLUGIN_EXPORT
#endif

// -----------------------------------------------------------------------------
//  Return codes (0 = success, negative = error)
// -----------------------------------------------------------------------------
#define CORE_PLUGIN_OK					0
#define CORE_PLUGIN_ERR_ARG			(-1)	// Invalid argument
#define CORE_PLUGIN_ERR_ABI			(-2)	// Incompatible major ABI / structure too short
#define CORE_PLUGIN_ERR_CONFLICT		(-3)	// Port already decoded by an internal chip or another plugin
#define CORE_PLUGIN_ERR_UNKNOWN_KEY	(-4)	// Unknown parameter
#define CORE_PLUGIN_ERR_BAD_VALUE		(-5)	// Parameter value refused
#define CORE_PLUGIN_ERR_NOT_FOUND		(-6)	// File / plugin / identifier not found
#define CORE_PLUGIN_ERR_IO				(-7)	// I/O error
#define CORE_PLUGIN_ERR_STATE			(-8)	// Call in an invalid state (already attached, not attached...)
#define CORE_PLUGIN_ERR_UNSUPPORTED	(-9)	// Capability missing on the host or plugin side
#define CORE_PLUGIN_ERR_BUFFER			(-10)	// Buffer too small (the required size is returned)

// -----------------------------------------------------------------------------
//  Connectors requested by a plugin (CorePluginDesc.connectors)
// -----------------------------------------------------------------------------
// Expansion connector: only ports whose lines A15..A11 are all 1 (&F8xx-&FFxx) can be claimed,
// outside the FDC decoding (A10 = 0 and A7 = 0). A range that touches a port decoded by an
// internal chip, or already claimed by another plugin in the same direction, makes the attach
// fail (CORE_PLUGIN_ERR_CONFLICT).
#define CORE_PLUGIN_CONN_EXPANSION		0x00000001u	// I/O ports of the expansion connector (io_ranges)
// Cartridge: Plus/GX4000 range only; on a classic CPC the attach is accepted but no event ever
// arrives (the client may change model after the attach). v1.0 only observes the LOWER ROM
// window (physical bank selected by RMR2, at &0000/&4000/&8000), not the upper ROM.
// `cart_banks_mask` must not be zero.
#define CORE_PLUGIN_CONN_CARTRIDGE		0x00000002u	// Observation of the cartridge window (cart_banks_mask)
// Printer: one plugin at a time (CORE_PLUGIN_ERR_CONFLICT otherwise). printer_out receives every OUT
// with A12 = 0 (&EFxx); the BUSY line (bit 6 of PPI port B) is the one from printer_busy, re-read on
// every read while the plugin is attached (callback absent = always ready); on detach, the original
// behaviour (client parameter PRINTER_CONNECTED) is restored.
#define CORE_PLUGIN_CONN_PRINTER		0x00000004u	// Printer port (output; busy as input)
#define CORE_PLUGIN_CONN_JOYSTICK0		0x00000008u	// Joystick port 0 (input)
#define CORE_PLUGIN_CONN_JOYSTICK1		0x00000010u	// Joystick port 1 (input)
// CRTC CURSOR signal (an expansion connector pin, ABI 1.2): `cursor` is called on every rising edge,
// at the exact cycle. Nothing else of the CRTC is exposed. The signal follows the 6845 definition:
// address MA = R14/R15, raster line between R10 (start) and R11 (end), blinking from R10 bits 6-5,
// and only during display (DISPTMG). Plus range: CRTC 3/4 provides the same signal.
#define CORE_PLUGIN_CONN_CURSOR		0x00000020u

// Z80 lines a plugin can drive (CorePluginHost.set_line)
// INT and WAIT are wired-OR with the Gate Array (and between plugins): a line is low as long as at
// least one of them holds it LOW; the level is kept until the plugin releases it (the Gate Array
// acknowledges the interrupt as it does its own). Detach releases everything.
// NB: NMI and BUSRQ are written directly into the Z80 (no OR between plugins: the last one to
// release wins). A plugin's IM 2 vector goes through the int_ack callback (ABI 1.1); without it, or
// if it returns 0, the acknowledge cycle presents &FF.
#define CORE_PLUGIN_LINE_WAIT			1
#define CORE_PLUGIN_LINE_INT			2
#define CORE_PLUGIN_LINE_NMI			3
#define CORE_PLUGIN_LINE_BUSRQ			4
// Levels: 0 = LOW (active, the Z80 signals are active-low), 1 = HIGH (inactive)

// Directions of a port range
#define CORE_PLUGIN_DIR_IN				0x1u
#define CORE_PLUGIN_DIR_OUT			0x2u

// Bits returned by joystick_in (1 = line pulled / direction active)
#define CORE_PLUGIN_JOY_UP				0x01u
#define CORE_PLUGIN_JOY_DOWN			0x02u
#define CORE_PLUGIN_JOY_LEFT			0x04u
#define CORE_PLUGIN_JOY_RIGHT			0x08u
#define CORE_PLUGIN_JOY_FIRE2			0x10u
#define CORE_PLUGIN_JOY_FIRE1			0x20u

// -----------------------------------------------------------------------------
//  Host capabilities (CorePluginHost.capabilities)
//  An optional host function is only called if its capability is announced.
//  This is how the ABI will later open up to possible targeted values
//  (docs/extensions.md) without changing the existing structures.
// -----------------------------------------------------------------------------
#define CORE_PLUGIN_CAP_FILES			0x00000001u	// file_read / file_write / file_list provided by the client
#define CORE_PLUGIN_CAP_CART_OVERRIDE	0x00000002u	// override_cart_bank / remap_now

// -----------------------------------------------------------------------------
//  Declarative parameters
//  The plugin describes its parameters; the client persists them and can generate a form
//  (GUI) or a prompt (CLI) by itself. Values are exchanged as UTF-8:
//    BOOL "0"/"1" - INT decimal - ENUM one of the choices - STRING - PATH client path
// -----------------------------------------------------------------------------
#define CORE_PLUGIN_PARAM_BOOL			1
#define CORE_PLUGIN_PARAM_INT			2
#define CORE_PLUGIN_PARAM_ENUM			3
#define CORE_PLUGIN_PARAM_STRING		4
#define CORE_PLUGIN_PARAM_PATH			5		// File or directory, chosen/resolved by the client

#define CORE_PLUGIN_APPLY_AT_ATTACH	0		// Only taken into account at attach time
#define CORE_PLUGIN_APPLY_LIVE			1		// Can be changed live (set_param callback)

typedef struct CorePluginParam
{
	uint32_t			size;			// sizeof(CorePluginParam)
	const char*			key;			// Stable identifier, e.g. "printer_file" (ASCII, no space)
	const char*			label;			// Display label (UTF-8)
	uint32_t			type;			// CORE_PLUGIN_PARAM_*
	uint32_t			apply;			// CORE_PLUGIN_APPLY_*
	const char*			def;			// Default value (text, depending on the type)
	int64_t				int_min;		// INT: bounds (inclusive)
	int64_t				int_max;
	const char* const*	choices;		// ENUM: array of choices (values and labels are identical)
	uint32_t			choice_count;
	const char*			path_filter;	// PATH: indicative extension filter, e.g. "*.rom;*.cro" (NULL = none)
} CorePluginParam;

typedef struct CorePluginKV			// Parameter value passed at attach time
{
	const char*			key;
	const char*			value;
} CorePluginKV;

// -----------------------------------------------------------------------------
//  Description of a plugin (returned by CorePlugin_Describe)
// -----------------------------------------------------------------------------
typedef struct CorePluginIORange		// The plugin answers if (port & mask) == value
{
	uint16_t			mask;
	uint16_t			value;
	uint32_t			dir;			// CORE_PLUGIN_DIR_IN | CORE_PLUGIN_DIR_OUT
} CorePluginIORange;

typedef struct CorePluginDesc
{
	uint32_t				size;				// sizeof(CorePluginDesc)
	uint32_t				abi_major;			// CORE_PLUGIN_ABI_MAJOR the plugin was built with
	uint32_t				abi_minor;
	const char*				name;				// "PicoGX"
	const char*				version;			// "0.1.0" (the plugin's version)
	const char*				description;		// One line
	uint32_t				connectors;			// CORE_PLUGIN_CONN_*
	uint32_t				required_caps;		// CORE_PLUGIN_CAP_* it cannot work without
	const CorePluginIORange*	io_ranges;		// CONN_EXPANSION: port ranges claimed
	uint32_t				io_range_count;
	uint32_t				cart_banks_mask;	// CONN_CARTRIDGE: PHYSICAL cartridge banks observed (bit n = bank n)
	const CorePluginParam* const*	params;		// Array of pointers: adding fields to CorePluginParam breaks nothing
	uint32_t				param_count;
} CorePluginDesc;

// -----------------------------------------------------------------------------
//  Host: what the core offers the plugin (provided to CorePlugin_Attach)
//  First argument of every function: `host_ctx`, to be passed back unchanged.
// -----------------------------------------------------------------------------
typedef struct CorePluginHost
{
	uint32_t			size;				// sizeof(CorePluginHost)
	uint32_t			abi_major;
	uint32_t			abi_minor;
	uint32_t			capabilities;		// CORE_PLUGIN_CAP_* actually provided
	uint32_t			clock_hz;			// Frequency of the time unit (4000000)
	void*				host_ctx;

	// Current emulated time (4 MHz T-states since reset)
	uint64_t			(*now)(void* host_ctx);

	// Drives a Z80 line (CORE_PLUGIN_LINE_*), level 0 = LOW / 1 = HIGH
	void				(*set_line)(void* host_ctx, uint32_t line, uint32_t level);

	// Provides an expansion ROM (logical ROM `rom_number`, 0..255, 16 KB). The bytes
	// are copied. A ROM already in place (client load) is not overwritten: returns
	// CORE_PLUGIN_ERR_STATE. On detach, the ROMs provided by the plugin are unloaded.
	int32_t				(*provide_rom)(void* host_ctx, uint32_t rom_number, const uint8_t* data, uint32_t size);

	// Log: level 0 = error, 1 = warning, 2 = info, 3 = trace
	void				(*log)(void* host_ctx, uint32_t level, const char* message);

	// --- CAP_CART_OVERRIDE ---------------------------------------------------
	// Replaces the PHYSICAL cartridge bank `bank` (0..31) with `data16k` (16384 bytes,
	// COPIED: the buffer need not stay valid; NULL = restores the original bank, which
	// detach also does). A bank has only one owning plugin at a time (ERR_STATE). Affects SUBSEQUENT
	// reads only (ADR 0002): the core never replaces the byte of a read in progress.
	int32_t				(*override_cart_bank)(void* host_ctx, uint32_t bank, const uint8_t* data16k);
	// Applies the mapping change right away ("the switch is instant").
	void				(*remap_now)(void* host_ctx);

	// --- CAP_FILES: files resolved by the client (the core touches no file) ---
	// Names are opaque (paths relative to the plugin, or PATH parameter values).
	// Synchronous and potentially slow calls: avoid them in a hot callback.
	int32_t				(*file_read)(void* host_ctx, const char* name, uint8_t* buffer, uint32_t capacity, uint32_t* size_out);
	int32_t				(*file_write)(void* host_ctx, const char* name, const uint8_t* data, uint32_t size);
	int32_t				(*file_list)(void* host_ctx, const char* directory,
										void (*emit)(void* emit_user, const char* name, uint32_t is_directory), void* emit_user);
} CorePluginHost;

// -----------------------------------------------------------------------------
//  Callbacks: what the plugin offers the core (filled in by CorePlugin_Attach)
//  Any NULL pointer = event not wanted. `ctx` is the plugin's context.
// -----------------------------------------------------------------------------
typedef struct CorePluginCallbacks
{
	uint32_t			size;				// sizeof(CorePluginCallbacks)

	void				(*reset)(void* ctx, uint64_t cycle);	// Machine reset (the plugin stays attached)
	void				(*detach)(void* ctx);					// Last call: free ctx

	// --- CONN_EXPANSION ---
	// Read of a claimed port. Returns 1 and writes *data if the plugin answers, 0 otherwise (free bus).
	int32_t				(*io_in)(void* ctx, uint16_t port, uint64_t cycle, uint8_t* data);
	void				(*io_out)(void* ctx, uint16_t port, uint8_t data, uint64_t cycle);

	// --- CONN_CARTRIDGE: OBSERVATION ONLY ---
	// Read in an observed bank. `cart_addr` = (physical bank << 14) | offset (19 bits).
	// `is_fetch` = 1 for an opcode fetch (M1), 0 for a data read. Returns void:
	// the byte read cannot be changed (ADR 0002). To change the mapping, call
	// override_cart_bank / remap_now on the host.
	void				(*cart_read)(void* ctx, uint32_t cart_addr, uint32_t is_fetch, uint64_t cycle);

	// --- CONN_PRINTER ---
	// Raw byte written to the printer port; bit 7 is the strobe line.
	void				(*printer_out)(void* ctx, uint8_t data, uint64_t cycle);
	// Printer busy line: 1 = busy. NULL = never busy.
	int32_t				(*printer_busy)(void* ctx, uint64_t cycle);

	// --- CONN_JOYSTICK0 / CONN_JOYSTICK1 ---
	// State of port `port` (0 or 1): a combination of CORE_PLUGIN_JOY_*; the core merges it with
	// the keyboard's / other sources' state. `cycle` lets a plugin date pulses (mouse).
	uint32_t			(*joystick_in)(void* ctx, uint32_t port, uint64_t cycle);

	// --- Parameters ---
	// Live change of a parameter declared CORE_PLUGIN_APPLY_LIVE. Returns CORE_PLUGIN_*.
	int32_t				(*set_param)(void* ctx, const char* key, const char* value);

	// --- State for snapshots (opaque buffer stored by the client, outside the core's SNA format) ---
	// If `capacity` is too small: returns CORE_PLUGIN_ERR_BUFFER, the required size in *size_out.
	int32_t				(*save_state)(void* ctx, uint8_t* buffer, uint32_t capacity, uint32_t* size_out);
	int32_t				(*load_state)(void* ctx, const uint8_t* buffer, uint32_t size);

	// --- Interrupts and time (ABI 1.1) ---
	// Interrupt acknowledge (M1 + IORQ cycle) while THIS plugin holds the INT line LOW. Returns 1
	// and writes *vector if the plugin answers (the byte presented to the Z80, e.g. the Z84C30 CTC's
	// IM 2 vector): it then has priority (IEI/IEO daisy chain) and the Gate Array is NOT acknowledged,
	// its interrupt stays pending. Returns 0: original acknowledge (&FF, Gate Array acknowledged). The
	// plugin may release INT from this callback. When several plugins hold INT, the first (attach order)
	// that answers wins.
	int32_t				(*int_ack)(void* ctx, uint64_t cycle, uint8_t* vector);
	// Emulated time: called after every Z80 instruction while the plugin is attached (lets it raise
	// INT at the right cycle without bus access, e.g. the CTC's timers). NULL = not wanted, at no cost.
	void				(*tick)(void* ctx, uint64_t cycle);

	// --- CONN_CURSOR (ABI 1.2) ---
	// Rising edge of the CRTC CURSOR signal at cycle `cycle` (T-states since reset, 1 µs resolution).
	void				(*cursor)(void* ctx, uint64_t cycle);
} CorePluginCallbacks;

// -----------------------------------------------------------------------------
//  Entry points a plugin must export
// -----------------------------------------------------------------------------

// Describes the plugin. Called once at load time, before any attach; the returned pointer
// stays valid as long as the library is loaded. Depends on no state.
//   CORE_PLUGIN_EXPORT const CorePluginDesc* CorePlugin_Describe(void);
typedef const CorePluginDesc* (*CorePlugin_Describe_Fn)(void);

// Attaches the plugin. `initial` = parameter values persisted by the client (may be
// empty: the plugin then takes its defaults). The plugin fills in `*callbacks` (with
// `callbacks->size`) and `*ctx`. A failure leaves the plugin unattached.
//   CORE_PLUGIN_EXPORT int32_t CorePlugin_Attach(const CorePluginHost* host,
//          const CorePluginKV* initial, uint32_t initial_count,
//          CorePluginCallbacks* callbacks, void** ctx);
typedef int32_t (*CorePlugin_Attach_Fn)(const CorePluginHost* host,
		const CorePluginKV* initial, uint32_t initial_count,
		CorePluginCallbacks* callbacks, void** ctx);

// -----------------------------------------------------------------------------
//  Client API (implemented by the core, called by the client)
//  The client manages the plugins: the core scans no directory and opens no file.
//  Not available on WASM. Declared only if AMSPIRIT_CORE_API is defined (include
//  Core_Amspirit.h first): a plugin does not need it.
//  v1.0: CONN_EXPANSION, CONN_CARTRIDGE and CONN_PRINTER are wired; the INT/WAIT/NMI/BUSRQ lines
//  can be driven; the joystick makes Attach answer ERR_UNSUPPORTED. Calls come from the emulation
//  thread (or with emulation stopped).
//  Life cycle: Load (dlopen + Describe) -> Attach -> [Set_Param, Save/Load_State] ->
//  Detach -> Unload.
// -----------------------------------------------------------------------------
#ifdef AMSPIRIT_CORE_API

typedef struct CorePluginFileOps		// Provided by the client (enables CORE_PLUGIN_CAP_FILES)
{
	uint32_t			size;			// sizeof(CorePluginFileOps)
	void*				user;
	int32_t				(*read)(void* user, const char* name, uint8_t* buffer, uint32_t capacity, uint32_t* size_out);
	int32_t				(*write)(void* user, const char* name, const uint8_t* data, uint32_t size);
	int32_t				(*list)(void* user, const char* directory,
									void (*emit)(void* emit_user, const char* name, uint32_t is_directory), void* emit_user);
} CorePluginFileOps;

// Optional: receiver of the plugins' log (level: 0 error .. 3 trace). Without it, the log is lost.
AMSPIRIT_CORE_API void		Core_Plugin_Set_Log(void (*log)(void* user, uint32_t level, const char* message), void* user);

// Optional: without it, the CAP_FILES capability is absent.
AMSPIRIT_CORE_API int32_t	Core_Plugin_Set_File_Ops(const CorePluginFileOps* ops);

// Loads the library and reads its description (no effect on the machine). `*id` identifies the plugin.
AMSPIRIT_CORE_API int32_t	Core_Plugin_Load(const char* library_path, uint32_t* id);
AMSPIRIT_CORE_API int32_t	Core_Plugin_Get_Desc(uint32_t id, const CorePluginDesc** desc);

// Plugs the extension in (CORE_PLUGIN_ERR_CONFLICT if a claimed port is already decoded).
AMSPIRIT_CORE_API int32_t	Core_Plugin_Attach(uint32_t id, const CorePluginKV* params, uint32_t count);
AMSPIRIT_CORE_API int32_t	Core_Plugin_Detach(uint32_t id);
AMSPIRIT_CORE_API int32_t	Core_Plugin_Unload(uint32_t id);

// Live parameter (APPLY_LIVE); otherwise CORE_PLUGIN_ERR_STATE.
AMSPIRIT_CORE_API int32_t	Core_Plugin_Set_Param(uint32_t id, const char* key, const char* value);

// State for snapshots (stored by the client, next to the SNA)
AMSPIRIT_CORE_API int32_t	Core_Plugin_Save_State(uint32_t id, uint8_t* buffer, uint32_t capacity, uint32_t* size_out);
AMSPIRIT_CORE_API int32_t	Core_Plugin_Load_State(uint32_t id, const uint8_t* buffer, uint32_t size);

#endif // AMSPIRIT_CORE_API

#ifdef __cplusplus
}
#endif
