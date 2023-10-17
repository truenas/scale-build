import logging
import os
import shutil

from .utils.paths import HASH_DIR, LOG_DIR, PKG_DIR, SOURCES_DIR, TMP_DIR


logger = logging.getLogger(__name__)


def clean_bootstrap_logs():
    for f in filter(lambda f: f.startswith('bootstrap'), os.listdir(LOG_DIR)):
        os.unlink(os.path.join(LOG_DIR, f))


def clean_packages():
    for d in (HASH_DIR, PKG_DIR):
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)


def complete_cleanup():
    for path in (LOG_DIR, SOURCES_DIR, TMP_DIR):
        try:
            shutil.rmtree(path)
        except (FileNotFoundError, NotADirectoryError):
            # these shouldn't happen but they're explicitly
            # ignored so a comment can be made and you are
            # able to gather context
            continue
        except OSError:
            # we use a bunch of overlayfs mounts (using tmpfs) for
            # each package that we build. if the build is interrupted
            # for whatever reason (someone kills job in jenkins) then
            # OSError can be raised with errno 66 (directory not empty)
            # for example because the `TMP_DIR` can have a sub-directory
            # that points back to an overlayfs mountpoint that has not
            # been umounted (because build process was interrupted)
            # In this case, we can safely ignore the errors and move on
            # because the next time our build process is kicked off, each
            # package will call `delete_overlayfs()` which will clean this
            # up for us
            continue

    logger.debug('Removed %s, %s, and %s directories', LOG_DIR, SOURCES_DIR, TMP_DIR)
