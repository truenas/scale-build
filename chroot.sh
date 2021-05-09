#!/bin/sh

umount -f ./tmp/b/proc
umount -f ./tmp/b/sys
umount -f ./tmp/b/packages
rm -rf ./tmp/b
mkdir ./tmp/b
unsquashfs -f -d ./tmp/b ./tmp/cache/basechroot-package.squashfs
mkdir -p ./tmp/b/proc ./tmp/b/sys ./tmp/b/packages
mount proc ./tmp/b/proc -t proc
mount sysfs ./tmp/b/sys -t sysfs
mount --bind ./tmp/pkgdir ./tmp/b/packages

echo "Setup basechroot directory for chroot successfully"

chroot ./tmp/b bash

echo "Cleaning up mounts"
umount -f ./tmp/b/proc
umount -f ./tmp/b/sys
umount -f ./tmp/b/packages
