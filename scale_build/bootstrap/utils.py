from scale_build.utils.manifest import get_manifest


def get_apt_preferences():
    return '\n\n'.join(
        '\n'.join(f'{k}: {v}' for k, v in pref.items()) for pref in get_manifest()['apt_preferences']
    )
