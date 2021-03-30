#!/bin/sh

exit_err() {
	if [ -n "$2" ] ; then
		EXIT_CODE=$2
	else
		EXIT_CODE=1
	fi
	del_overlayfs
	del_bootstrapdir
	echo "ERROR: $1" >&2
	exit $EXIT_CODE
}

exit_clean() {
	del_overlayfs
	del_bootstrapdir
	exit_err "$1"
}

cleanup() {
	del_overlayfs
	del_bootstrapdir
	rm -rf tmp
	rm -rf ${SOURCES}
	rm -rf ${LOG_DIR}
}

prep_yq() {
	if [ -e "tmp/bin/yq" ] ; then
		return 0
	fi

	echo "Fetching yq..."

	# Download and stash the YQ binary we'll use for YAML parsing
	mkdir -p tmp/bin/yq

	local VERSION=v4.6.1
	local BINARY=yq_linux_amd64
	wget https://github.com/mikefarah/yq/releases/download/${VERSION}/${BINARY}.tar.gz -O - 2>/dev/null | \
		tar xz && mv ${BINARY} tmp/bin/yq
	if [ $? -ne 0 ] ; then echo "Failed downloading yq" && exit 1 ; fi
	chmod 755 tmp/bin/yq
}

preflight_check() {

	if [ $(id -u) != "0" ]; then
		exit_err "Must be run as root (or using sudo)!"
	fi

	local mem=$(grep MemTotal /proc/meminfo | awk -F ' ' '{print $2}')
	if [ $mem -lt 15500000 ] ; then
		echo "WARNING: Running with less than 16GB of memory. Build may fail..."
		HAS_LOW_RAM=1
		sleep 5
	fi

	# Check that yq binary is present
	prep_yq

	# Check for deps
	DEPS="make debootstrap git xorriso grub-mkrescue mksquashfs unzip"
	for i in $DEPS
	do
		which $i >/dev/null 2>/dev/null
		if [ $? -ne 0 ] ; then
			exit_err "Failed preflight check. Please install: $i"
		fi
	done

	if [ ! -d "/lib/grub/x86_64-efi" -a ! -d "/usr/lib/grub/x86_64-efi" ] ; then
		exit_err "Missing installed package: grub-efi-amd64-bin"
	fi
	if [ ! -d "/lib/grub/i386-pc" -a ! -d "/usr/lib/grub/i386-pc" ] ; then
		exit_err "Missing installed package: grub-pc-bin"
	fi

	if [ ! -d tmp/ ] ; then mkdir tmp ; fi
	if [ ! -d ${PKG_DIR} ] ; then mkdir ${PKG_DIR} ; fi
	if [ ! -d ${HASH_DIR} ] ; then mkdir -p ${HASH_DIR} ; fi
	mkdir -p ${LOG_DIR}

	# Validate MANIFEST
	${YQ} e ${MANIFEST} >/dev/null 2>/dev/null || exit_err "Invalid $MANIFEST"
}
