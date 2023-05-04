import contextlib
import os
import os.path

from scale_build.utils.run import run


class CcacheMixin:

    CCACHE_PATH = '/usr/lib/ccache'

    @contextlib.contextmanager
    def setup_ccache(self, chroot_dir, ccache):
        ccache_outside_chroot = ccache['ccache_dir']
        ccache_in_chroot = os.path.join(chroot_dir, self.ccache_directory().lstrip('/'))
        os.makedirs(ccache_in_chroot, exist_ok=True)

        # print(f"Mounting {ccache_outside_chroot} on {ccache_in_chroot}")
        run(["mount", "--bind", ccache_outside_chroot, ccache_in_chroot],
            exception_msg=f'Failed mount --bind {ccache_outside_chroot} {ccache_in_chroot}')

        try:
            yield
        finally:
            # print(f"Unmounting {ccache_in_chroot}")
            run(['umount', '-f', ccache_in_chroot], check=False)

    def ccache_directory(self):
        return '/root/.ccache'

    def set_ccache_state(self, ccache):
        self._ccache = ccache

    def ccache_enabled(self):
        # set_ccache_state should have been called before we call this method,
        # unless we're building a binary package
        return hasattr(self, '_ccache') and 'ccache_dir' in self._ccache

    def ccache_in_path(self, path):
        return self.CCACHE_PATH in path.split(':')

    def add_ccache_to_path(self, path):
        result = [self.CCACHE_PATH] + path.split(':')
        return ':'.join(result)
