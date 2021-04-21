import logging
import os
import queue
import shutil
import threading

from toposort import toposort

from .bootstrap.configure import make_bootstrapdir
from .clean import clean_bootstrap_logs
from .config import PARALLEL_BUILD, PKG_DEBUG
from .packages.order import get_to_build_packages
from .utils.paths import PKG_DIR, PKG_LOG_DIR
from .utils.run import interactive_run, run


logger = logging.getLogger(__name__)

APT_LOCK = threading.Lock()
PACKAGE_BUILD_LOCK = threading.Lock()


def update_queue(package_queue, to_build_orig, failed, in_progress, built):
    if failed:
        # If we have failure(s), there is no point in continuing
        return

    to_build = {k: v for k, v in to_build_orig.items()}
    to_remove = set()
    for pkg_name, package in in_progress.items():
        for child in package.children:
            to_remove.add(child)

    for rm in to_remove:
        to_build.pop(rm, None)

    deps_mapping = {
        p.name: {d for d in p.build_time_dependencies() if d not in built} for p in list(to_build.values())
    }
    sorted_ordering = [list(deps) for deps in toposort(deps_mapping)]

    for item in filter(
        lambda i: i in to_build and i not in in_progress and i not in package_queue.queue and i not in built,
        sorted(sorted_ordering[0], key=lambda k: to_build_orig[k].batch_priority) if sorted_ordering else []
    ):
        package_queue.put(to_build_orig.pop(item))


def build_package(package_queue, to_build, failed, in_progress, built):
    while True:
        if not failed and (to_build or package_queue.queue):
            try:
                package = package_queue.get(timeout=5)
            except queue.Empty:
                package = None
            else:
                in_progress[package.name] = package
        else:
            if PKG_DEBUG:
                logger.debug('Thread exiting')
            break

        if package:
            try:
                logger.debug('Building %r package', package.name)
                package.delete_overlayfs()
                package.setup_chroot_basedir()
                package.make_overlayfs()
                with APT_LOCK:
                    package.clean_previous_packages()
                    shutil.copytree(PKG_DIR, package.dpkg_overlay_packages_path)
                package._build_impl()
            except Exception as e:
                logger.error('Failed to build %r package', package.name)
                failed[package.name] = {'package': package, 'exception': e}
                break
            else:
                with APT_LOCK:
                    package.logger.debug('Building local APT repo Packages.gz...')
                    run(
                        f'cd {PKG_DIR} && dpkg-scanpackages . /dev/null | gzip -9c > Packages.gz',
                        shell=True, logger=package.logger
                    )
                in_progress.pop(package.name)
                built[package.name] = package
                logger.info(
                    'Successfully built %r package (Remaining %d packages)', package.name,
                    len(to_build) + package_queue.qsize() + len(in_progress)
                )

        with PACKAGE_BUILD_LOCK:
            if not package:
                update_queue(package_queue, to_build, failed, in_progress, built)


def build_packages():
    clean_bootstrap_logs()
    _build_packages_impl()


def _build_packages_impl():
    logger.info('Building packages')
    logger.debug('Setting up bootstrap directory')
    make_bootstrapdir('package')
    logger.debug('Successfully setup bootstrap directory')

    shutil.rmtree(PKG_LOG_DIR, ignore_errors=True)
    os.makedirs(PKG_LOG_DIR)

    to_build = get_to_build_packages()
    logger.debug('Going to build %d packages: %s', len(to_build), ','.join(to_build))
    package_queue = queue.Queue()
    in_progress = {}
    failed = {}
    built = {}
    update_queue(package_queue, to_build, failed, in_progress, built)
    logger.debug('Creating %d parallel tasks', PARALLEL_BUILD)
    threads = [
        threading.Thread(
            name=f'build_packages_thread_{i + 1}', target=build_package,
            args=(package_queue, to_build, failed, in_progress, built)
        ) for i in range(PARALLEL_BUILD)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if failed:
        logger.error('Failed to build %r package(s)', ', '.join(failed))
        try:
            if PKG_DEBUG:
                logger.debug(
                    'Please specify name or index of package to debug ( shell access would be provided to failed '
                    'package\'s environment ) from following.'
                )
                while True:
                    data = input(
                        '\n'.join(
                            [f'{i+1}) {k}' for i, k in enumerate(failed)]
                        ) + '\n\nPlease type "exit" when done.\n'
                    )
                    if data in ('exit', 'e'):
                        logger.debug('Exiting debug session')
                        break
                    elif data.isdigit() and not (1 <= int(data) <= len(failed)):
                        logger.debug('Please provide valid index value')
                    elif not data.isdigit() and data not in failed:
                        logger.debug('Please provide valid package name')
                    else:
                        package = failed[data]['package'] if data in failed else list(failed.values())[int(data) - 1]
                        interactive_run(package.debug_command)
        finally:
            for p in failed.values():
                p['package'].delete_overlayfs()

    else:
        logger.info('Success! Done building packages')
