from collections.abc import Generator
from dataclasses import dataclass
from functools import cached_property
from os import makedev, scandir

__all__ = ("get_pids", "getmntinfo",)


@dataclass(frozen=True, kw_only=True)
class PidEntry:
    cmdline: bytes
    pid: int

    @cached_property
    def name(self) -> bytes:
        """The name of process as described in man 2 PR_SET_NAME"""
        with open(f"/proc/{self.pid}/status", "rb") as f:
            # first line in this file is name of process
            # and this is in procfs, which is considered
            # part of linux's ABI and is stable
            return f.readline().split(b"\t", 1)[-1].strip()


@dataclass(slots=True, frozen=True, kw_only=True)
class DevIdEntry:
    major: int
    minor: int
    dev_t: int


@dataclass(slots=True, frozen=True, kw_only=True)
class MntEntry:
    mount_id: int
    parent_id: int
    device_id: DevIdEntry
    root: str
    mountpoint: str
    mount_opts: list[str]
    fs_type: str
    mount_source: str
    super_opts: list[str]


def get_pids() -> Generator[PidEntry] | None:
    """Get the currently running processes on the OS"""
    with scandir("/proc/") as sdir:
        for i in filter(lambda x: x.name.isdigit(), sdir):
            try:
                with open(f"{i.path}/cmdline", "rb") as f:
                    cmdline = f.read().replace(b"\x00", b" ")
                yield PidEntry(cmdline=cmdline, pid=int(i.name))
            except FileNotFoundError:
                # process could have gone away
                pass


def getmntinfo() -> Generator[MntEntry]:
    with open('/proc/self/mountinfo') as f:
        for line in f:
            mnt_id, parent_id, maj_min, root, mp, opts, extra = line.split(" ", 6)
            fstype, mnt_src, super_opts = extra.split(' - ')[1].split()
            major, minor = maj_min.split(':')
            major, minor = int(major), int(minor)
            devid = makedev(major, minor)
            deventry = DevIdEntry(major=major, minor=minor, dev_t=devid)
            yield MntEntry(**{
                'mount_id': int(mnt_id),
                'parent_id': int(parent_id),
                'device_id': deventry,
                'root': root.replace('\\040', ' '),
                'mountpoint': mp.replace('\\040', ' '),
                'mount_opts': opts.upper().split(','),
                'fs_type': fstype,
                'mount_source': mnt_src.replace('\\040', ' '),
                'super_opts': super_opts.upper().split(','),
            })
