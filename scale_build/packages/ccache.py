import os

from scale_build.config import CCACHE_ENABLED


class CCacheMixin:

    CCACHE_PATH = '/usr/lib/ccache'

    @property
    def ccache_enabled(self) -> bool:
        return self.ccache and CCACHE_ENABLED

    @property
    def ccache_with_chroot_path(self) -> str:
        return os.path.join(self.dpkg_overlay, self.ccache_in_chroot.lstrip('/'))

    @property
    def ccache_in_chroot(self) -> str:
        return '/root/.ccache'
