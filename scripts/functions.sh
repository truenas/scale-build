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

	# Check for deps
	DEPS="make debootstrap jq git xorriso grub-mkrescue mformat mksquashfs unzip"
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
	jq -r '.' ${MANIFEST} >/dev/null 2>/dev/null || exit_err "Invalid $MANIFEST"
}
