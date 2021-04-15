from scale_build.bootstrap.cache import restore_basecache
from scale_build.utils.run import run


class BootstrapMixin:
    def setup_chroot_basedir(self):
        self.logger.debug('Restoring CHROOT_BASEDIR for runs...')
        if self.tmpfs:
            run(
                ['mount', '-t', 'tmpfs', '-o', f'size={self.tmpfs_size}G', 'tmpfs', self.tmpfs_path],
                logger=self.logger
            )
        restore_basecache('package', self.chroot_base_directory, self.logger)
