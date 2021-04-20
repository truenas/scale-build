#############################################################################
# Makefile for building: TrueNAS SCALE
#############################################################################
PYTHON?=/usr/bin/python3
COMMIT_HASH=$(shell git rev-parse --short HEAD)

check:
ifeq ("$(wildcard ./venv-${COMMIT_HASH})","")
	@rm -rf venv-*
	@apt install -y python3-distutils python3-pip python3-venv >/dev/null 2>&1
	@${PYTHON} -m venv venv-${COMMIT_HASH}
	@. ./venv-${COMMIT_HASH}/bin/activate && \
		python3 -m pip install -r requirements.txt >/dev/null 2>&1 && \
		python3 setup.py install >/dev/null 2>&1;
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
