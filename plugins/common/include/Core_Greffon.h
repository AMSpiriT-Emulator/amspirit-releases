/////////////////////////////////////////////////////////////////////////////////
// Emulateur Amstrad CPC - ABI des greffons (extensions chargées dynamiquement) //
//                                                                             //
// BROUILLON v1.0 - voir docs/adr/0002-*.md, docs/adr/0003-*.md et             //
// docs/extensions.md. Rien ici n'est encore implémenté côté core.             //
/////////////////////////////////////////////////////////////////////////////////
#pragma once

// =============================================================================
//  Vocabulaire (cf. CONTEXT.md)
//    Extension  : le périphérique émulé (PicoGX, Digiblaster, M4 Board...).
//    Connecteur : l'endroit où elle se branche (connecteur d'extension, cartouche,
//                 port imprimante, port joystick).
//    Greffon    : la bibliothèque dynamique (.so/.dll/.dylib) qui l'émule.
//
//  Règles de l'ABI
//    - C pur : ce fichier ne dépend que de <stdint.h> et <stddef.h>. Un greffon
//      n'inclut rien d'autre du core. Pas de wchar_t, pas de type C++, pas
//      d'exception qui traverse la frontière. Chaînes en UTF-8.
//    - Toute structure commence par `size` (sizeof côté émetteur) : le récepteur
//      ne lit un champ que s'il est couvert par `size`, ce qui permet d'ajouter
//      des champs en fin de structure sans casser l'ABI.
//    - OPAQUE : le greffon ne reçoit jamais de pointeur vers l'état du core. Il
//      voit les lignes du Z80 et les connecteurs, et rien de l'état interne du
//      CRTC, du Gate Array ou de l'ASIC (ADR 0003).
//    - Tous les appels (core -> greffon et greffon -> hôte) ont lieu sur le fil
//      d'émulation. Un greffon qui crée ses propres fils n'appelle jamais l'hôte
//      depuis ceux-ci.
//    - Temps : T-states du Z80 (4 MHz), 64 bits, depuis le reset de la machine.
// =============================================================================

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CORE_GREFFON_ABI_MAJOR		1		// Incompatible : le core refuse le greffon si différent
#define CORE_GREFFON_ABI_MINOR		1		// Compatible : ajouts de champs/capacités

// Noms des points d'entrée exportés par un greffon (résolus par dlsym/GetProcAddress)
#define CORE_GREFFON_SYM_DESCRIBE	"CoreGreffon_Describe"
#define CORE_GREFFON_SYM_ATTACH		"CoreGreffon_Attach"

#if defined(_WIN32)
  #define CORE_GREFFON_EXPORT		__declspec(dllexport)
#elif defined(__GNUC__) || defined(__clang__)
  #define CORE_GREFFON_EXPORT		__attribute__ ((visibility ("default")))
#else
  #define CORE_GREFFON_EXPORT
#endif

// -----------------------------------------------------------------------------
//  Codes de retour (0 = succès, négatif = erreur)
// -----------------------------------------------------------------------------
#define CORE_GREFFON_OK					0
#define CORE_GREFFON_ERR_ARG			(-1)	// Argument invalide
#define CORE_GREFFON_ERR_ABI			(-2)	// ABI majeure incompatible / structure trop courte
#define CORE_GREFFON_ERR_CONFLICT		(-3)	// Port déjà décodé par une puce interne ou un autre greffon
#define CORE_GREFFON_ERR_UNKNOWN_KEY	(-4)	// Paramètre inconnu
#define CORE_GREFFON_ERR_BAD_VALUE		(-5)	// Valeur de paramètre refusée
#define CORE_GREFFON_ERR_NOT_FOUND		(-6)	// Fichier / greffon / identifiant introuvable
#define CORE_GREFFON_ERR_IO				(-7)	// Erreur d'entrée/sortie
#define CORE_GREFFON_ERR_STATE			(-8)	// Appel dans un état invalide (déjà attaché, non attaché...)
#define CORE_GREFFON_ERR_UNSUPPORTED	(-9)	// Capacité absente côté hôte ou greffon
#define CORE_GREFFON_ERR_BUFFER			(-10)	// Tampon trop petit (la taille nécessaire est renvoyée)

// -----------------------------------------------------------------------------
//  Connecteurs demandés par un greffon (CoreGreffonDesc.connectors)
// -----------------------------------------------------------------------------
// Connecteur d'extension : seuls les ports dont les lignes A15..A11 sont toutes à 1 (&F8xx-&FFxx)
// peuvent être réclamés, hors décodage du FDC (A10 = 0 et A7 = 0). Une plage qui touche un port
// décodé par une puce interne, ou déjà réclamé par un autre greffon dans le même sens, fait
// refuser l'attache (CORE_GREFFON_ERR_CONFLICT).
#define CORE_GREFFON_CONN_EXPANSION		0x00000001u	// Ports I/O du connecteur d'extension (io_ranges)
// Cartouche : gamme Plus/GX4000 seulement ; sur un CPC classique l'attache est acceptée mais aucun
// événement n'arrive (le client peut changer de modèle après l'attache). v1.0 n'observe que la
// fenêtre ROM BASSE (banque physique choisie par RMR2, en &0000/&4000/&8000), pas la ROM haute.
// `cart_banks_mask` ne doit pas être nul.
#define CORE_GREFFON_CONN_CARTRIDGE		0x00000002u	// Observation de la fenêtre cartouche (cart_banks_mask)
// Imprimante : un seul greffon à la fois (CORE_GREFFON_ERR_CONFLICT sinon). printer_out reçoit tout OUT
// dont A12 = 0 (&EFxx) ; la ligne BUSY (bit 6 du port B du PPI) est celle de printer_busy, relue à chaque
// lecture, tant que le greffon est attaché (callback absent = toujours prête) ; au detach, le comportement
// d'origine (paramètre client PRINTER_CONNECTED) est rétabli.
#define CORE_GREFFON_CONN_PRINTER		0x00000004u	// Port imprimante (sortie ; busy en entrée)
#define CORE_GREFFON_CONN_JOYSTICK0		0x00000008u	// Port joystick 0 (entrée)
#define CORE_GREFFON_CONN_JOYSTICK1		0x00000010u	// Port joystick 1 (entrée)

// Lignes du Z80 qu'un greffon peut piloter (CoreGreffonHost.set_line)
// INT et WAIT sont câblées en OU avec le Gate Array (et entre greffons) : une ligne est basse tant
// qu'au moins un des deux la tient à LOW ; le niveau est maintenu jusqu'à ce que le greffon la relâche
// (le Gate Array acquitte l'interruption comme pour la sienne). Le detach relâche tout.
// NB : NMI et BUSRQ sont écrites directement dans le Z80 (pas de OU entre greffons : le dernier qui
// relâche gagne). Le vecteur IM 2 d'un greffon passe par le callback int_ack (ABI 1.1) ; sans lui, ou
// s'il renvoie 0, le cycle d'acquittement présente &FF.
#define CORE_GREFFON_LINE_WAIT			1
#define CORE_GREFFON_LINE_INT			2
#define CORE_GREFFON_LINE_NMI			3
#define CORE_GREFFON_LINE_BUSRQ			4
// Niveaux : 0 = LOW (actif, signaux actifs-bas du Z80), 1 = HIGH (inactif)

// Directions d'une plage de ports
#define CORE_GREFFON_DIR_IN				0x1u
#define CORE_GREFFON_DIR_OUT			0x2u

// Bits renvoyés par joystick_in (1 = ligne tirée / direction active)
#define CORE_GREFFON_JOY_UP				0x01u
#define CORE_GREFFON_JOY_DOWN			0x02u
#define CORE_GREFFON_JOY_LEFT			0x04u
#define CORE_GREFFON_JOY_RIGHT			0x08u
#define CORE_GREFFON_JOY_FIRE2			0x10u
#define CORE_GREFFON_JOY_FIRE1			0x20u

// -----------------------------------------------------------------------------
//  Capacités de l'hôte (CoreGreffonHost.capabilities)
//  Une fonction d'hôte optionnelle n'est appelée que si sa capacité est annoncée.
//  C'est par ici que l'ABI s'ouvrira plus tard à d'éventuelles valeurs ciblées
//  (docs/extensions.md) sans changer les structures existantes.
// -----------------------------------------------------------------------------
#define CORE_GREFFON_CAP_FILES			0x00000001u	// file_read / file_write / file_list fournis par le client
#define CORE_GREFFON_CAP_CART_OVERRIDE	0x00000002u	// override_cart_bank / remap_now

// -----------------------------------------------------------------------------
//  Paramètres déclaratifs
//  Le greffon décrit ses paramètres ; le client les persiste et peut générer seul
//  un formulaire (GUI) ou une invite (CLI). Valeurs échangées en UTF-8 :
//    BOOL "0"/"1" - INT décimal - ENUM un des choix - STRING - PATH chemin du client
// -----------------------------------------------------------------------------
#define CORE_GREFFON_PARAM_BOOL			1
#define CORE_GREFFON_PARAM_INT			2
#define CORE_GREFFON_PARAM_ENUM			3
#define CORE_GREFFON_PARAM_STRING		4
#define CORE_GREFFON_PARAM_PATH			5		// Fichier ou répertoire, choisi/résolu par le client

#define CORE_GREFFON_APPLY_AT_ATTACH	0		// Pris en compte seulement à l'attache
#define CORE_GREFFON_APPLY_LIVE			1		// Peut être changé à chaud (callback set_param)

typedef struct CoreGreffonParam
{
	uint32_t			size;			// sizeof(CoreGreffonParam)
	const char*			key;			// Identifiant stable, ex. "printer_file" (ASCII, sans espace)
	const char*			label;			// Libellé affichable (UTF-8)
	uint32_t			type;			// CORE_GREFFON_PARAM_*
	uint32_t			apply;			// CORE_GREFFON_APPLY_*
	const char*			def;			// Valeur par défaut (texte, selon le type)
	int64_t				int_min;		// INT : bornes (inclusives)
	int64_t				int_max;
	const char* const*	choices;		// ENUM : tableau de choix (valeurs et libellés identiques)
	uint32_t			choice_count;
	const char*			path_filter;	// PATH : filtre d'extension indicatif, ex. "*.rom;*.cro" (NULL = aucun)
} CoreGreffonParam;

typedef struct CoreGreffonKV			// Valeur de paramètre transmise à l'attache
{
	const char*			key;
	const char*			value;
} CoreGreffonKV;

// -----------------------------------------------------------------------------
//  Description d'un greffon (renvoyée par CoreGreffon_Describe)
// -----------------------------------------------------------------------------
typedef struct CoreGreffonIORange		// Le greffon répond si (port & mask) == value
{
	uint16_t			mask;
	uint16_t			value;
	uint32_t			dir;			// CORE_GREFFON_DIR_IN | CORE_GREFFON_DIR_OUT
} CoreGreffonIORange;

typedef struct CoreGreffonDesc
{
	uint32_t				size;				// sizeof(CoreGreffonDesc)
	uint32_t				abi_major;			// CORE_GREFFON_ABI_MAJOR avec lequel le greffon a été compilé
	uint32_t				abi_minor;
	const char*				name;				// "PicoGX"
	const char*				version;			// "0.1.0" (version du greffon)
	const char*				description;		// Une ligne
	uint32_t				connectors;			// CORE_GREFFON_CONN_*
	uint32_t				required_caps;		// CORE_GREFFON_CAP_* sans lesquelles il ne peut pas fonctionner
	const CoreGreffonIORange*	io_ranges;		// CONN_EXPANSION : plages de ports réclamées
	uint32_t				io_range_count;
	uint32_t				cart_banks_mask;	// CONN_CARTRIDGE : banques cartouche PHYSIQUES observées (bit n = banque n)
	const CoreGreffonParam* const*	params;		// Tableau de pointeurs : l'ajout de champs à CoreGreffonParam ne casse rien
	uint32_t				param_count;
} CoreGreffonDesc;

// -----------------------------------------------------------------------------
//  Hôte : ce que le core offre au greffon (fourni à CoreGreffon_Attach)
//  Premier argument de chaque fonction : `host_ctx`, à repasser tel quel.
// -----------------------------------------------------------------------------
typedef struct CoreGreffonHost
{
	uint32_t			size;				// sizeof(CoreGreffonHost)
	uint32_t			abi_major;
	uint32_t			abi_minor;
	uint32_t			capabilities;		// CORE_GREFFON_CAP_* effectivement fournies
	uint32_t			clock_hz;			// Fréquence de l'unité de temps (4000000)
	void*				host_ctx;

	// Temps émulé courant (T-states 4 MHz depuis le reset)
	uint64_t			(*now)(void* host_ctx);

	// Pilote une ligne du Z80 (CORE_GREFFON_LINE_*), niveau 0 = LOW / 1 = HIGH
	void				(*set_line)(void* host_ctx, uint32_t line, uint32_t level);

	// Fournit une ROM d'extension (ROM logique `rom_number`, 0..255, 16 Ko). Les octets
	// sont copiés. Une ROM déjà posée (chargement client) n'est pas écrasée : retour
	// CORE_GREFFON_ERR_STATE. Au detach, les ROMs fournies par le greffon sont déchargées.
	int32_t				(*provide_rom)(void* host_ctx, uint32_t rom_number, const uint8_t* data, uint32_t size);

	// Journal : level 0 = erreur, 1 = avertissement, 2 = info, 3 = trace
	void				(*log)(void* host_ctx, uint32_t level, const char* message);

	// --- CAP_CART_OVERRIDE ---------------------------------------------------
	// Remplace la banque cartouche PHYSIQUE `bank` (0..31) par `data16k` (16384 octets,
	// COPIÉS : le tampon n'a pas à rester valide ; NULL = rétablit la banque d'origine, ce que
	// fait aussi le detach). Une banque n'a qu'un greffon propriétaire à la fois (ERR_STATE). Effet pour les lectures SUIVANTES seulement (ADR 0002) :
	// le core ne remplace jamais l'octet d'une lecture en cours.
	int32_t				(*override_cart_bank)(void* host_ctx, uint32_t bank, const uint8_t* data16k);
	// Applique tout de suite le changement de mapping (« le switch est instant »).
	void				(*remap_now)(void* host_ctx);

	// --- CAP_FILES : fichiers résolus par le client (le core ne touche à aucun fichier) ---
	// Les noms sont opaques (chemins relatifs au greffon, ou valeurs de paramètres PATH).
	// Appels synchrones et potentiellement lents : à éviter dans un callback chaud.
	int32_t				(*file_read)(void* host_ctx, const char* name, uint8_t* buffer, uint32_t capacity, uint32_t* size_out);
	int32_t				(*file_write)(void* host_ctx, const char* name, const uint8_t* data, uint32_t size);
	int32_t				(*file_list)(void* host_ctx, const char* directory,
										void (*emit)(void* emit_user, const char* name, uint32_t is_directory), void* emit_user);
} CoreGreffonHost;

// -----------------------------------------------------------------------------
//  Callbacks : ce que le greffon offre au core (renseignés dans CoreGreffon_Attach)
//  Tout pointeur NULL = événement non souhaité. `ctx` est le contexte du greffon.
// -----------------------------------------------------------------------------
typedef struct CoreGreffonCallbacks
{
	uint32_t			size;				// sizeof(CoreGreffonCallbacks)

	void				(*reset)(void* ctx, uint64_t cycle);	// Reset machine (le greffon reste attaché)
	void				(*detach)(void* ctx);					// Dernier appel : libérer ctx

	// --- CONN_EXPANSION ---
	// Lecture d'un port réclamé. Renvoie 1 et écrit *data si le greffon répond, 0 sinon (bus libre).
	int32_t				(*io_in)(void* ctx, uint16_t port, uint64_t cycle, uint8_t* data);
	void				(*io_out)(void* ctx, uint16_t port, uint8_t data, uint64_t cycle);

	// --- CONN_CARTRIDGE : OBSERVATION SEULEMENT ---
	// Lecture dans une banque observée. `cart_addr` = (banque physique << 14) | décalage (19 bits).
	// `is_fetch` = 1 pour un fetch d'opcode (M1), 0 pour une lecture de donnée. Retour void :
	// l'octet lu ne peut pas être changé (ADR 0002). Pour changer le mapping, appeler
	// override_cart_bank / remap_now sur l'hôte.
	void				(*cart_read)(void* ctx, uint32_t cart_addr, uint32_t is_fetch, uint64_t cycle);

	// --- CONN_PRINTER ---
	// Octet écrit sur le port imprimante, brut ; le bit 7 est la ligne strobe.
	void				(*printer_out)(void* ctx, uint8_t data, uint64_t cycle);
	// Ligne busy de l'imprimante : 1 = occupée. NULL = jamais occupée.
	int32_t				(*printer_busy)(void* ctx, uint64_t cycle);

	// --- CONN_JOYSTICK0 / CONN_JOYSTICK1 ---
	// État du port `port` (0 ou 1) : combinaison de CORE_GREFFON_JOY_* ; le core fusionne avec
	// l'état du clavier / des autres sources. `cycle` permet de dater les impulsions (souris).
	uint32_t			(*joystick_in)(void* ctx, uint32_t port, uint64_t cycle);

	// --- Paramètres ---
	// Changement à chaud d'un paramètre déclaré CORE_GREFFON_APPLY_LIVE. Renvoie CORE_GREFFON_*.
	int32_t				(*set_param)(void* ctx, const char* key, const char* value);

	// --- État pour les snapshots (tampon opaque rangé par le client, hors format SNA du core) ---
	// Si `capacity` est trop petit : renvoie CORE_GREFFON_ERR_BUFFER, taille nécessaire dans *size_out.
	int32_t				(*save_state)(void* ctx, uint8_t* buffer, uint32_t capacity, uint32_t* size_out);
	int32_t				(*load_state)(void* ctx, const uint8_t* buffer, uint32_t size);

	// --- Interruptions et temps (ABI 1.1) ---
	// Acquittement d'interruption (cycle M1 + IORQ) alors que CE greffon tient la ligne INT à LOW. Renvoie 1
	// et écrit *vector si le greffon répond (octet présenté au Z80, p.ex. vecteur IM 2 du CTC Z84C30) : il
	// est alors prioritaire (daisy-chain IEI/IEO) et le Gate Array n'est PAS acquitté, son interruption reste
	// en attente. Renvoie 0 : acquittement d'origine (&FF, Gate Array acquitté). Le greffon peut relâcher
	// INT depuis ce callback. Plusieurs greffons tiennent INT : le premier (ordre d'attache) qui répond gagne.
	int32_t				(*int_ack)(void* ctx, uint64_t cycle, uint8_t* vector);
	// Temps émulé : appelé après chaque instruction du Z80 tant que le greffon est attaché (permet de
	// lever INT au bon cycle sans accès au bus, p.ex. timers du CTC). NULL = non souhaité, sans aucun coût.
	void				(*tick)(void* ctx, uint64_t cycle);
} CoreGreffonCallbacks;

// -----------------------------------------------------------------------------
//  Points d'entrée à exporter par un greffon
// -----------------------------------------------------------------------------

// Décrit le greffon. Appelé une fois au chargement, avant toute attache ; le pointeur
// renvoyé reste valable tant que la bibliothèque est chargée. Ne dépend d'aucun état.
//   CORE_GREFFON_EXPORT const CoreGreffonDesc* CoreGreffon_Describe(void);
typedef const CoreGreffonDesc* (*CoreGreffon_Describe_Fn)(void);

// Attache le greffon. `initial` = valeurs de paramètres persistées par le client (peut être
// vide : le greffon prend alors les défauts). Le greffon renseigne `*callbacks` (avec
// `callbacks->size`) et `*ctx`. Un échec laisse le greffon non attaché.
//   CORE_GREFFON_EXPORT int32_t CoreGreffon_Attach(const CoreGreffonHost* host,
//          const CoreGreffonKV* initial, uint32_t initial_count,
//          CoreGreffonCallbacks* callbacks, void** ctx);
typedef int32_t (*CoreGreffon_Attach_Fn)(const CoreGreffonHost* host,
		const CoreGreffonKV* initial, uint32_t initial_count,
		CoreGreffonCallbacks* callbacks, void** ctx);

// -----------------------------------------------------------------------------
//  API cliente (implémentée par le core, appelée par le client)
//  Le client gère les greffons : le core ne scrute aucun répertoire et n'ouvre aucun
//  fichier. Non disponible sur WASM. Déclarée seulement si AMSPIRIT_CORE_API est défini
//  (inclure Core_Amspirit.h d'abord) : un greffon n'en a pas besoin.
//  v1.0 : CONN_EXPANSION, CONN_CARTRIDGE et CONN_PRINTER sont câblés ; lignes INT/WAIT/NMI/BUSRQ pilotables ; le joystick fait répondre
//  Attach -> ERR_UNSUPPORTED. Appels depuis le fil d'émulation (ou émulation à l'arrêt).
//  Cycle de vie : Load (dlopen + Describe) -> Attach -> [Set_Param, Save/Load_State] ->
//  Detach -> Unload.
// -----------------------------------------------------------------------------
#ifdef AMSPIRIT_CORE_API

typedef struct CoreGreffonFileOps		// Fournis par le client (active CORE_GREFFON_CAP_FILES)
{
	uint32_t			size;			// sizeof(CoreGreffonFileOps)
	void*				user;
	int32_t				(*read)(void* user, const char* name, uint8_t* buffer, uint32_t capacity, uint32_t* size_out);
	int32_t				(*write)(void* user, const char* name, const uint8_t* data, uint32_t size);
	int32_t				(*list)(void* user, const char* directory,
									void (*emit)(void* emit_user, const char* name, uint32_t is_directory), void* emit_user);
} CoreGreffonFileOps;

// Optionnel : récepteur du journal des greffons (level : 0 erreur .. 3 trace). Sans lui, perdu.
AMSPIRIT_CORE_API void		Core_Greffon_Set_Log(void (*log)(void* user, uint32_t level, const char* message), void* user);

// Optionnel : sans lui, la capacité CAP_FILES est absente.
AMSPIRIT_CORE_API int32_t	Core_Greffon_Set_File_Ops(const CoreGreffonFileOps* ops);

// Charge la bibliothèque et lit sa description (aucun effet sur la machine). `*id` identifie le greffon.
AMSPIRIT_CORE_API int32_t	Core_Greffon_Load(const char* library_path, uint32_t* id);
AMSPIRIT_CORE_API int32_t	Core_Greffon_Get_Desc(uint32_t id, const CoreGreffonDesc** desc);

// Branche l'extension (CORE_GREFFON_ERR_CONFLICT si un port réclamé est déjà décodé).
AMSPIRIT_CORE_API int32_t	Core_Greffon_Attach(uint32_t id, const CoreGreffonKV* params, uint32_t count);
AMSPIRIT_CORE_API int32_t	Core_Greffon_Detach(uint32_t id);
AMSPIRIT_CORE_API int32_t	Core_Greffon_Unload(uint32_t id);

// Paramètre à chaud (APPLY_LIVE) ; sinon CORE_GREFFON_ERR_STATE.
AMSPIRIT_CORE_API int32_t	Core_Greffon_Set_Param(uint32_t id, const char* key, const char* value);

// État pour les snapshots (rangé par le client, à côté du SNA)
AMSPIRIT_CORE_API int32_t	Core_Greffon_Save_State(uint32_t id, uint8_t* buffer, uint32_t capacity, uint32_t* size_out);
AMSPIRIT_CORE_API int32_t	Core_Greffon_Load_State(uint32_t id, const uint8_t* buffer, uint32_t size);

#endif // AMSPIRIT_CORE_API

#ifdef __cplusplus
}
#endif
