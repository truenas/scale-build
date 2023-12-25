import os
import difflib

from .paths import REFERENCE_FILES_DIR, REFERENCE_FILES, CHROOT_BASEDIR


def compare_reference_files(cut_nonexistent_user_group_membership=False):
    for reference_file in REFERENCE_FILES:
        with open(os.path.join(REFERENCE_FILES_DIR, reference_file)) as f:
            reference = f.readlines()

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

        diff = list(difflib.unified_diff(reference, real))

        yield reference_file, diff[3:]
