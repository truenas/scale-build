#!/bin/sh

CODENAME="Angelfish"

if [ -n "$TRUENAS_TRAIN" ] ; then
  TRAIN="$TRUENAS_TRAIN"
else
  TRAIN="TrueNAS-SCALE-${CODENAME}-Nightlies"
fi

BUILDTIME=$(date +%s)

if [ -n "$TRUENAS_VERSION" ] ; then
  VERSION="$TRUENAS_VERSION"
else
  VERSION="$(date -d@$BUILDTIME +%y.%m)-MASTER-$(date -d@$BUILDTIME '+%Y%m%d-%H%M%S')"
fi

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

# When loggin in as 'su root' the /sbin dirs get dropped out of PATH
export PATH="${PATH}:/sbin:/usr/sbin:/usr/local/sbin"

# Makes some perl scripts happy during package builds
export LC_ALL="C"
export LANG="C"

# Passed along to WAF for parallel build
export DEB_BUILD_OPTIONS="parallel=$(nproc)"

# Never go full interactive on any packages
export DEBIAN_FRONTEND="noninteractive"

# Source helper functions
. scripts/functions.sh

apt_preferences() {
	cat << EOF
Package: *
Pin: release n=bullseye
Pin-Priority: 900

Package: python3-*
Pin: origin ""
Pin-Priority: 950

Package: *truenas-samba*
Pin: version 4.13.*
Pin-Priority: 950

Package: *zfs*
Pin: version 2.0.*
Pin-Priority: 1000
EOF
}

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
	mount -t tmpfs -o size=8G tmpfs ${TMPFS}

	# Check if we should invalidate the base cache
	validate_basecache "$CACHENAME"

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

	# Do the fresh bootstrap
	debootstrap ${DEOPTS} --keyring /etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg \
		bullseye ${CHROOT_BASEDIR} $aptrepo \
		|| exit_err "Failed debootstrap"
	create_basehash "$CACHENAME"

	# Mount to prep build
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

	# Set bullseye repo as the priority
	# TODO - This should be moved to manifest later
	apt_preferences >${CHROOT_BASEDIR}/etc/apt/preferences

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

	save_build_cache "${CACHENAME}"

	return 0
}

remove_basecache() {
	echo "Removing base chroot cache for ${1}"
	rm ${CACHE_DIR}/basechroot-${1}.squashfs 2>/dev/null
	rm ${CACHE_DIR}/basechroot-${1}.squashfs.hash 2>/dev/null
}

create_basehash() {
	cache="$1"
	get_all_repo_hash
	echo "${ALLREPOHASH}" > ${CACHE_DIR}/basechroot-${cache}.squashfs.hash
}

get_repo_hash() {
	wget -q -O tmp/.cachecheck ${1}/dists/${2}/Release
	if [ $? -ne 0 ] ; then
		rm tmp/.cachecheck 2>/dev/null
		return 1
	fi
	unset REPOHASH
	REPOHASH=$(cat tmp/.cachecheck | sha256sum | awk '{print $1}')
	rm tmp/.cachecheck 2>/dev/null
	export REPOHASH
}

get_all_repo_hash() {
	# Start by validating the main APT repo
	local repo=$(jq -r '."apt-repos"."url"' $MANIFEST)
	local dist=$(jq -r '."apt-repos"."distribution"' $MANIFEST)

	# Get the hash of remote repo, otherwise remove cache
	get_repo_hash "${repo}" "${dist}"
	ALLREPOHASH="${REPOHASH}"

	# Get the hash of extra repos
	for k in $(jq -r '."apt-repos"."additional" | keys[]' ${MANIFEST} 2>/dev/null | tr -s '\n' ' ')
	do
		local aptrepo=$(jq -r '."apt-repos"."additional"['$k']."url"' $MANIFEST)
		local aptdist=$(jq -r '."apt-repos"."additional"['$k']."distribution"' $MANIFEST)
		get_repo_hash "${aptrepo}" "${aptdist}"
		ALLREPOHASH="${ALLREPOHASH}${REPOHASH}"
	done

	# Hash the apt preferences, too
	ALLREPOHASH="${ALLREPOHASH}$(apt_preferences | sha256sum | awk '{print $1}')"

	export ALLREPOHASH
}

validate_basecache() {
	cache="$1"

	get_all_repo_hash

	# No hash file? Lets remove to be safe
	if [ ! -e "${CACHE_DIR}/basechroot-${cache}.squashfs.hash" ]; then
		remove_basecache "${cache}"
		return 1
	fi
	# Has the cache changed?
	if [ "${ALLREPOHASH}" != "$(cat ${CACHE_DIR}/basechroot-${cache}.squashfs.hash)" ] ; then
		echo "Upstream repo changed! Removing squashfs cache to re-create."
		remove_basecache "${cache}"
		return 1
	fi

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
	rm ${LOG_DIR}/bootstrap* 2>/dev/null
	echo "`date`: Creating debian bootstrap directory: (${LOG_DIR}/bootstrap_chroot.log)"
	make_bootstrapdir "package" >${LOG_DIR}/bootstrap_chroot.log 2>&1

	if [ ! -d "${LOG_DIR}/packages" ] ; then
		mkdir -p ${LOG_DIR}/packages
	fi
	rm ${LOG_DIR}/packages/* 2>/dev/null

	for k in $(jq -r '."sources" | keys[]' ${MANIFEST} 2>/dev/null | tr -s '\n' ' ')
	do
		del_overlayfs
		mk_overlayfs

		# Clear variables we are going to load from MANIFEST
		unset GENERATE_VERSION SUBDIR PREBUILD PREDEP NAME

		NAME=$(jq -r '."sources"['$k']."name"' ${MANIFEST})
		PREDEP=$(jq -r '."sources"['$k']."predepscmd"' ${MANIFEST})
		PREBUILD=$(jq -r '."sources"['$k']."prebuildcmd"' ${MANIFEST})
		SUBDIR=$(jq -r '."sources"['$k']."subdir"' ${MANIFEST})
		GENERATE_VERSION=$(jq -r '."sources"['$k']."generate_version"' ${MANIFEST})
		if [ ! -d "${SOURCES}/${NAME}" ] ; then
			exit_err "Missing sources for ${NAME}, did you forget to run 'make checkout'?"
		fi
		if [ "$PREBUILD" = "null" ] ; then
			unset PREBUILD
		fi

		# Check if we need to rebuild this package
		SOURCEHASH=$(cd ${SOURCES}/${NAME} && git rev-parse --verify HEAD)
		if [ $NAME != truenas -a -e "${HASH_DIR}/${NAME}.hash" ] ; then
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
		build_dpkg "$NAME" "$PREDEP" "$PREBUILD" "$SUBDIR" "$GENERATE_VERSION" >>${LOG_DIR}/packages/${NAME}.log 2>&1

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
	predep="$2"
	prebuild="$3"
	subarg="$4"
	generate_version="$5"
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

	# Check for a predep command
	if [ -n "$predep" -a "$predep" != "null" ] ; then
		echo "Running predepcmd: $predep"
		chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && $predep" || exit_err "Failed to execute predep command"
	fi

	if [ ! -e "${DPKG_OVERLAY}/$srcdir/debian/control" ] ; then
		exit_err "Missing debian/control file for $name"
	fi

	# Install all the build depends
	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && mk-build-deps --build-dep" || exit_err "Failed mk-build-deps"
	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && apt install -y ./*.deb" || exit_err "Failed install build deps"
	if [ $name = truenas ] ; then
		mkdir ${DPKG_OVERLAY}${srcdir}/data
		echo '{"buildtime": '$BUILDTIME', "train": "'$TRAIN'", "version": "'$VERSION'"}' > ${DPKG_OVERLAY}${srcdir}/data/manifest.json
		mkdir ${DPKG_OVERLAY}${srcdir}/etc
		echo $VERSION > ${DPKG_OVERLAY}${srcdir}/etc/version
	fi
	# Check for a prebuild command
	if [ -n "$prebuild" ] ; then
		echo "Running prebuildcmd: $prebuild"
		chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && $prebuild" || exit_err "Failed to prebuild"
	fi

	# Make a programatically generated version for this build
	if [ "$generate_version" != "false" ] ; then
		DATESTAMP=$(date +%Y%m%d%H%M%S)
		chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && dch -b -M -v ${DATESTAMP}~truenas+1 --force-distribution --distribution bullseye-truenas-unstable 'Tagged from truenas-build'" || exit_err "Failed dch changelog"
	else
		chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && dch -b -M --force-distribution --distribution bullseye-truenas-unstable 'Tagged from truenas-build'" || exit_err "Failed dch changelog"
	fi

	# Build the package
	chroot ${DPKG_OVERLAY} /bin/bash -c "cd $srcdir && debuild $deflags" || exit_err "Failed to build package"

	# Move out the resulting packages
	echo "Copying finished packages"

	# Copy and record each built packages for cleanup later
	for pkg in $(ls ${DPKG_OVERLAY}${pkgdir}/*.deb ${DPKG_OVERLAY}${pkgdir}/*.udeb 2>/dev/null)
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

checkout_sources() {
	if [ ! -d "$SOURCES" ] ; then
		mkdir -p ${SOURCES}
	fi

	GITREMOTE=$(git remote get-url origin)
	GITSHA=$(git rev-parse --short HEAD)
	echo "${GITREMOTE} ${GITSHA}" > ${LOG_DIR}/GITMANIFEST


	echo "`date`: Starting checkout of source"
	for k in $(jq -r '."sources" | keys[]' ${MANIFEST} 2>/dev/null | tr -s '\n' ' ')
	do
		#eval "CHECK=\$$k"
		NAME=$(jq -r '."sources"['$k']."name"' ${MANIFEST})
		REPO=$(jq -r '."sources"['$k']."repo"' ${MANIFEST})
		BRANCH=$(jq -r '."sources"['$k']."branch"' ${MANIFEST})
		if [ -z "$NAME" ] ; then exit_err "Invalid NAME: $NAME" ; fi
		if [ -z "$REPO" ] ; then exit_err "Invalid REPO: $REPO" ; fi
		if [ -z "$BRANCH" ] ; then exit_err "Invalid BRANCH: $BRANCH" ; fi

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

		# TRY_BRANCH_OVERRIDE is a special use-case. It allows setting a branch name to be used
		# during the checkout phase, only if it exists on the remote.
		#
		# This is useful for PR builds and testing where you want to use defaults for most repos
		# but need to test building of a series of repos with the same experimental branch
		#
		if [ -n "${TRY_BRANCH_OVERRIDE}" ] ; then
			git ls-remote ${REPO} | grep -q -E "/${TRY_BRANCH_OVERRIDE}\$"
			if [ $? -eq 0 ] ; then
				echo "TRY_BRANCH_OVERRIDE: Using remote branch ${TRY_BRANCH_OVERRIDE} on ${REPO}"
				GHBRANCH="${TRY_BRANCH_OVERRIDE}"
			fi
		fi

		# Check if we can do a git pull, or need to checkout fresh
		if [ -d ${SOURCES}/${NAME} ] ; then
			cbranch=$(cd ${SOURCES}/${NAME} && git branch | awk '{print $2}')
			corigin=$(cd ${SOURCES}/${NAME} && git remote get-url origin)
			if [ "$cbranch" != "$GHBRANCH" -o "$corigin" != "${REPO}" ] ; then
				# Branch or repo name changed in manifest
				checkout_git_repo "${NAME}" "${GHBRANCH}" "${REPO}"
			else
				update_git_repo "${NAME}" "${GHBRANCH}" "${REPO}"
			fi
		else
			checkout_git_repo "${NAME}" "${GHBRANCH}" "${REPO}"
		fi

		# Update the GITMANIFEST file
		GITREMOTE=$(cd ${SOURCES}/${NAME} && git remote get-url origin)
		GITSHA=$(cd ${SOURCES}/${NAME} && git rev-parse --short HEAD)
		echo "${GITREMOTE} ${GITSHA}" >> ${LOG_DIR}/GITMANIFEST

	done
	echo "`date`: Finished checkout of source"
}

update_git_repo() {
	NAME="$1"
	GHBRANCH="$2"
	REPO="$3"
	echo "`date`: Updating git repo [${NAME}] (${LOG_DIR}/git-checkout.log)"
	(cd ${SOURCES}/${NAME} && git fetch --unshallow) >${LOG_DIR}/git-checkout.log 2>&1
	(cd ${SOURCES}/${NAME} && git fetch origin ${GHBRANCH}) >${LOG_DIR}/git-checkout.log 2>&1 || exit_err "Failed git fetch"
	(cd ${SOURCES}/${NAME} && git reset --hard origin/${GHBRANCH}) >${LOG_DIR}/git-checkout.log 2>&1 || exit_err "Failed git reset"
}

checkout_git_repo() {
	NAME="$1"
	GHBRANCH="$2"
	REPO="$3"
	echo "`date`: Checking out git repo [${NAME}] (${LOG_DIR}/git-checkout.log)"

	# Cleanup old dir, if it exists
	if [ -d "${SOURCES}/${NAME}" ] ; then
		rm -r ${SOURCES}/${NAME}
	fi
	git clone --depth=1 -b ${GHBRANCH} ${REPO} ${SOURCES}/${NAME} \
		>${LOG_DIR}/git-checkout.log 2>&1 || exit_err "Failed checkout of ${REPO}"
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

	# Create /etc/version
	echo "${VERSION}" > ${CHROOT_BASEDIR}/etc/version

	# Copy the CD files
	cp conf/cd-files/getty@.service ${CHROOT_BASEDIR}/lib/systemd/system/ || exit_err "Failed copy of getty@"
	cp conf/cd-files/serial-getty@.service ${CHROOT_BASEDIR}/lib/systemd/system/ || exit_err "Failed copy of serial-getty@"
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

	grub-mkrescue -o ${RELEASE_DIR}/TrueNAS-SCALE-${VERSION}.iso ${CD_DIR} \
		|| exit_err "Failed grub-mkrescue"
	sha256sum ${RELEASE_DIR}/TrueNAS-SCALE-${VERSION}.iso > ${RELEASE_DIR}/TrueNAS-SCALE-${VERSION}.iso.sha256 || exit_err "Failed sha256"
}

prune_cd_basedir() {
	rm -rf ${CHROOT_BASEDIR}/var/cache/apt
	rm -rf ${CHROOT_BASEDIR}/var/lib/apt
	rm -rf ${CHROOT_BASEDIR}/usr/share/doc
	rm -rf ${CHROOT_BASEDIR}/usr/share/man
	rm -rf ${CHROOT_BASEDIR}/lib/modules/*-amd64/kernel/sound
}

build_iso() {
	rm ${LOG_DIR}/cdrom* 2>/dev/null
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
	echo "`date`: Success! CD/USB: ${RELEASE_DIR}/TrueNAS-SCALE-${VERSION}.iso"
}

install_rootfs_packages() {
	mount proc ${CHROOT_BASEDIR}/proc -t proc
	mount sysfs ${CHROOT_BASEDIR}/sys -t sysfs
	mkdir -p ${CHROOT_BASEDIR}/packages

	mount --bind ${PKG_DIR} ${CHROOT_BASEDIR}/packages || exit_err "Failed mount --bind /packages"
	chroot ${CHROOT_BASEDIR} apt update || exit_err "Failed apt update"

	for package in $(jq -r '."base-packages" | values[]' $MANIFEST | tr -s '\n' ' ')
	do
		echo "`date`: apt installing package [${package}]"
		chroot ${CHROOT_BASEDIR} apt install -V -y $package
		if [ $? -ne 0 ] ; then
			exit_err "Failed apt install $package"
		fi
	done

	# Do any custom steps for setting up the rootfs image
	custom_rootfs_setup

	# Do any pruning of rootfs
	clean_rootfs

	# Copy the default sources.list file
	cp conf/sources.list ${CHROOT_BASEDIR}/etc/apt/sources.list || exit_err "Failed installing sources.list"

	#chroot ${CHROOT_BASEDIR} /bin/bash
	umount -f ${CHROOT_BASEDIR}/packages
	rmdir ${CHROOT_BASEDIR}/packages
	umount -f ${CHROOT_BASEDIR}/proc
	umount -f ${CHROOT_BASEDIR}/sys
}

clean_rootfs() {

	# Remove packages from our build manifest
	for package in $(jq -r '."base-prune" | values[]' $MANIFEST | tr -s '\n' ' ')
	do
		chroot ${CHROOT_BASEDIR} apt remove -y $package || exit_err "Failed apt remove $package"
	done

	# Remove any temp build depends
	chroot ${CHROOT_BASEDIR} /bin/bash -c 'apt autoremove -y' || exit_err "Failed apt autoremove"

	# We install the nvidia-kernel-dkms package which causes a modprobe file to be written
	# (i.e /etc/modprobe.d/nvidia.conf). This file tries to modprobe all the associated
	# nvidia drivers at boot whether or not your system has an nvidia card installed.
	# For all truenas certified and truenas enterprise hardware, we do not include nvidia GPUS.
	# So to prevent a bunch of systemd "Failed" messages to be barfed to the console during boot,
	# we remove this file because the linux kernel dynamically loads the modules based on whether
	# or not you have the actual hardware installed in the system.
	NVIDIA_CONF="${CHROOT_BASEDIR}/etc/modprobe.d/nvidia.conf"
	if [ -e "${NVIDIA_CONF}" ] ; then
		rm -f ${NVIDIA_CONF} 2>&1
	fi

	rm -rf ${CHROOT_BASEDIR}/usr/share/doc/*
	rm -rf ${CHROOT_BASEDIR}/var/cache/apt/*
	rm -rf ${CHROOT_BASEDIR}/var/lib/apt/lists/*
}


custom_rootfs_setup() {

	# Any kind of custom mangling of the built rootfs image can exist here
	#

	# Install nomad binary, since no sane debian package exists yet
	NOMADVER="0.11.1"
	if [ ! -e "${CACHE_DIR}/nomad_${NOMADVER}.zip" ] ; then
		wget -O ${CACHE_DIR}/nomad_${NOMADVER}.zip \
			https://releases.hashicorp.com/nomad/${NOMADVER}/nomad_${NOMADVER}_linux_amd64.zip \
			|| exit_err "Failed wget of nomad"
	fi
	unzip -d ${CHROOT_BASEDIR}/usr/bin ${CACHE_DIR}/nomad_${NOMADVER}.zip || exit_err "Failed unzip of nomad"
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
	python3 scripts/build_update_manifest.py "$UPDATE_DIR" "${RELEASE_DIR}/TrueNAS-SCALE.update"
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
	python3 scripts/build_manifest.py "$UPDATE_DIR" "$CHROOT_BASEDIR"
}

build_update_image() {
	rm ${LOG_DIR}/rootfs* 2>/dev/null
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
