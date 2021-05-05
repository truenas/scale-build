#############################################################################
# Makefile for building: TrueNAS SCALE
#############################################################################
PYTHON?=/usr/bin/python3
COMMIT_HASH=$(shell git rev-parse --short HEAD)

check:
ifeq ("$(wildcard ./venv-${COMMIT_HASH})","")
	@echo "Setting up new virtual environment"
	@rm -rf venv-*
	@${PYTHON} -m pip install -U virtualenv >/dev/null 2>&1 || { echo "Failed to install/upgrade virtualenv package"; exit 1; }
	@${PYTHON} -m venv venv-${COMMIT_HASH} || { echo "Failed to create virutal environment"; exit 1; }
	@{ . ./venv-${COMMIT_HASH}/bin/activate && \
		python3 -m pip install -r requirements.txt >/dev/null 2>&1 && \
		python3 setup.py install >/dev/null 2>&1; } || { echo "Failed to install scale-build"; exit 1; }
endif

all: checkout packages update iso

clean: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build clean
checkout: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build checkout
iso: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build iso
packages: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build packages
update: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build update
validate_manifest: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build validate --no-validate-system_state
validate: check
	. ./venv-${COMMIT_HASH}/bin/activate && scale_build validate
