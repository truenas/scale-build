#############################################################################
# Makefile for building: TrueNAS SCALE
#############################################################################

all: checkout packages update iso

clean:
	@sh scripts/build.sh clean
checkout:
	@sh scripts/build.sh checkout
iso:
	@sh scripts/build.sh iso
packages:
	@sh scripts/build.sh packages
update:
	@sh scripts/build.sh update
