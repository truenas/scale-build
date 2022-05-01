import logging
import concurrent.futures

from .exceptions import CallError
from .utils.git_utils import retrieve_git_remote_and_sha, update_git_manifest
from .utils.package import get_packages


logger = logging.getLogger(__name__)
MAX_THREADS = 10  # number of threads to spin up to checkout/pull github sources


def checkout_sources():
    info = retrieve_git_remote_and_sha('.')
    update_git_manifest(info['url'], info['sha'], 'w')

    pkgs = {
        pkg.name: {
            'checkout_method': pkg.checkout,
            'get_branch_override_method': pkg.get_branch_override,
            'branch_override': None,
        } for pkg in get_packages()
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as exc:
        logger.info('Getting override for branches')
        branchoverrides_to_pkgs = {exc.submit(v['get_branch_override_method']): k for k, v in pkgs.items()}
        for fut in concurrent.futures.as_completed(branchoverrides_to_pkgs):
            pkg_name = branchoverrides_to_pkgs[fut]
            try:
                pkgs[pkg_name]['branch_override'] = fut.result()
            except Exception:
                logger.warning('Failed to generate branch override for %r', pkg_name, exc_info=True)
                raise

        logger.info('Starting checkout of sources')
        futures = [exc.submit(v['checkout_method'], v['branch_override']) for pkg, v in pkgs.items()]
        failures = []
        for future, pkg in zip(futures, pkgs):
            try:
                future.result()
            except Exception as e:
                failures.append((pkg, str(e)))

    if failures:
        raise CallError(
            'Failed to checkout following packages:\n' + '\n'.join(
                f'{i+1}) {v[0]} ({v[1]})' for i, v in enumerate(failures)
            )
        )
