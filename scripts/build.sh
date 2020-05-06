#!/bin/sh

# Source helper functions
. scripts/functions.sh

TMPFS="./tmp/tmpfs"
CHROOT_BASEDIR="${TMPFS}/chroot"
CHROOT_OVERLAY="${TMPFS}/chroot-overlay"
DPKG_OVERLAY="./tmp/dpkg-overlay"
WORKDIR_OVERLAY="${TMPFS}/workdir-overlay"
PKG_DIR="./tmp/pkgdir"
LOG_DIR="./logs"
MANIFEST="./conf/build.manifest"
SOURCES="./sources"

# Makes some perl scripts happy during package builds
export LC_ALL="C"
export LANG="C"

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
}

preflight_check() {
	# Check for deps
	DEPS="debootstrap jq git"
	for i in $DEPS
	do
		which $i >/dev/null 2>/dev/null
		if [ $? -ne 0 ] ; then
			exit_err "Failed preflight check. Please install: $i"
		fi
	done

	if [ ! -d tmp/ ] ; then mkdir tmp ; fi
	if [ ! -d ${PKG_DIR} ] ; then mkdir ${PKG_DIR} ; fi
	if [ -d ${LOG_DIR} ] ; then
		rm -rf ${LOG_DIR}
	fi
	mkdir -p ${LOG_DIR}

	# Validate MANIFEST
	jq -r '.' ${MANIFEST} >/dev/null 2>/dev/null || exit_err "Invalid $MANIFEST"
}

make_bootstrapdir() {
	del_overlayfs
	del_bootstrapdir

	# Setup our ramdisk, up to 2G should suffice
	mkdir -p ${TMPFS}
	mount -t tmpfs -o size=8G tmpfs ${TMPFS}

	# Bootstrap the debian base system
	apt-key add keys/truenas.gpg 2>/dev/null >/dev/null || exit_err "Failed adding truenas.gpg apt-key"
	aptrepo=$(jq -r '."apt-repos"."url"' $MANIFEST)
	aptdist=$(jq -r '."apt-repos"."distribution"' $MANIFEST)
	aptcomp=$(jq -r '."apt-repos"."components"' $MANIFEST)
	debootstrap --keyring /etc/apt/trusted.gpg bullseye ${CHROOT_BASEDIR} $aptrepo || exit_err "Failed debootstrap"
	mount proc ${CHROOT_BASEDIR}/proc -t proc
	mount sysfs ${CHROOT_BASEDIR}/sys -t sysfs

	# Add extra packages for builds
	chroot ${CHROOT_BASEDIR} apt install -y build-essential dh-make devscripts fakeroot || exit_err "Failed chroot setup"

	# Save the correct repo in sources.list
	echo "deb $aptrepo $aptdist $aptcomp" > ${CHROOT_BASEDIR}/etc/apt/sources.list

	# Add additional repos
	for k in $(jq -r '."apt-repos"."additional" | keys[]' ${MANIFEST} 2>/dev/null | tr -s '\n' ' ')
	do
		apturl=$(jq -r '."apt-repos"."additional"['$k']."url"' $MANIFEST)
		aptdist=$(jq -r '."apt-repos"."additional"['$k']."distribution"' $MANIFEST)
		aptcomp=$(jq -r '."apt-repos"."additional"['$k']."component"' $MANIFEST)
		aptkey=$(jq -r '."apt-repos"."additional"['$k']."key"' $MANIFEST)
		echo "Adding additional repo: $apturl"
		cp $aptkey ${CHROOT_BASEDIR}/apt.key || exit_err "Failed copying repo apt key"
		chroot ${CHROOT_BASEDIR} apt-key add /apt.key || exit_err "Failed adding apt-key"
		rm ${CHROOT_BASEDIR}/apt.key
		echo "deb $apturl $aptdist $aptcomp" >> ${CHROOT_BASEDIR}/etc/apt/sources.list

	done
	cat ${CHROOT_BASEDIR}/etc/apt/sources.list

	chroot ${CHROOT_BASEDIR} apt update || exit_err "Failed apt update"

	echo "deb file:/packages ./" >> ${CHROOT_BASEDIR}/etc/apt/sources.list || exit_err "Failed local deb repo"

	umount -f ${CHROOT_BASEDIR}/proc
	umount -f ${CHROOT_BASEDIR}/sys

	return 0
}

del_bootstrapdir() {
	echo "Removing package build chroot"
	umount -f ${CHROOT_BASEDIR}/proc 2>/dev/null
	umount -f ${CHROOT_BASEDIR}/sys 2>/dev/null
	umount -f ${CHROOT_BASEDIR} 2>/dev/null
	rmdir ${CHROOT_BASEDIR} 2>/dev/null
	umount -f ${TMPFS} 2>/dev/null
	rmdir ${TMPFS} 2>/dev/null
}

del_overlayfs() {

	umount -f ${DPKG_OVERLAY}/packages 2>/dev/null
	umount -f ${DPKG_OVERLAY}/proc 2>/dev/null
	umount -f ${DPKG_OVERLAY}/sys 2>/dev/null
	umount -f ${DPKG_OVERLAY} 2>/dev/null
	rm -rf ${DPKG_OVERLAY} 2>/dev/null
	rm -rf ${CHROOT_OVERLAY} 2>/dev/null
	rm -rf ${WORKDIR_OVERLAY} 2>/dev/null
}

mk_overlayfs() {

	# Create a new overlay directory
	mkdir -p ${CHROOT_OVERLAY}
	mkdir -p ${DPKG_OVERLAY}
	mkdir -p ${WORKDIR_OVERLAY}
	mount -t overlay -o lowerdir=${CHROOT_BASEDIR},upperdir=${CHROOT_OVERLAY},workdir=${WORKDIR_OVERLAY} none ${DPKG_OVERLAY}/ || exit_err "Failed overlayfs"
	mount proc ${DPKG_OVERLAY}/proc -t proc || "Failed mount proc"
	mount sysfs ${DPKG_OVERLAY}/sys -t sysfs || "Failed mount sysfs"
	mkdir -p ${DPKG_OVERLAY}/packages || exit_err "Failed mkdir /packages"
	mount --bind ${PKG_DIR} ${DPKG_OVERLAY}/packages || "Failed mount --bind /packages"
}

build_deb_packages() {
	echo "`date`: Creating debian bootstrap directory: (${LOG_DIR}/bootstrap_chroot.log)"
	make_bootstrapdir >${LOG_DIR}/bootstrap_chroot.log 2>&1
	if [ ! -d "${LOG_DIR}/packages" ] ; then
		mkdir -p ${LOG_DIR}/packages
	fi


	for k in $(jq -r '."sources" | keys[]' ${MANIFEST} 2>/dev/null | tr -s '\n' ' ')
	do
		del_overlayfs
		mk_overlayfs

		NAME=$(jq -r '."sources"['$k']."name"' ${MANIFEST})
		PREBUILD=$(jq -r '."sources"['$k']."prebuildcmd"' ${MANIFEST})
		if [ ! -d "${SOURCES}/${NAME}" ] ; then
			exit_cleanup "Missing sources for ${NAME}, did you forget to run 'make checkout'?"
		fi
		if [ "$PREBUILD" = "null" ] ; then
			unset PREBUILD
		fi
		echo "`date`: Building package [$NAME] (${LOG_DIR}/packages/${NAME}.log)"
		build_dpkg "$NAME" "$PREBUILD" >${LOG_DIR}/packages/${NAME}.log 2>&1

		del_overlayfs
	done

	del_bootstrapdir
	return 0
}

build_dpkg() {
	if [ -d "${DPKG_OVERLAY}/packages/Packages.gz" ] ; then
		chroot ${DPKG_OVERLAY} apt update || exit_err "Failed apt update"
	fi
	deflags="-us -uc -b"
	cp -r ${SOURCES}/${1} ${DPKG_OVERLAY}/dpkg-src || exit_err "Failed to copy sources"
	if [ -e "${DPKG_OVERLAY}/dpkg-src/debian/control" ] ; then
		subdir="/dpkg-src"
		pkgdir="/"
	elif [ -e "${DPKG_OVERLAY}/dpkg-src/debian/debian/control" ] ; then
		subdir="/dpkg-src/debian"
		pkgdir="/dpkg-src"
	else
		exit_err "Missing debian/control file for $1"
	fi

	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $subdir && mk-build-deps --build-dep" || exit_err "Failed mk-build-deps"
	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $subdir && apt install -y ./*.deb" || exit_err "Failed install build deps"
	# Check for a prebuild command
	if [ -n "$2" ] ; then
		chroot ${DPKG_OVERLAY} /bin/bash -c "cd $subdir && $2" || exit_err "Failed to prebuild"
	fi
	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $subdir && debuild $deflags" || exit_err "Failed to build package"

	# Move out the resulting packages
	echo "Copying finished packages"

	mv ${DPKG_OVERLAY}${pkgdir}/*.deb ${PKG_DIR}/ 2>/dev/null
	mv ${DPKG_OVERLAY}${pkgdir}/*.udeb ${PKG_DIR}/ 2>/dev/null

	# Update the local APT repo
	echo "Building local APT repo Packages.gz..."
	chroot ${DPKG_OVERLAY} /bin/bash -c 'cd /packages && dpkg-scanpackages . /dev/null | gzip -9c > Packages.gz'
}

checkout_sources() {
	if [ ! -d "$SOURCES" ] ; then
		mkdir -p ${SOURCES}
	fi

	for k in $(jq -r '."sources" | keys[]' ${MANIFEST} 2>/dev/null | tr -s '\n' ' ')
	do
		#eval "CHECK=\$$k"
		NAME=$(jq -r '."sources"['$k']."name"' ${MANIFEST})
		REPO=$(jq -r '."sources"['$k']."repo"' ${MANIFEST})
		BRANCH=$(jq -r '."sources"['$k']."branch"' ${MANIFEST})
		if [ -z "$NAME" ] ; then exit_err "Invalid NAME: $NAME" ; fi
		if [ -z "$REPO" ] ; then exit_err "Invalid REPO: $REPO" ; fi
		if [ -z "$BRANCH" ] ; then exit_err "Invalid BRANCH: $BRANCH" ; fi

		if [ -d ${SOURCES}/${NAME} ] ; then
			rm -r ${SOURCES}/${NAME}
		fi
		git clone --depth=1 -b ${BRANCH} ${REPO} ${SOURCES}/${NAME}
																done
}

preflight_check

case $1 in
	iso) ;;
	checkout) checkout_sources ;;
	packages) build_deb_packages ;;
	clean) cleanup ;;
	*) exit_err "Invalid build option!" ;;
esac

exit 0
