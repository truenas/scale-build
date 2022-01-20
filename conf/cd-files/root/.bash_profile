#!/bin/sh

# Inspired by https://salsa.debian.org/live-team/live-boot/-/blob/master/components/9990-misc-helpers.sh

mountpoint=/cdrom

is_live_path()
{
    FILE="${1}/TrueNAS-SCALE.update"
    if [ -f "${FILE}" ]
    then
        return 0
    fi
    return 1
}

is_nice_device ()
{
    sysfs_path="${1#/sys}"

    if udevadm info --query=all --path="${sysfs_path}" | egrep -q "DEVTYPE=disk"
    then
        return 0
    elif echo "${sysfs_path}" | grep -q '^/block/vd[a-z]$'
    then
        return 0
    elif echo ${sysfs_path} | grep -q "^/block/dm-"
    then
        return 0
    elif echo ${sysfs_path} | grep -q "^/block/mtdblock"
    then
        return 0
    fi

    return 1
}

check_dev ()
{
    local force fix
    sysdev="${1}"
    devname="${2}"
    skip_uuid_check="${3}"

    if [ -z "${devname}" ]
    then
        devname=$(sys2dev "${sysdev}")
    fi

    mount "${devname}" $mountpoint || return 1

    if is_live_path $mountpoint
    then
        echo $mountpoint
        return 0
    else
        umount $mountpoint
    fi

    return 1
}

find_livefs ()
{
    # scan of block devices to find the installation media
    # prefer removable devices over non-removable devices, so scan them first
    devices_to_scan="$(removable_dev 'sys') $(non_removable_dev 'sys')"

    for sysblock in $devices_to_scan
    do
        devname=$(sys2dev "${sysblock}")
        [ -e "$devname" ] || continue

        if /lib/udev/cdrom_id ${devname} > /dev/null
        then
            if check_dev "null" "${devname}"
            then
                return 0
            fi
        elif is_nice_device "${sysblock}"
        then
            for dev in $(subdevices "${sysblock}")
            do
                if check_dev "${dev}"
                then
                    return 0
                fi
            done
        fi
    done

    return 1
}

sys2dev ()
{
    sysdev=${1#/sys}
    echo "/dev/$(udevadm info -q name -p ${sysdev} 2>/dev/null|| echo ${sysdev##*/})"
}

subdevices ()
{
    sysblock=${1}
    r=""

    for dev in "${sysblock}"/* "${sysblock}"
    do
        if [ -e "${dev}/dev" ]
        then
            r="${r} ${dev}"
        fi
    done

    echo ${r}
}

removable_dev ()
{
    output_format="${1}"
    want_usb="${2}"
    ret=

    for sysblock in $(echo /sys/block/* | tr ' ' '\n' | grep -vE "/(loop|ram|dm-|fd)")
    do
        if [ ! -d "${sysblock}" ]; then
            continue
        fi

        dev_ok=
        if [ "$(cat ${sysblock}/removable)" = "1" ]
        then
            if [ -z "${want_usb}" ]
            then
                dev_ok="true"
            else
                if readlink ${sysblock} | grep -q usb
                then
                    dev_ok="true"
                fi
            fi
        fi

        if [ "${dev_ok}" = "true" ]
        then
            case "${output_format}" in
                sys)
                    ret="${ret} ${sysblock}"
                    ;;
                *)
                    devname=$(sys2dev "${sysblock}")
                    ret="${ret} ${devname}"
                    ;;
            esac
        fi
    done

    echo "${ret}"
}

non_removable_dev ()
{
    output_format="${1}"
    ret=

    for sysblock in $(echo /sys/block/* | tr ' ' '\n' | grep -vE "/(loop|ram|dm-|fd)")
    do
        if [ ! -d "${sysblock}" ]; then
            continue
        fi

        if [ "$(cat ${sysblock}/removable)" = "0" ]
        then
            case "${output_format}" in
                sys)
                    ret="${ret} ${sysblock}"
                    ;;
                *)
                    devname=$(sys2dev "${sysblock}")
                    ret="${ret} ${devname}"
                    ;;
            esac
        fi
    done

    echo "${ret}"
}

if find_livefs
then
    until /sbin/truenas-install; do true; done
else
    read -p "No installation media found. Press enter to reboot..." answer
    reboot
fi
