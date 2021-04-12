import errno


class CallError(Exception):
    def __init__(self, errmsg, errno=errno.EFAULT, extra=None):
        self.errmsg = errmsg
        self.errno = errno
        self.extra = extra

    def __str__(self):
        return f'[{self.errno}] {self.errmsg}'


class MissingManifest(CallError):
    def __init__(self):
        super().__init__('Unable to locate manifest file', errno.ENOENT)


class InvalidManifest(CallError):
    def __init__(self):
        super().__init__('Invalid manifest file found', errno.EINVAL)


class MissingPackagesException(CallError):
    def __init__(self, packages):
        super().__init__(f'Failed preflight check. Please install {", ".join(packages)!r} packages.', errno.ENOENT)
