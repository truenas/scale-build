import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from .utils.git_utils import retrieve_git_remote_and_sha, update_git_manifest
from .utils.package import get_packages


logger = logging.getLogger(__name__)
MAX_THREADS = 10  # number of threads to spin up to checkout/pull github sources


def checkout_sources():
    info = retrieve_git_remote_and_sha('.')
    update_git_manifest(info['url'], info['sha'], 'w')

    pkgs = {
        pkg.pkg_name: {
            'checkout_method': pkg.checkout,
            'get_branch_override_method': pkg.get_branch_override,
            'branch_override': None,
        } for pkg in get_packages()
    }
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as exc:
        logger.info('Getting override for branches')
        branchoverrides_to_pkgs = {exc.submit(v['get_branch_override_method']): k for k, v in pkgs.items()}
        for fut in as_completed(branchoverrides_to_pkgs):
            pkg_name = branchoverrides_to_pkgs[fut]
            try:
                branch_override = fut.result()
            except Exception:
                logger.warning('Failed to generate branch override for %r', pkg_name, exc_info=True)
                branch_override = None

            pkgs[pkg_name]['branch_override'] = branch_override

        logger.info('Starting checkout of sources')
        [exc.submit(v['checkout_method'], v['branch_override']) for pkg, v in pkgs.items()]
