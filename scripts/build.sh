#!/bin/sh

TMPFS="./tmp/tmpfs"
CHROOT_BASEDIR="${TMPFS}/chroot"
CHROOT_OVERLAY="${TMPFS}/chroot-overlay"
DPKG_OVERLAY="./tmp/dpkg-overlay"
WORKDIR_OVERLAY="${TMPFS}/workdir-overlay"
CACHE_DIR="./tmp/cache"
PKG_DIR="./tmp/pkgdir"
RELEASE_DIR="./tmp/release"
UPDATE_DIR="./tmp/update"
CD_DIR="./tmp/cdrom"
LOG_DIR="./logs"
HASH_DIR="./tmp/pkghashes"
MANIFEST="./conf/build.manifest"
SOURCES="./sources"

# Makes some perl scripts happy during package builds
export LC_ALL="C"
export LANG="C"

# Never go full interactive on any packages
export DEBIAN_FRONTEND="noninteractive"

# Source helper functions
. scripts/functions.sh

make_bootstrapdir() {
	del_overlayfs
	del_bootstrapdir

	# Make sure apt cache is ready
	if [ ! -d "${CACHE_DIR}/apt" ] ; then
		mkdir -p ${CACHE_DIR}/apt || exit_err "Failed mkdir ${CACHE_DIR}/apt"
	fi

	case $1 in
		cd|CD)
			CDBUILD=1
			DEOPTS="--components=main,contrib,nonfree --variant=minbase --include=systemd-sysv,gnupg,grub-pc,grub-efi-amd64-signed"
			CACHENAME="cdrom"
			;;
		package|packages)
			DEOPTS=""
			CACHENAME="package"
			unset CDBUILD
			;;
		*)
			exit_err "Invalid bootstrapdir target"
			;;
	esac

	# Setup our ramdisk, up to 4G should suffice
	mkdir -p ${TMPFS}
	mount -t tmpfs -o size=6G tmpfs ${TMPFS}

	# Check if there is a cache we can restore
	if [ -e "${CACHE_DIR}/basechroot-${CACHENAME}.squashfs" ]; then
		restore_build_cache "${CACHENAME}"
		return 0
	fi

	# Bootstrap the debian base system
	apt-key --keyring /etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg add keys/truenas.gpg 2>/dev/null >/dev/null || exit_err "Failed adding truenas.gpg apt-key"
	aptrepo=$(jq -r '."apt-repos"."url"' $MANIFEST)
	aptdist=$(jq -r '."apt-repos"."distribution"' $MANIFEST)
	aptcomp=$(jq -r '."apt-repos"."components"' $MANIFEST)
	debootstrap ${DEOPTS} --keyring /etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg \
		bullseye ${CHROOT_BASEDIR} $aptrepo \
		|| exit_err "Failed debootstrap"
	mount proc ${CHROOT_BASEDIR}/proc -t proc
	mount sysfs ${CHROOT_BASEDIR}/sys -t sysfs
	mount --bind ${CACHE_DIR}/apt ${CHROOT_BASEDIR}/var/cache/apt || exit_err "Failed mount --bind /var/cache/apt"

	if [ -z "$CDBUILD" ] ; then
		# Add extra packages for builds
		chroot ${CHROOT_BASEDIR} apt install -y build-essential \
			dh-make devscripts fakeroot \
			|| exit_err "Failed chroot setup"
	fi

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

	# If not building a cd environment
	if [ -z "$CDBUILD" ] ; then
		check_basechroot_changed
	fi

	# Update apt
	chroot ${CHROOT_BASEDIR} apt update || exit_err "Failed apt update"

	# Put our local package up at the top of the foodchain
	mv ${CHROOT_BASEDIR}/etc/apt/sources.list ${CHROOT_BASEDIR}/etc/apt/sources.list.prev || exit_err "mv"
	echo "deb [trusted=yes] file:/packages /" > ${CHROOT_BASEDIR}/etc/apt/sources.list || exit_err "Failed local deb repo"
	cat ${CHROOT_BASEDIR}/etc/apt/sources.list.prev >> ${CHROOT_BASEDIR}/etc/apt/sources.list || exit_err "cat"
	rm ${CHROOT_BASEDIR}/etc/apt/sources.list.prev


	umount -f ${CHROOT_BASEDIR}/var/cache/apt
	umount -f ${CHROOT_BASEDIR}/proc
	umount -f ${CHROOT_BASEDIR}/sys

	# Build the ZFS module first, so we can install into base chroot
	echo "Building ZFS Modules"
	mk_overlayfs
	build_zfs_modules
	del_overlayfs

	# Install the new ZFS module into the chroot
	mount proc ${CHROOT_BASEDIR}/proc -t proc
	mount sysfs ${CHROOT_BASEDIR}/sys -t sysfs
	mkdir ${CHROOT_BASEDIR}/packages
	mount --bind ${PKG_DIR} ${CHROOT_BASEDIR}/packages || exit_err "Failed mount --bind /packages"
	mount --bind ${CACHE_DIR}/apt ${CHROOT_BASEDIR}/var/cache/apt || exit_err "Failed mount --bind /var/cache/apt"
	install_zfs_modules "${CHROOT_BASEDIR}"
	umount -f ${CHROOT_BASEDIR}/var/cache/apt
	umount -f ${CHROOT_BASEDIR}/packages
	umount -f ${CHROOT_BASEDIR}/proc
	umount -f ${CHROOT_BASEDIR}/sys

	save_build_cache "${CACHENAME}"

	return 0
}

restore_build_cache() {
	if [ ! -d "${CHROOT_BASEDIR}" ] ; then
		mkdir -p ${CHROOT_BASEDIR}
	fi
	echo "Restoring CHROOT_BASEDIR for runs..."
	unsquashfs -f -d ${CHROOT_BASEDIR} ${CACHE_DIR}/basechroot-${1}.squashfs || exit_err "Failed unsquashfs"
}

save_build_cache() {
	if [ ! -d "${CACHE_DIR}" ] ; then
		mkdir -p ${CACHE_DIR}
	fi
	echo "Caching CHROOT_BASEDIR for future runs..."
	mksquashfs ${CHROOT_BASEDIR} ${CACHE_DIR}/basechroot-${1}.squashfs || exit_err "Failed squashfs"
}

check_basechroot_changed() {
	BASEHASH=$(chroot ${CHROOT_BASEDIR} apt list --installed 2>/dev/null | sha256sum | awk '{print $1}')
	if [ -e "${HASH_DIR}/.basechroot.hash" ] ; then
		if [ "$(cat ${HASH_DIR}/.basechroot.hash)" != "$BASEHASH" ] ; then
			echo "Upstream repository changes detected. Rebuilding all packages..."
			rm ${HASH_DIR}/*.hash
			rm ${PKG_DIR}/*.deb 2>/dev/null
			rm ${PKG_DIR}/*.udeb 2>/dev/null
		fi
	fi
	echo "$BASEHASH" > ${HASH_DIR}/.basechroot.hash
}

del_bootstrapdir() {
	umount -f ${CHROOT_BASEDIR}/proc 2>/dev/null
	umount -f ${CHROOT_BASEDIR}/sys 2>/dev/null
	umount -f ${CHROOT_BASEDIR} 2>/dev/null
	umount -Rf ${CHROOT_BASEDIR} 2>/dev/null
	rmdir ${CHROOT_BASEDIR} 2>/dev/null
	umount -Rf ${TMPFS} 2>/dev/null
	rmdir ${TMPFS} 2>/dev/null
}

del_overlayfs() {

	umount -f ${DPKG_OVERLAY}/var/cache/apt 2>/dev/null
	umount -f ${DPKG_OVERLAY}/packages 2>/dev/null
	umount -f ${DPKG_OVERLAY}/proc 2>/dev/null
	umount -f ${DPKG_OVERLAY}/sys 2>/dev/null
	umount -f ${DPKG_OVERLAY} 2>/dev/null
	umount -Rf ${DPKG_OVERLAY} 2>/dev/null
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
	mount proc ${DPKG_OVERLAY}/proc -t proc || exit_err "Failed mount proc"
	mount sysfs ${DPKG_OVERLAY}/sys -t sysfs || exit_err "Failed mount sysfs"
	mkdir -p ${DPKG_OVERLAY}/packages || exit_err "Failed mkdir /packages"
	mount --bind ${PKG_DIR} ${DPKG_OVERLAY}/packages || exit_err "Failed mount --bind /packages"
	mount --bind ${CACHE_DIR}/apt ${DPKG_OVERLAY}/var/cache/apt || exit_err "Failed mount --bind /var/cache/apt"
}

build_deb_packages() {
	echo "`date`: Creating debian bootstrap directory: (${LOG_DIR}/bootstrap_chroot.log)"
	make_bootstrapdir "package" >${LOG_DIR}/bootstrap_chroot.log 2>&1
	if [ ! -d "${LOG_DIR}/packages" ] ; then
		mkdir -p ${LOG_DIR}/packages
	fi

	for k in $(jq -r '."sources" | keys[]' ${MANIFEST} 2>/dev/null | tr -s '\n' ' ')
	do
		del_overlayfs
		mk_overlayfs

		NAME=$(jq -r '."sources"['$k']."name"' ${MANIFEST})
		PREBUILD=$(jq -r '."sources"['$k']."prebuildcmd"' ${MANIFEST})
		SUBDIR=$(jq -r '."sources"['$k']."subdir"' ${MANIFEST})
		if [ ! -d "${SOURCES}/${NAME}" ] ; then
			exit_err "Missing sources for ${NAME}, did you forget to run 'make checkout'?"
		fi
		if [ "$PREBUILD" = "null" ] ; then
			unset PREBUILD
		fi

		# Check if we need to rebuild this package
		SOURCEHASH=$(cd ${SOURCES}/${NAME} && git rev-parse --verify HEAD)
		if [ -e "${HASH_DIR}/${NAME}.hash" ] ; then
			if [ "$(cat ${HASH_DIR}/${NAME}.hash)" = "$SOURCEHASH" ] ; then
				if [ $(cd ${SOURCES}/${NAME} >/dev/null && git diff-files --quiet --ignore-submodules >/dev/null ; echo $?) -eq 0 ] ; then
					echo "`date`: Skipping [$NAME] - No changes detected"
					continue
				fi
			fi
		fi


		echo "`date`: Building package [$NAME] (${LOG_DIR}/packages/${NAME}.log)"
		# Cleanup any packages that came before
		clean_previous_packages "$NAME" >${LOG_DIR}/packages/${NAME}.log 2>&1

		# Do the build now
		build_dpkg "$NAME" "$PREBUILD" "$SUBDIR" >>${LOG_DIR}/packages/${NAME}.log 2>&1

		# Save the build hash
		echo "$SOURCEHASH" > ${HASH_DIR}/${NAME}.hash

		del_overlayfs
	done

	del_bootstrapdir
	echo "`date`: Success! Done building packages"
	return 0
}

clean_previous_packages() {
	if [ ! -e "${HASH_DIR}/${1}.pkglist" ]; then
		# Nothing to do
		return 0
	fi
	echo "Removing previously built packages for ${1}:"
	while read pkg
	do
		echo "Removing ${pkg}"
		rm ${PKG_DIR}/${pkg} || echo "Misssing package ${pkg}... Ignored"
	done < ${HASH_DIR}/${1}.pkglist
	rm ${HASH_DIR}/${1}.pkglist
}

build_dpkg() {
	if [ -e "${DPKG_OVERLAY}/packages/Packages.gz" ] ; then
		chroot ${DPKG_OVERLAY} apt update || exit_err "Failed apt update"
	fi
	name="$1"
	prebuild="$2"
	subarg="$3"
	deflags="-us -uc -b"

	# Check if we have a valid sub directory for these sources
	if [ -z "$subarg" -o "$subarg" = "null" ] ; then
		subdir=""
	else
		subdir="/$subarg"
	fi
	srcdir="/dpkg-src$subdir"
	pkgdir="$srcdir/../"

	cp -r ${SOURCES}/${name} ${DPKG_OVERLAY}/dpkg-src || exit_err "Failed to copy sources"

	if [ ! -e "${DPKG_OVERLAY}/$srcdir/debian/control" ] ; then
		exit_err "Missing debian/control file for $name"
	fi

	# Install all the build depends
	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && mk-build-deps --build-dep" || exit_err "Failed mk-build-deps"
	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && apt install -y ./*.deb" || exit_err "Failed install build deps"
	# Check for a prebuild command
	if [ -n "$prebuild" ] ; then
		chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && $prebuild" || exit_err "Failed to prebuild"
	fi

	# Make a programatically generated version for this build
	DATESTAMP=$(date +%Y%m%d%H%M%S)
	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && dch -b -M -v ${DATESTAMP}~truenas+1 --force-distribution --distribution bullseye-truenas-unstable 'Tagged from truenas-build'" || exit_err "Failed dch changelog"

	# Build the package
	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && debuild $deflags" || exit_err "Failed to build package"

	# Move out the resulting packages
	echo "Copying finished packages"

	# Copy and record each built packages for cleanup later
	for pkg in $(ls ${DPKG_OVERLAY}${pkgdir}/*.deb ${DPKG_OVERLAY}${pkgdir}/*.udeb)
	do
		basepkg=$(basename $pkg)
		mv ${DPKG_OVERLAY}${pkgdir}/$basepkg ${PKG_DIR}/ || exit_err "Failed mv of $basepkg"
		echo "$basepkg" >>${HASH_DIR}/${NAME}.pkglist || "Failed recording package name(s)"
	done

	mv ${DPKG_OVERLAY}${pkgdir}/*.deb ${PKG_DIR}/ 2>/dev/null
	mv ${DPKG_OVERLAY}${pkgdir}/*.udeb ${PKG_DIR}/ 2>/dev/null

	# Update the local APT repo
	echo "Building local APT repo Packages.gz..."
	chroot ${DPKG_OVERLAY} /bin/bash -c 'cd /packages && dpkg-scanpackages . /dev/null | gzip -9c > Packages.gz'
}

install_zfs_modules() {
	zfsmodules=$(ls ${PKG_DIR}/zfs-modules* 2>/devnull)
	if [ -z "$zfsmodules" ] ; then
		return
	fi
	zfsmodules=$(basename $zfsmodules)
	zfsmodules=$(echo $zfsmodules | awk -F'-amd64' '{print $1}')
	echo "Installing ZFS Modules: $zfsmodules"
	chroot ${1} /bin/bash -c "cd /packages && apt install -y ./zfs-modules-*" || exit_err "Failed install zfs-modules"
}

build_zfs_modules() {

	chroot ${DPKG_OVERLAY} apt install -y locales || exit_err "Failed apt install locales"
	chroot ${DPKG_OVERLAY} apt install -y linux-image-amd64 || exit_err "Failed apt install linux-image-amd64"
	chroot ${DPKG_OVERLAY} apt install -y debhelper || exit_err "Failed apt install debhelper"

	# Build the .deb package now
	cp scripts/mk-zfs-modules ${DPKG_OVERLAY}/build.sh
	chroot ${DPKG_OVERLAY} sh /build.sh || exit_err "Failed building zfs-modules"

	mv ${DPKG_OVERLAY}/*.deb ${PKG_DIR}/ 2>/dev/null
	mv ${DPKG_OVERLAY}/*.udeb ${PKG_DIR}/ 2>/dev/null
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

		# Check if any overrides have been provided
		unset GHOVERRIDE
		eval "GHOVERRIDE=\$${NAME}_OVERRIDE"

		if [ -n "$TRUENAS_BRANCH_OVERRIDE" ] ; then
			GHBRANCH="$TRUENAS_BRANCH_OVERRIDE"
		elif [ -n "$GHOVERRIDE"  ] ; then
			GHBRANCH="$GHOVERRIDE"
		else
			GHBRANCH="$BRANCH"
		fi

		git clone --depth=1 -b ${GHBRANCH} ${REPO} ${SOURCES}/${NAME} || exit_err "Failed checkout of ${REPO}"
																done
}

install_iso_packages() {
	mount proc ${CHROOT_BASEDIR}/proc -t proc
	mount sysfs ${CHROOT_BASEDIR}/sys -t sysfs
	mkdir -p ${CHROOT_BASEDIR}/packages
	#echo "/dev/disk/by-label/TRUENAS / iso9660 loop 0 0" > ${CHROOT_BASEDIR}/etc/fstab

	mount --bind ${PKG_DIR} ${CHROOT_BASEDIR}/packages || exit_err "Failed mount --bind /packages"
	chroot ${CHROOT_BASEDIR} apt update || exit_err "Failed apt update"

	for package in $(jq -r '."iso-packages" | values[]' $MANIFEST | tr -s '\n' ' ')
	do
		chroot ${CHROOT_BASEDIR} apt install -y $package || exit_err "Failed apt install $package"
	done

	#chroot ${CHROOT_BASEDIR} /bin/bash
	mkdir -p ${CHROOT_BASEDIR}/boot/grub
	cp scripts/grub.cfg ${CHROOT_BASEDIR}/boot/grub/grub.cfg || exit_err "Failed copying grub.cfg"
	umount -f ${CHROOT_BASEDIR}/packages
	umount -f ${CHROOT_BASEDIR}/proc
	umount -f ${CHROOT_BASEDIR}/sys
}

make_iso_file() {
	rm ${RELEASE_DIR}/*.iso
	rm ${RELEASE_DIR}/*.iso.sha256

	# Set default PW to root
	chroot ${CHROOT_BASEDIR} /bin/bash -c 'echo -e "root\nroot" | passwd root'

	# Copy the CD files
	cp conf/cd-files/getty@.service ${CHROOT_BASEDIR}/lib/systemd/system/ || exit_err "Failed copy of getty@"
	cp conf/cd-files/bash_profile ${CHROOT_BASEDIR}/root/.bash_profile || exit_err "Failed copy of bash_profile"

	# Drop to shell for debugging
	#chroot ${CHROOT_BASEDIR} /bin/bash

	# Create the CD assembly dir
	rm -rf ${CD_DIR}
	mkdir -p ${CD_DIR}

	# Prune away the fat
	prune_cd_basedir

	# Lets make squashfs now
	mksquashfs ${CHROOT_BASEDIR} ./tmp/truenas.squashfs -comp xz || exit_err "Failed squashfs"
	mkdir -p ${CD_DIR}/live
	mv ./tmp/truenas.squashfs ${CD_DIR}/live/filesystem.squashfs || exit_err "failed mv squashfs"

	# Copy over boot and kernel before rolling CD
	cp -r ${CHROOT_BASEDIR}/boot ${CD_DIR}/boot || exit_err "Failed copy boot"
	cp -r ${CHROOT_BASEDIR}/init* ${CD_DIR}/ || exit_err "Failed copy initrd"
	cp -r ${CHROOT_BASEDIR}/vmlinuz* ${CD_DIR}/ || exit_err "Failed copy vmlinuz"
	cp ${RELEASE_DIR}/TrueNAS-SCALE.update ${CD_DIR}/TrueNAS-SCALE.update || exit_err "Faile copy .update"

	grub-mkrescue -o ${RELEASE_DIR}/TrueNAS-SCALE.iso ${CD_DIR} \
		|| exit_err "Failed grub-mkrescue"
	sha256sum ${RELEASE_DIR}/TrueNAS-SCALE.iso > ${RELEASE_DIR}/TrueNAS-SCALE.iso.sha256 || exit_err "Failed sha256"
}

prune_cd_basedir() {
	rm -rf ${CHROOT_BASEDIR}/var/cache/apt
}

build_iso() {
	# Check if the update / install rootfs image was created
	if [ ! -e "${RELEASE_DIR}/TrueNAS-SCALE.update" ] ; then
		exit_err "Missing rootfs image. Run 'make update' first."
	fi

	echo "`date`: Bootstrapping CD chroot [ISO] (${LOG_DIR}/cdrom-bootstrap.log)"
	make_bootstrapdir "CD" >${LOG_DIR}/cdrom-bootstrap.log 2>&1
	echo "`date`: Installing packages [ISO] (${LOG_DIR}/cdrom-packages.log)"
	install_iso_packages >${LOG_DIR}/cdrom-packages.log 2>&1
	echo "`date`: Creating ISO file [ISO] (${LOG_DIR}/cdrom-iso.log)"
	make_iso_file >${LOG_DIR}/cdrom-iso.log 2>&1
	del_bootstrapdir
	echo "`date`: Success! CD/USB: ${RELEASE_DIR}/TrueNAS-SCALE.iso"
}

install_rootfs_packages() {
	mount proc ${CHROOT_BASEDIR}/proc -t proc
	mount sysfs ${CHROOT_BASEDIR}/sys -t sysfs
	mkdir -p ${CHROOT_BASEDIR}/packages

	mount --bind ${PKG_DIR} ${CHROOT_BASEDIR}/packages || exit_err "Failed mount --bind /packages"
	chroot ${CHROOT_BASEDIR} apt update || exit_err "Failed apt update"

	for package in $(jq -r '."base-packages" | values[]' $MANIFEST | tr -s '\n' ' ')
	do
		chroot ${CHROOT_BASEDIR} apt install -y $package || exit_err "Failed apt install $package"
	done

	# Copy the default sources.list file
	cp conf/sources.list ${CHROOT_BASEDIR}/etc/apt/sources.list || exit_err "Failed installing sources.list"

	#chroot ${CHROOT_BASEDIR} /bin/bash
	umount -f ${CHROOT_BASEDIR}/packages
	rmdir ${CHROOT_BASEDIR}/packages
	umount -f ${CHROOT_BASEDIR}/proc
	umount -f ${CHROOT_BASEDIR}/sys
}

build_rootfs_image() {
	rm ${RELEASE_DIR}/*.update 2>/dev/null
	rm ${RELEASE_DIR}/*.update.sha256 2>/dev/null
	if [ -d "${UPDATE_DIR}" ] ; then
		rm -rf ${UPDATE_DIR}
	fi
	mkdir -p ${UPDATE_DIR}
	mkdir -p ${RELEASE_DIR}

	# We are going to build a nested squashfs image.
	# Why nested? So that during update we can easily RO mount the outer image
	# to read a MANIFEST and verify signatures of the real rootfs inner image
	#
	# This allows us to verify without ever extracting anything to disk

	# Create the inner image
	mksquashfs ${CHROOT_BASEDIR} ${UPDATE_DIR}/rootfs.squashfs -comp xz || exit_err "Failed squashfs"

	# Build any MANIFEST information
	build_manifest

	# Sign the image (if enabled)
	sign_manifest

	# Create the outer image now
	mksquashfs ${UPDATE_DIR} ${RELEASE_DIR}/TrueNAS-SCALE.update -noD || exit_err "Failed squashfs"
	sha256sum ${RELEASE_DIR}/TrueNAS-SCALE.update > ${RELEASE_DIR}/TrueNAS-SCALE.update.sha256 || exit_err "Failed sha256"
}

sign_manifest() {
	# No signing key? Don't sign the image
	if [ -z "$SIGNING_KEY" ]; then
		return 0
	fi
	if [ -z "$SIGNING_PASSWORD" ] ; then
		return 0
	fi

	echo "$SIGNING_PASSWORD" | gpg -ab --batch --yes --no-use-agent \
		--pinentry-mode loopback \
		--passphrase-fd 0 --default-key ${SIGNING_KEY} \
		--output ${UPDATE_DIR}/MANIFEST.sig \
		--sign ${UPDATE_DIR}/MANIFEST || exit_err "Failed gpg signing with SIGNING_PASSWORD"
}

build_manifest() {
	echo "{ }" > ${UPDATE_DIR}/MANIFEST
	# Add the date to the manifest
	jq -r '. += {"date":"'`date +%s`'"}' \
		${UPDATE_DIR}/MANIFEST > ${UPDATE_DIR}/MANIFEST.new || exit_err "Failed jq"
	mv ${UPDATE_DIR}/MANIFEST.new ${UPDATE_DIR}/MANIFEST

	# Create SHA512 checksum of the inner image
	ROOTCHECKSUM=$(sha512sum ${UPDATE_DIR}/rootfs.squashfs | awk '{print $1}')
	if [ -z "$ROOTCHECKSUM" ] ; then
		exit_err "Failed getting rootfs checksum"
	fi

	# Save checksum to manifest
	jq -r '. += {"checksum":"'$ROOTCHECKSUM'"}' \
		${UPDATE_DIR}/MANIFEST > ${UPDATE_DIR}/MANIFEST.new || exit_err "Failed jq"
	mv ${UPDATE_DIR}/MANIFEST.new ${UPDATE_DIR}/MANIFEST

	# Save the version string
	if [ -n "$TRUENAS_VERSION" ] ; then
		VERSION="$TRUENAS_VERSION"
	else
		VERSION="MASTER-$(date '+%Y%m%d-%H%M%S')"
	fi
	jq -r '. += {"version":"'$VERSION'"}' \
		${UPDATE_DIR}/MANIFEST > ${UPDATE_DIR}/MANIFEST.new || exit_err "Failed jq"
	mv ${UPDATE_DIR}/MANIFEST.new ${UPDATE_DIR}/MANIFEST

}

build_update_image() {
	echo "`date`: Bootstrapping TrueNAS rootfs [UPDATE] (${LOG_DIR}/rootfs-bootstrap.log)"
	make_bootstrapdir "package" >${LOG_DIR}/rootfs-bootstrap.log 2>&1
	echo "`date`: Installing TrueNAS rootfs packages [UPDATE] (${LOG_DIR}/rootfs-packages.log)"
	install_rootfs_packages >${LOG_DIR}/rootfs-packages.log 2>&1
	echo "`date`: Building TrueNAS rootfs image [UPDATE] (${LOG_DIR}/rootfs-image.log)"
	build_rootfs_image >${LOG_DIR}/rootfs-image.log 2>&1
	del_bootstrapdir
	echo "`date`: Success! Update image created at: ${RELEASE_DIR}/TrueNAS-SCALE.update"
}

# Check that host has all the prereq tools installed
preflight_check

case $1 in
	checkout) checkout_sources ;;
	clean) cleanup ;;
	iso) build_iso ;;
	packages) build_deb_packages ;;
	update) build_update_image ;;
	*) exit_err "Invalid build option!" ;;
esac

exit 0
