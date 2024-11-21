import errno
import logging
import os
import shutil

import requests

from .image.utils import run_in_chroot
from .utils.kernel import get_kernel_version
from .utils.manifest import get_manifest
from .utils.paths import TMPFS, PKG_DIR
from .utils.run import run

logger = logging.getLogger(__name__)

BINARIES = ("apt", "apt-config", "apt-key", "dpkg")
TEMPORARY_PACKAGES = ["gcc", "make", "pkg-config"]
PERMANENT_PACKAGES = ["libvulkan1", "nvidia-container-toolkit", "vulkan-validationlayers"]
HEADERS = {"User-Agent": "curl/7.88.1"}
EXTENSIONS_CHROOT = os.path.join(TMPFS, "extensions_chroot")
EXTENSIONS_CHROOT_BASE = os.path.join(TMPFS, "extensions_chroot_base")


def build_extensions(rootfs_image, dst_dir):
    for path in [EXTENSIONS_CHROOT, EXTENSIONS_CHROOT_BASE]:
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)

    run(["unsquashfs", "-dest", EXTENSIONS_CHROOT, rootfs_image])
    run(["unsquashfs", "-dest", EXTENSIONS_CHROOT_BASE, rootfs_image])

    kernel_version = get_kernel_version(EXTENSIONS_CHROOT)

    os.makedirs(os.path.join(EXTENSIONS_CHROOT, "proc"), exist_ok=True)
    run(["mount", "proc", os.path.join(EXTENSIONS_CHROOT, "proc"), "-t", "proc"])
    os.makedirs(os.path.join(EXTENSIONS_CHROOT, "sys"), exist_ok=True)
    run(["mount", "sysfs", os.path.join(EXTENSIONS_CHROOT, "sys"), "-t", "sysfs"])
    os.makedirs(os.path.join(EXTENSIONS_CHROOT, "packages"), exist_ok=True)
    run(["mount", "--bind", PKG_DIR, os.path.join(EXTENSIONS_CHROOT, "packages")])
    try:
        shutil.copyfile("/etc/resolv.conf", f"{EXTENSIONS_CHROOT}/etc/resolv.conf")

        for binary in BINARIES:
            os.unlink(os.path.join(EXTENSIONS_CHROOT, f"usr/local/bin/{binary}"))
            os.chmod(os.path.join(EXTENSIONS_CHROOT, f"usr/bin/{binary}"), 0o755)

        add_nvidia_repository()
        run_in_chroot(["apt", "update"], chroot=EXTENSIONS_CHROOT)
        run_in_chroot(["apt", "-y", "install"] + TEMPORARY_PACKAGES + PERMANENT_PACKAGES, chroot=EXTENSIONS_CHROOT)

        install_nvidia_driver(kernel_version)

        run_in_chroot(["apt", "-y", "remove"] + TEMPORARY_PACKAGES, chroot=EXTENSIONS_CHROOT)
        run_in_chroot(["apt", "-y", "autoremove"], chroot=EXTENSIONS_CHROOT)
    finally:
        run(["umount", os.path.join(EXTENSIONS_CHROOT, "packages")])
        run(["umount", os.path.join(EXTENSIONS_CHROOT, "sys")])
        run(["umount", os.path.join(EXTENSIONS_CHROOT, "proc")])

    build_extension("nvidia", f"{dst_dir}/nvidia.raw")


def add_nvidia_repository():
    r = requests.get("https://nvidia.github.io/libnvidia-container/gpgkey")
    r.raise_for_status()

    with open(f"{EXTENSIONS_CHROOT}/key.gpg", "w") as f:
        f.write(r.text)

    run_in_chroot(["gpg", "-o", "/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg", "--dearmor", "/key.gpg"],
                  chroot=EXTENSIONS_CHROOT)

    with open(f"{EXTENSIONS_CHROOT}/etc/apt/sources.list.d/nvidia-container-toolkit.list", "w") as f:
        f.write("deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] "
                "https://nvidia.github.io/libnvidia-container/stable/deb/$(ARCH) /")


def download_nvidia_driver():
    prefix = "https://download.nvidia.com/XFree86/Linux-x86_64"

    version = get_manifest()["extensions"]["nvidia"]["current"]
    filename = f"NVIDIA-Linux-x86_64-{version}-no-compat32.run"
    result = f"{EXTENSIONS_CHROOT}/{filename}"

    with requests.get(f"{prefix}/{version}/{filename}", headers=HEADERS, stream=True, timeout=10) as r:
        r.raise_for_status()
        with open(result, "wb") as f:
            shutil.copyfileobj(r.raw, f)

    os.chmod(result, 0o755)
    return result


def install_nvidia_driver(kernel_version):
    driver = download_nvidia_driver()

    run_in_chroot([f"/{os.path.basename(driver)}", "--skip-module-load", "--silent", f"--kernel-name={kernel_version}",
                   "--allow-installation-with-running-driver", "--no-rebuild-initramfs"],
                  chroot=EXTENSIONS_CHROOT)

    os.unlink(driver)


def build_extension(name, dst_path):
    changed_files = [
        os.path.relpath(filename, EXTENSIONS_CHROOT)
        for filename in map(
            lambda filename: os.path.join(os.getcwd(), filename),
            run(
                ["rsync", "-avn", "--out-format=%f", f"{EXTENSIONS_CHROOT}/", f"{EXTENSIONS_CHROOT_BASE}/"],
                log=False,
            ).stdout.split("\n")
        )
        if os.path.abspath(filename).startswith(os.path.abspath(EXTENSIONS_CHROOT))
    ]

    sysext_files = [f for f in changed_files if f.startswith("usr/") and not (f.startswith("usr/src/"))]

    for root, dirs, files in os.walk(EXTENSIONS_CHROOT, topdown=False):
        for f in files:
            path = os.path.relpath(os.path.abspath(os.path.join(root, f)), EXTENSIONS_CHROOT)
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

    os.makedirs(f"{EXTENSIONS_CHROOT}/usr/lib/extension-release.d", exist_ok=True)
    with open(f"{EXTENSIONS_CHROOT}/usr/lib/extension-release.d/extension-release.{name}", "w") as f:
        f.write("ID=_any\n")

    run(["mksquashfs", EXTENSIONS_CHROOT, dst_path, "-comp", "xz"])
