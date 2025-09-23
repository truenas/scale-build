#############################################################################
# Makefile for building: TrueNAS SCALE
#############################################################################
PYTHON?=/usr/bin/python3
COMMIT_HASH=$(shell git rev-parse --short HEAD)
PACKAGES?=""
REPO_CHANGED=$(shell if [ -d "./venv-$(COMMIT_HASH)" ]; then git status --porcelain | grep -c "scale_build/"; else echo "1"; fi)
# Check if --break-system-packages flag is supported by pip
BREAK_SYS_PKGS_FLAG=$(shell ${PYTHON} -m pip help install | grep -q -- '--break-system-packages' && echo "--break-system-packages" || echo "")

.DEFAULT_GOAL := all

check:
ifneq ($(REPO_CHANGED),0)
	@echo "Setting up new virtual environment"
	@rm -rf venv-*
	@${PYTHON} -m pip install $(BREAK_SYS_PKGS_FLAG) -U virtualenv >/dev/null || { echo "Failed to install/upgrade virtualenv package"; exit 1; }
	@${PYTHON} -m venv venv-${COMMIT_HASH} || { echo "Failed to create virutal environment"; exit 1; }
	@{ . ./venv-${COMMIT_HASH}/bin/activate && \
		python3 -m pip install -r requirements.txt >/dev/null 2>&1 && \
		python3 -m pip install . >/dev/null 2>&1; } || { echo "Failed to install scale-build"; exit 1; }
endif

all: checkout packages update iso

clean: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build clean
checkout: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build checkout
check_upstream_package_updates: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build check_upstream_package_updates
iso: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build iso
packages: check
ifeq ($(PACKAGES),"")
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build packages
else
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build packages --packages ${PACKAGES}
endif
update: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build update
validate_manifest: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build validate --no-validate-system_state
validate: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build validate

branchout: checkout
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build branchout $(args)
