class CallError(Exception):
    def __init__(self, errmsg):
        self.errmsg = errmsg

    def __str__(self):
        return self.errmsg


class MissingManifest(CallError):
    def __init__(self):
        super().__init__('Unable to locate manifest file')


class MissingPackagesException(CallError):
    def __init__(self, packages):
        super().__init__(f'Failed preflight check. Please install {", ".join(packages)!r} packages.')
