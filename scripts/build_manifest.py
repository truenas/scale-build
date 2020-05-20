# -*- coding=utf-8 -*-
from datetime import datetime
import glob
import json
import os
import shutil
import subprocess
import sys

if __name__ == "__main__":
    output, rootfs, version = sys.argv[1:]

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
            "checksums": checksums,
            "kernel_version": glob.glob(os.path.join(rootfs, "boot/vmlinuz-*"))[0].split("/")[-1][len("vmlinuz-"):],
        }))
