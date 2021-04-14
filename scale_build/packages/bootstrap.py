from scale_build.bootstrap.cache import restore_basecache


class BootstrapMixin:
    def setup_chroot_basedir(self):
        self.logger.debug('Restoring CHROOT_BASEDIR for runs...')
        restore_basecache('package', self.chroot_base_directory, self.logger)
