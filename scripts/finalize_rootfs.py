# -*- coding=utf-8 -*-
import os
import shutil
import sys

if __name__ == "__main__":
    rootfs, = sys.argv[1:]

    os.makedirs(f"{rootfs}/conf/base/etc", exist_ok=True)
    for file in ["group", "passwd"]:
        original = f"{rootfs}/etc/{file}"
        shutil.copy(f"{rootfs}/etc/{file}", f"{rootfs}/conf/base/etc/{file}")
