#############################################################################
# Makefile for building: TrueOS
#############################################################################

all: packages iso

clean:
	@sh scripts/build.sh clean
iso:
	@sh scripts/build.sh iso
packages:
	@sh scripts/build.sh packages
checkout:
	@sh scripts/build.sh checkout
