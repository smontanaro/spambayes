EXTRA_TARGETS=subdirs
include ../scripts/make.rules
ROOT_DIR = ..
ROOT_OFFSET = apps

# Not sure what the correct magic for subdirs is
# want 'make' to recurse without 'install' and
# 'make install' to recurse *with* 'install'
local_install:
	cd outlook; $(MAKE) $(MAKEFLAGS) install

subdirs:
	cd outlook; $(MAKE) $(MAKEFLAGS)
