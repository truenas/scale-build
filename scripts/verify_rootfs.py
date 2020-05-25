# -*- coding=utf-8 -*-
import subprocess
import sys

if __name__ == "__main__":
    rootfs, = sys.argv[1:]

    for file in ["group", "passwd"]:
        cmd = [
            "diff", "-u", f"{rootfs}/etc/{file}",
            f"{rootfs}/usr/lib/python3/dist-packages/middlewared/assets/account/builtin/linux/{file}"
        ]
        run = subprocess.run(cmd, stdout=subprocess.PIPE, encoding="utf-8", errors="ignore")
        if run.returncode not in [0, 1]:
            raise subprocess.CalledProcessError(run.returncode, cmd, run.stdout)

        diff = "\n".join(run.stdout.split("\n")[3:])
        if any(line.startswith("-") for line in diff.split("\n")):
            sys.stderr.write(f"Invalid {file!r} assest:\n{diff}")
            sys.exit(1)
