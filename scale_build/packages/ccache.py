from scale_build.config import CCACHE_ENABLED


class CCacheMixin:

    CCACHE_PATH = '/usr/lib/ccache'

    @property
    def ccache_enabled(self) -> bool:
        return self.ccache and CCACHE_ENABLED
