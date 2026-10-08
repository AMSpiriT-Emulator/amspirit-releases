// Paramètres déclaratifs d'un greffon : défauts, validation par type, lecture typée.
// Tronc commun des greffons AmspiriT. Aucune dépendance autre que l'en-tête d'ABI.
#pragma once
#include "Core_Greffon.h"

#define GF_PARAMS_MAX		32
#define GF_VALUE_MAX		256

typedef struct GfParams
{
	const CoreGreffonParam* const*	decl;
	uint32_t						count;
	char							value[GF_PARAMS_MAX][GF_VALUE_MAX];
} GfParams;

// Prend les valeurs par défaut des déclarations. CORE_GREFFON_ERR_ARG si > GF_PARAMS_MAX.
int32_t		gf_params_init(GfParams* p, const CoreGreffonParam* const* decl, uint32_t count);

// Valide `value` pour `key` (type, bornes, choix) puis la mémorise. `live` = 1 pour un changement à
// chaud (set_param) : un paramètre APPLY_AT_ATTACH est alors refusé (CORE_GREFFON_ERR_STATE).
// ERR_UNKNOWN_KEY, ERR_BAD_VALUE, ou CORE_GREFFON_OK. Rien n'est modifié en cas d'erreur.
int32_t		gf_params_set(GfParams* p, const char* key, const char* value, int live);

// Valeurs initiales passées à CoreGreffon_Attach : clé inconnue ignorée, valeur invalide refusée.
int32_t		gf_params_load_initial(GfParams* p, const CoreGreffonKV* kv, uint32_t count);

// Lecture typée (clé déclarée obligatoire ; clé inconnue -> 0 / "")
int64_t		gf_params_int(const GfParams* p, const char* key);		// INT, BOOL
const char*	gf_params_str(const GfParams* p, const char* key);		// ENUM, STRING, PATH
