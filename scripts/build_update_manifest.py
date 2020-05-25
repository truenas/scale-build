# -*- coding=utf-8 -*-
import json
import os
import sys

if __name__ == "__main__":
    output, release_file = sys.argv[1:]

    with open(os.path.join(output, "manifest.json")) as f:
        manifest = json.load(f)

    with open(f"{release_file}.sha256") as f:
        checksum = f.read().split()[0]

    with open(os.path.join(os.path.dirname(release_file), "manifest.json"), "w") as f:
        json.dump({
            "filename": os.path.basename(release_file),
            "version": manifest["version"],
            "date": manifest["date"],
            "changelog": "",
            "checksum": checksum,
        }, f)
