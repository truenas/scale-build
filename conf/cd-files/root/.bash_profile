#!/bin/sh

if -f /cdrom/TrueNAS-SCALE.update
then
    until /sbin/truenas-install; do true; done
else
    read -p "No installation media found. Press enter to reboot..." answer
    reboot
fi
