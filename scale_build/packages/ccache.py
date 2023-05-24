import os

from scale_build.config import CCACHE_ENABLED


class CCacheMixin:

    CCACHE_PATH = '/usr/lib/ccache'

    @property
    def ccache_enabled(self) -> bool:
        return self.supports_ccache and CCACHE_ENABLED

    @property
    def ccache_with_chroot_path(self) -> str:
        return os.path.join(self.dpkg_overlay, self.ccache_in_chroot.lstrip('/'))

    @property
    def ccache_in_chroot(self) -> str:
        return '/root/.ccache'

    def ccache_env(self, existing_env: dict) -> dict:
        if not self.ccache_enabled:
            return {}

        env = {'CCACHE_DIR': self.ccache_in_chroot}
        if self.CCACHE_PATH not in existing_env['PATH'].split(':'):
            env['PATH'] = f'{self.CCACHE_PATH}:{existing_env["PATH"]}'

        return env

    def setup_ccache(self) -> None:
        if not self.ccache_enabled:
            return

        self.logger.debug('Setting up ccache')
        self.run_in_chroot('apt install -y ccache')
