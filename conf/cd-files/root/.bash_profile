#!/bin/sh

if [ -f /cdrom/TrueNAS-SCALE.update ];
then
    until /usr/bin/python3 -m truenas_installer; do true; done
else
    read -p "No installation media found. Press enter to reboot..." answer
    reboot
fi
