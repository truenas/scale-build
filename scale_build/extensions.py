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


def build_extensions(rootfs_image, dst_dir):
    chroot = os.path.join(TMPFS, "extensions_chroot")
    chroot_base = os.path.join(TMPFS, "extensions_chroot_base")

    if os.path.exists(chroot_base):
        shutil.rmtree(chroot_base)
    os.makedirs(chroot_base)
    run(["unsquashfs", "-dest", chroot_base, rootfs_image])

    for klass, name in [(DevToolsExtension, "dev-tools"), (NvidiaExtension, "nvidia")]:
        klass(rootfs_image, chroot_base, chroot).build(name, f"{dst_dir}/{name}.raw")


class Extension:
    def __init__(self, base_image: str, chroot_base: str, chroot: str):
        """
        :param base_image: rootfs squashfs image path
        :param chroot_base: a path where `base_image` is extracted
            (it will be used to compare which files were modified and should be included in the extension image)
        :param chroot: a path which will be used as chroot for extension install
        """
        self.base_image = base_image
        self.chroot_base = chroot_base
        self.chroot = chroot

    def build(self, name, dst_path):
        if os.path.exists(self.chroot):
            shutil.rmtree(self.chroot)
        os.makedirs(self.chroot)

        run(["unsquashfs", "-dest", self.chroot, self.base_image])

        os.makedirs(os.path.join(self.chroot, "proc"), exist_ok=True)
        run(["mount", "proc", os.path.join(self.chroot, "proc"), "-t", "proc"])
        os.makedirs(os.path.join(self.chroot, "sys"), exist_ok=True)
        run(["mount", "sysfs", os.path.join(self.chroot, "sys"), "-t", "sysfs"])
        os.makedirs(os.path.join(self.chroot, "packages"), exist_ok=True)
        run(["mount", "--bind", PKG_DIR, os.path.join(self.chroot, "packages")])
        try:
            shutil.copyfile("/etc/resolv.conf", f"{self.chroot}/etc/resolv.conf")

            self.build_impl()
        finally:
            run(["umount", os.path.join(self.chroot, "packages")])
            run(["umount", os.path.join(self.chroot, "sys")])
            run(["umount", os.path.join(self.chroot, "proc")])

        self.build_extension(name, dst_path)

    def build_impl(self):
        raise NotImplementedError

    def build_extension(self, name, dst_path):
        changed_files = [
            os.path.relpath(filename, self.chroot)
            for filename in map(
                lambda filename: os.path.join(os.getcwd(), filename),
                run(
                    ["rsync", "-avn", "--out-format=%f", f"{self.chroot}/", f"{self.chroot_base}/"],
                    log=False,
                ).stdout.split("\n")
            )
            if os.path.abspath(filename).startswith(os.path.abspath(self.chroot))
        ]

        sysext_files = [f for f in changed_files if f.startswith("usr/") and not (f.startswith("usr/src/"))]

        for root, dirs, files in os.walk(self.chroot, topdown=False):
            for f in files:
                path = os.path.relpath(os.path.abspath(os.path.join(root, f)), self.chroot)
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

        os.makedirs(f"{self.chroot}/usr/lib/extension-release.d", exist_ok=True)
        with open(f"{self.chroot}/usr/lib/extension-release.d/extension-release.{name}", "w") as f:
            f.write("ID=_any\n")

        run(["mksquashfs", self.chroot, dst_path, "-comp", "xz"])

    def run(self, cmd: list[str]):
        run_in_chroot(cmd, chroot=self.chroot)


class DevToolsExtension(Extension):
    def build_impl(self):
        # Make `install-dev-tools` think that this is not necessary
        os.unlink(os.path.join(self.chroot, "usr/local/libexec/disable-rootfs-protection"))

        self.run(["install-dev-tools"])


class NvidiaExtension(Extension):
    binaries = ("apt", "apt-config", "apt-key", "dpkg")
    temporary_packages = ["gcc", "make", "pkg-config"]
    permanent_packages = ["libvulkan1", "nvidia-container-toolkit", "vulkan-validationlayers"]

    def build_impl(self):
        kernel_version = get_kernel_version(self.chroot)

        for binary in self.binaries:
            os.unlink(os.path.join(self.chroot, f"usr/local/bin/{binary}"))
            os.chmod(os.path.join(self.chroot, f"usr/bin/{binary}"), 0o755)

        self.add_nvidia_repository()
        self.run(["apt", "update"])
        self.run(["apt", "-y", "install"] + self.temporary_packages + self.permanent_packages)

        self.install_nvidia_driver(kernel_version)

        self.run(["apt", "-y", "remove"] + self.temporary_packages)
        self.run(["apt", "-y", "autoremove"])

    def add_nvidia_repository(self):
        r = requests.get("https://nvidia.github.io/libnvidia-container/gpgkey")
        r.raise_for_status()

        with open(f"{self.chroot}/key.gpg", "w") as f:
            f.write(r.text)

        self.run(["gpg", "-o", "/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg", "--dearmor", "/key.gpg"])

        with open(f"{self.chroot}/etc/apt/sources.list.d/nvidia-container-toolkit.list", "w") as f:
            f.write("deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] "
                    "https://nvidia.github.io/libnvidia-container/stable/deb/$(ARCH) /")

    def download_nvidia_driver(self):
        prefix = "https://us.download.nvidia.com/XFree86/Linux-x86_64"

        version = get_manifest()["extensions"]["nvidia"]["current"]
        filename = f"NVIDIA-Linux-x86_64-{version}-no-compat32.run"
        result = f"{self.chroot}/{filename}"

        self.run(["wget", "-c", "-O", f"/{filename}", f"{prefix}/{version}/{filename}"])

        os.chmod(result, 0o755)
        return result

    def install_nvidia_driver(self, kernel_version):
        driver = self.download_nvidia_driver()

        self.run(
            [
                f"/{os.path.basename(driver)}",
                "--skip-module-load",
                "--silent",
                f"--kernel-name={kernel_version}",
                "--allow-installation-with-running-driver",
                "--no-rebuild-initramfs",
                "--kernel-module-type=open"
            ]
        )

        os.unlink(driver)
