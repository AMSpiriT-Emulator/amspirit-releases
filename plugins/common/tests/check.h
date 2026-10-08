// Micro-cadre de test : un échec affiche le fichier:ligne et la condition, puis fait échouer le programme.
#pragma once
#include <stdio.h>
#include <stdlib.h>
static int gf_failures;
#define CHECK(cond) do { if (!(cond)) { fprintf(stderr, "%s:%d: CHECK(%s) a echoue\n", __FILE__, __LINE__, #cond); ++gf_failures; } } while (0)
#define CHECK_DONE() (gf_failures ? (fprintf(stderr, "%d echec(s)\n", gf_failures), 1) : 0)
