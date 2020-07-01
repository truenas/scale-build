# -*- coding=utf-8 -*-
from datetime import datetime
import glob
import json
import os
import shutil
import subprocess
import sys

if __name__ == "__main__":
    output, rootfs = sys.argv[1:]

    with open(os.path.join(rootfs, "etc/version")) as f:
        version = f.read().strip()

    size = int(int(subprocess.run(
        ["du", "--block-size", "1", "-d", "0", "-x", rootfs],
        check=True, stdout=subprocess.PIPE, encoding="utf-8", errors="ignore",
    ).stdout.split()[0]) * 1.1)

    shutil.copytree(
        os.path.join(os.path.dirname(__file__), "../truenas_install"),
        os.path.join(output, "truenas_install"),
    )

    checksums = {}
    for root, dirs, files in os.walk(output):
        for file in files:
            abspath = os.path.join(root, file)
            checksums[os.path.relpath(abspath, output)] = subprocess.run(
                ["sha1sum", abspath],
                check=True, stdout=subprocess.PIPE, encoding="utf-8", errors="ignore",
            ).stdout.split()[0]

    with open(os.path.join(output, "manifest.json"), "w") as f:
        f.write(json.dumps({
            "date": datetime.utcnow().isoformat(),
            "version": version,
            "size": size,
            "checksums": checksums,
            "kernel_version": glob.glob(os.path.join(rootfs, "boot/vmlinuz-*"))[0].split("/")[-1][len("vmlinuz-"):],
        }))
