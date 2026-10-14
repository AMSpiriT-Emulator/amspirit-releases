# Règles communes d'un plugin. À inclure depuis <plugin>/Makefile après avoir défini :
#   PLUGIN   nom du projet (répertoire)
#   MODULE   nom du module produit (sans extension), vide si le projet n'en produit pas
# Usage : make [PLATFORM=linux|windows|arm] [all|test|dist|clean]
include $(dir $(lastword $(MAKEFILE_LIST)))platform.mk

SRC_DIR  := $(CURDIR)
BUILD    := $(SRC_DIR)/$(BUILD_NAME)
DIST     := $(abspath $(SRC_DIR)/../dist)/$(PLATFORM)
SETUP_FLAGS := $(if $(CROSS_FILE),--cross-file $(CROSS_FILE)) $(MESON_OPTS)

.PHONY: all test dist clean
all: $(BUILD)/build.ninja
	ninja -C $(BUILD)

$(BUILD)/build.ninja:
	meson setup $(BUILD) $(SRC_DIR) $(SETUP_FLAGS)

test: all
ifeq ($(CAN_TEST),1)
	meson test -C $(BUILD) --print-errorlogs
else
	@echo "[$(PLUGIN)] tests ignorés pour PLATFORM=$(PLATFORM)"
endif

dist: all
ifneq ($(MODULE),)
	mkdir -p $(DIST)
	cp $(BUILD)/$(MODULE).$(EXT) $(DIST)/
endif

clean:
	rm -rf $(BUILD)
