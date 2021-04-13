#############################################################################
# Makefile for building: TrueNAS SCALE
#############################################################################
PYTHON?=/usr/bin/python3

all: checkout packages update iso

clean:
	${PYTHON} scale_build clean
checkout:
	${PYTHON} scale_build checkout
iso:
	${PYTHON} scale_build iso
packages:
	${PYTHON} scale_build packages
update:
	${PYTHON} scale_build update
