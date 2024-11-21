import errno
import json
import logging
import os
import shutil

import requests

from .exceptions import CallError
from .image.bootstrap import clean_mounts
from .image.manifest import update_file_path
from .image.utils import run_in_chroot
from .utils.paths import CD_DIR, CHROOT_BASEDIR, CHROOT_OVERLAY, RELEASE_DIR
from .utils.run import run

logger = logging.getLogger(__name__)

BINARIES = ("apt", "apt-config", "apt-key", "dpkg")
TEMPORARY_PACKAGES = ["gcc", "make", "pkg-config"]
PERMANENT_PACKAGES = ["libvulkan1", "nvidia-container-toolkit", "vulkan-validationlayers"]
HEADERS = {"User-Agent": "curl/7.88.1"}
EXTENSIONS_DIR = os.path.join(RELEASE_DIR, "extensions")


def build_extensions():
    clean_mounts()

    if not os.path.exists(update_file_path()):
        raise CallError("Missing rootfs image. Run `make update` first.")

    if os.path.exists(CHROOT_BASEDIR):
        shutil.rmtree(CHROOT_BASEDIR)
    if os.path.exists(CHROOT_OVERLAY):
        shutil.rmtree(CHROOT_OVERLAY)

    run(["mount", "-o", "loop", update_file_path(), CD_DIR])
    try:
        run(["unsquashfs", "-dest", CHROOT_BASEDIR, os.path.join(CD_DIR, "rootfs.squashfs")])
        run(["unsquashfs", "-dest", CHROOT_OVERLAY, os.path.join(CD_DIR, "rootfs.squashfs")])
        with open(f"{CD_DIR}/manifest.json") as f:
            manifest = json.load(f)
    finally:
        run(["umount", CD_DIR])

    run(["mount", "proc", os.path.join(CHROOT_BASEDIR, "proc"), "-t", "proc"])
    run(["mount", "sysfs", os.path.join(CHROOT_BASEDIR, "sys"), "-t", "sysfs"])
    try:
        shutil.copyfile("/etc/resolv.conf", f"{CHROOT_BASEDIR}/etc/resolv.conf")

        for binary in BINARIES:
            os.unlink(os.path.join(CHROOT_BASEDIR, f"usr/local/bin/{binary}"))
            os.chmod(os.path.join(CHROOT_BASEDIR, f"usr/bin/{binary}"), 0o755)

        add_nvidia_repository()
        run_in_chroot(["apt", "update"])
        run_in_chroot(["apt", "-y", "install"] + TEMPORARY_PACKAGES + PERMANENT_PACKAGES)

        install_nvidia_driver(manifest["kernel_version"])

        run_in_chroot(["apt", "-y", "remove"] + TEMPORARY_PACKAGES)
        run_in_chroot(["apt", "-y", "autoremove"])
    finally:
        run(["umount", os.path.join(CHROOT_BASEDIR, "sys")])
        run(["umount", os.path.join(CHROOT_BASEDIR, "proc")])

    if os.path.exists(EXTENSIONS_DIR):
        shutil.rmtree(EXTENSIONS_DIR)
    build_extension("nvidia")


def add_nvidia_repository():
    r = requests.get("https://nvidia.github.io/libnvidia-container/gpgkey")
    r.raise_for_status()

    with open(f"{CHROOT_BASEDIR}/key.gpg", "w") as f:
        f.write(r.text)

    run_in_chroot(["gpg", "-o", "/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg", "--dearmor", "/key.gpg"])

    with open(f"{CHROOT_BASEDIR}/etc/apt/sources.list.d/nvidia-container-toolkit.list", "w") as f:
        f.write("deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] "
                "https://nvidia.github.io/libnvidia-container/stable/deb/$(ARCH) /")


def download_nvidia_driver():
    prefix = "https://download.nvidia.com/XFree86/Linux-x86_64"

    r = requests.get(f"{prefix}/latest.txt", headers=HEADERS, timeout=10)
    r.raise_for_status()
    version = r.text.split()[0]
    filename = f"NVIDIA-Linux-x86_64-{version}-no-compat32.run"
    result = f"{CHROOT_BASEDIR}/{filename}"

    with requests.get(f"{prefix}/{version}/{filename}", headers=HEADERS, stream=True, timeout=10) as r:
        r.raise_for_status()
        with open(result, "wb") as f:
            shutil.copyfileobj(r.raw, f)

    os.chmod(result, 0o755)
    return result


def install_nvidia_driver(kernel_version):
    driver = download_nvidia_driver()

    run_in_chroot([f"/{os.path.basename(driver)}", "--skip-module-load", "--silent", f"--kernel-name={kernel_version}",
                   "--allow-installation-with-running-driver", "--no-rebuild-initramfs"])

    os.unlink(driver)


def build_extension(name):
    changed_files = [
        os.path.relpath(filename, CHROOT_BASEDIR)
        for filename in map(
            lambda filename: os.path.join(os.getcwd(), filename),
            run(
                ["rsync", "-avn", "--out-format=%f", f"{CHROOT_BASEDIR}/", f"{CHROOT_OVERLAY}/"],
                log=False,
            ).stdout.split("\n")
        )
        if os.path.abspath(filename).startswith(os.path.abspath(CHROOT_BASEDIR))
    ]

    sysext_files = [f for f in changed_files if f.startswith("usr/") and not (f.startswith("usr/src/"))]

    for root, dirs, files in os.walk(CHROOT_BASEDIR, topdown=False):
        for f in files:
            path = os.path.relpath(os.path.abspath(os.path.join(root, f)), CHROOT_BASEDIR)
            if path not in sysext_files:
                os.unlink(os.path.join(root, f))

        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except NotADirectoryError:
                os.unlink(os.path.join(root, d))  # It's a symlink
            except OSError as e:
                if e.errno == errno.ENOTEMPTY:
                    pass
                else:
                    raise

    os.makedirs(f"{CHROOT_BASEDIR}/usr/lib/extension-release.d", exist_ok=True)
    with open(f"{CHROOT_BASEDIR}/usr/lib/extension-release.d/extension-release.{name}", "w") as f:
        f.write("ID=_any\n")

    os.makedirs(EXTENSIONS_DIR, exist_ok=True)
    path = os.path.join(EXTENSIONS_DIR, f"{name}.raw")
    run(["mksquashfs", CHROOT_BASEDIR, path, "-comp", "xz"])
    with open(f"{path}.sha256", "w") as f:
        f.write(run(["sha256sum", path], log=False).stdout.split()[0])
