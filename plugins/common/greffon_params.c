#include "greffon_params.h"
#include <stdlib.h>
#include <string.h>

static int find(const GfParams* p, const char* key)
{
	for (uint32_t i = 0; i < p->count; ++i)
		if (strcmp(p->decl[i]->key, key) == 0)
			return (int)i;
	return -1;
}

static int parse_int(const char* s, int64_t* out)
{
	char* end = NULL;
	const long long v = strtoll(s, &end, 10);
	if (!s[0] || *end)
		return 0;
	*out = v;
	return 1;
}

static int valid(const CoreGreffonParam* d, const char* value)
{
	int64_t v;
	switch (d->type)
	{
	case CORE_GREFFON_PARAM_BOOL:
		return strcmp(value, "0") == 0 || strcmp(value, "1") == 0;
	case CORE_GREFFON_PARAM_INT:
		return parse_int(value, &v) && v >= d->int_min && v <= d->int_max;
	case CORE_GREFFON_PARAM_ENUM:
		for (uint32_t i = 0; i < d->choice_count; ++i)
			if (strcmp(d->choices[i], value) == 0)
				return 1;
		return 0;
	default:										// STRING, PATH : tout texte de taille raisonnable
		return 1;
	}
}

int32_t gf_params_init(GfParams* p, const CoreGreffonParam* const* decl, uint32_t count)
{
	if (!p || (count && !decl) || count > GF_PARAMS_MAX)
		return CORE_GREFFON_ERR_ARG;
	p->decl = decl;
	p->count = count;
	for (uint32_t i = 0; i < count; ++i)
	{
		const char* def = decl[i]->def ? decl[i]->def : "";
		if (strlen(def) >= GF_VALUE_MAX)
			return CORE_GREFFON_ERR_ARG;
		strcpy(p->value[i], def);
	}
	return CORE_GREFFON_OK;
}

static int32_t set(GfParams* p, const char* key, const char* value, int live, int check_apply)
{
	if (!p || !key || !value)
		return CORE_GREFFON_ERR_ARG;
	const int i = find(p, key);
	if (i < 0)
		return CORE_GREFFON_ERR_UNKNOWN_KEY;
	const CoreGreffonParam* d = p->decl[i];
	if (check_apply && live && d->apply != CORE_GREFFON_APPLY_LIVE)
		return CORE_GREFFON_ERR_STATE;
	if (strlen(value) >= GF_VALUE_MAX || !valid(d, value))
		return CORE_GREFFON_ERR_BAD_VALUE;
	strcpy(p->value[i], value);
	return CORE_GREFFON_OK;
}

int32_t gf_params_set(GfParams* p, const char* key, const char* value, int live)
{
	return set(p, key, value, live, 1);
}

int32_t gf_params_load_initial(GfParams* p, const CoreGreffonKV* kv, uint32_t count)
{
	for (uint32_t i = 0; i < count; ++i)
	{
		const int32_t rc = set(p, kv[i].key, kv[i].value, 0, 0);
		if (rc != CORE_GREFFON_OK && rc != CORE_GREFFON_ERR_UNKNOWN_KEY)
			return rc;
	}
	return CORE_GREFFON_OK;
}

int64_t gf_params_int(const GfParams* p, const char* key)
{
	const int i = find(p, key);
	int64_t v = 0;
	if (i >= 0)
		parse_int(p->value[i], &v);
	return v;
}

const char* gf_params_str(const GfParams* p, const char* key)
{
	const int i = find(p, key);
	return (i >= 0) ? p->value[i] : "";
}
