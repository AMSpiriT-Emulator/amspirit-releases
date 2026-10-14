# Compile tous les plugins.
# Usage : make [PLATFORM=linux|windows|arm] [all|test|dist|clean]
#         make digiblaster            (un seul plugin)
#         make playcity-dist PLATFORM=windows
# Les modules produits sont copiés dans dist/<PLATFORM>/ par « dist ».
PLUGINS := common digiblaster playcity
TARGETS := all test dist clean

.PHONY: $(TARGETS) $(PLUGINS) $(foreach p,$(PLUGINS),$(foreach t,$(TARGETS),$(p)-$(t)))

$(TARGETS): %: $(addsuffix -%,$(PLUGINS))

$(PLUGINS): %: %-all

define RULE
$(1)-$(2):
	$$(MAKE) -C $(1) $(2)
endef
$(foreach p,$(PLUGINS),$(foreach t,$(TARGETS),$(eval $(call RULE,$(p),$(t)))))
