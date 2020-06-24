# -*- coding=utf-8 -*-
import os
import shutil
import sys

if __name__ == "__main__":
    rootfs, = sys.argv[1:]

    for file in ["group", "passwd", "syslog-ng/syslog-ng.conf"]:
        original = f"{rootfs}/etc/{file}"
        destination = f"{rootfs}/conf/base/etc/{file}"
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy(f"{rootfs}/etc/{file}", destination)
