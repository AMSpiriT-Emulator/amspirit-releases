#include "plugin_params.h"
#include "check.h"
#include <string.h>

static const char* const k_modes[] = { "stereo", "mono" };
static const CorePluginParam p_vol  = { sizeof(CorePluginParam), "volume", "Volume", CORE_PLUGIN_PARAM_INT, CORE_PLUGIN_APPLY_LIVE, "80", 0, 100, NULL, 0, NULL };
static const CorePluginParam p_mode = { sizeof(CorePluginParam), "mode", "Mode", CORE_PLUGIN_PARAM_ENUM, CORE_PLUGIN_APPLY_AT_ATTACH, "stereo", 0, 0, k_modes, 2, NULL };
static const CorePluginParam p_on   = { sizeof(CorePluginParam), "active", "Actif", CORE_PLUGIN_PARAM_BOOL, CORE_PLUGIN_APPLY_LIVE, "1", 0, 0, NULL, 0, NULL };
static const CorePluginParam p_file = { sizeof(CorePluginParam), "rom", "ROM", CORE_PLUGIN_PARAM_PATH, CORE_PLUGIN_APPLY_AT_ATTACH, "", 0, 0, NULL, 0, "*.rom" };
static const CorePluginParam* const k_decl[] = { &p_vol, &p_mode, &p_on, &p_file };

static void defaults(void)
{
	GfParams p;
	CHECK(gf_params_init(&p, k_decl, 4) == CORE_PLUGIN_OK);
	CHECK(gf_params_int(&p, "volume") == 80);
	CHECK(strcmp(gf_params_str(&p, "mode"), "stereo") == 0);
	CHECK(gf_params_int(&p, "active") == 1);
	CHECK(strcmp(gf_params_str(&p, "rom"), "") == 0);
}

static void set_validates_by_type(void)
{
	GfParams p;
	gf_params_init(&p, k_decl, 4);
	CHECK(gf_params_set(&p, "volume", "55", 1) == CORE_PLUGIN_OK);
	CHECK(gf_params_int(&p, "volume") == 55);
	CHECK(gf_params_set(&p, "volume", "101", 1) == CORE_PLUGIN_ERR_BAD_VALUE);	// hors bornes
	CHECK(gf_params_set(&p, "volume", "-1", 1) == CORE_PLUGIN_ERR_BAD_VALUE);
	CHECK(gf_params_set(&p, "volume", "12abc", 1) == CORE_PLUGIN_ERR_BAD_VALUE);	// pas un entier
	CHECK(gf_params_set(&p, "volume", "", 1) == CORE_PLUGIN_ERR_BAD_VALUE);
	CHECK(gf_params_int(&p, "volume") == 55);										// inchangé après erreur
	CHECK(gf_params_set(&p, "active", "0", 1) == CORE_PLUGIN_OK);
	CHECK(gf_params_set(&p, "active", "2", 1) == CORE_PLUGIN_ERR_BAD_VALUE);
	CHECK(gf_params_set(&p, "nope", "1", 1) == CORE_PLUGIN_ERR_UNKNOWN_KEY);
	CHECK(gf_params_set(&p, "mode", "mono", 0) == CORE_PLUGIN_OK);
	CHECK(gf_params_set(&p, "mode", "quad", 0) == CORE_PLUGIN_ERR_BAD_VALUE);		// pas dans les choix
	CHECK(gf_params_set(&p, "rom", "/tmp/x.rom", 0) == CORE_PLUGIN_OK);
	CHECK(strcmp(gf_params_str(&p, "rom"), "/tmp/x.rom") == 0);
}

static void live_change_refused_for_attach_only_params(void)
{
	GfParams p;
	gf_params_init(&p, k_decl, 4);
	CHECK(gf_params_set(&p, "mode", "mono", 1) == CORE_PLUGIN_ERR_STATE);
	CHECK(strcmp(gf_params_str(&p, "mode"), "stereo") == 0);
}

static void initial_values(void)
{
	GfParams p;
	gf_params_init(&p, k_decl, 4);
	const CorePluginKV kv[] = { { "volume", "30" }, { "inconnue", "x" }, { "mode", "mono" } };
	CHECK(gf_params_load_initial(&p, kv, 3) == CORE_PLUGIN_OK);					// clé inconnue ignorée
	CHECK(gf_params_int(&p, "volume") == 30);
	CHECK(strcmp(gf_params_str(&p, "mode"), "mono") == 0);						// AT_ATTACH accepté à l'attache

	const CorePluginKV bad[] = { { "volume", "300" } };
	CHECK(gf_params_load_initial(&p, bad, 1) == CORE_PLUGIN_ERR_BAD_VALUE);
}

static void value_too_long_is_refused(void)
{
	GfParams p;
	gf_params_init(&p, k_decl, 4);
	char big[GF_VALUE_MAX + 10];
	memset(big, 'a', sizeof big - 1);
	big[sizeof big - 1] = 0;
	CHECK(gf_params_set(&p, "rom", big, 0) == CORE_PLUGIN_ERR_BAD_VALUE);
}

int main(void)
{
	defaults();
	set_validates_by_type();
	live_change_refused_for_attach_only_params();
	initial_values();
	value_too_long_is_refused();
	return CHECK_DONE();
}
