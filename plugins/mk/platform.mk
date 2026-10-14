# Spécificités par plateforme. PLATFORM = linux (natif) | windows | arm
# Noms de répertoires alignés sur amspirit-lite (build, build_windows, build_rpi5).
# Aucune notion de conteneur ici : on suppose la chaîne d'outils de la plateforme visée présente.
PLATFORM ?= linux
CROSS_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../cross)

ifeq ($(PLATFORM),linux)
  EXT := so
  BUILD_NAME := build
  CROSS_FILE :=
  CAN_TEST := 1
else ifeq ($(PLATFORM),windows)
  EXT := dll
  BUILD_NAME := build_windows
  CROSS_FILE := $(CROSS_DIR)/windows-x86_64.ini
  CAN_TEST := 0          # binaires Windows : non exécutables ici
else ifeq ($(PLATFORM),arm)
  EXT := so
  BUILD_NAME := build_rpi5
  CROSS_FILE := $(CROSS_DIR)/linux-aarch64.ini
  CAN_TEST := 0          # binaires ARM : non exécutables ici
else
  $(error PLATFORM inconnue '$(PLATFORM)' (linux, windows, arm))
endif

MESON_OPTS ?=
