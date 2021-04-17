from scale_build.utils.logger import get_logger as _get_logger


def get_log_file_name(bootstrap_dir_type):
    if bootstrap_dir_type == 'package':
        return 'bootstrap_chroot.log'
    elif bootstrap_dir_type == 'cd':
        return 'cdrom-bootstrap.log'
    else:
        return 'rootfs-bootstrap.log'


def get_logger(bootstrap_dir_type, mode='a+'):
    return _get_logger(f'bootstrap_dir_{bootstrap_dir_type}', get_log_file_name(bootstrap_dir_type), mode)
