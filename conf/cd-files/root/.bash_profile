#!/bin/sh

# Mount the local CD/USB image to access install file
mkdir /cdrom
mount /dev/disk/by-label/ISOIMAGE /cdrom

until /sbin/truenas-install; do true; done
