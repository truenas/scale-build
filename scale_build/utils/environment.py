import os


APT_ENV = {
    # When logging in as 'su root' the /sbin dirs get dropped out of PATH
    'PATH': f'{os.environ["PATH"]}:/sbin:/usr/sbin:/usr/local/sbin',
    'LC_ALL': 'C',  # Makes some perl scripts happy during package builds
    'LANG': 'C',
    'DEB_BUILD_OPTIONS': f'parallel={os.cpu_count()}',  # Passed along to WAF for parallel build,
    'DEBIAN_FRONTEND': 'noninteractive',  # Never go full interactive on any packages
}
