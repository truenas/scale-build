import os
import difflib

from scale_build.exceptions import CallError

from .paths import REFERENCE_FILES_DIR, REFERENCE_FILES, CHROOT_BASEDIR


def compare_reference_files(cut_nonexistent_user_group_membership: bool = False, default_homedir: str | None = None):
    """Diff /conf/reference-files/etc/group|passwd with the respective files in chroot.

    :param cut_nonexistent_user_group_membership:
    :param default_homedir: A home directory to replace Debian's default `/nonexistent` before running the diff.
    """
    for reference_file in REFERENCE_FILES:
        with open(os.path.join(REFERENCE_FILES_DIR, reference_file)) as f:
            reference = f.readlines()

        if not os.path.exists(os.path.join(CHROOT_BASEDIR, reference_file)):
            raise CallError(f'File {reference_file!r} does not exist in cached chroot')

        if cut_nonexistent_user_group_membership:
            if reference_file == 'etc/group':
                # `etc/group` on newly installed system can't have group membership information for users that have
                # not been created yet.
                with open(os.path.join(CHROOT_BASEDIR, 'etc/passwd')) as f:
                    reference_users = {line.split(':')[0] for line in f.readlines()}

                for i, line in enumerate(reference):
                    bits = line.rstrip().split(':')
                    bits[3] = ','.join([user for user in bits[3].split(',') if user in reference_users])
                    reference[i] = ':'.join(bits) + '\n'

        with open(os.path.join(CHROOT_BASEDIR, reference_file)) as f:
            real = f.readlines()

        if default_homedir and reference_file == 'etc/passwd':
            real = [line.replace('/nonexistent', default_homedir) for line in real]

        diff = list(difflib.unified_diff(reference, real))

        yield reference_file, diff[3:]
