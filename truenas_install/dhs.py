TRUENAS_DATA_HIERARCHY_SCHEMA = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'type': 'array',
    'items': {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'pattern': r'^data.*'},
            'mode': {
                'type': 'object',
                'properties': {
                    'user': {'type': 'string', 'pattern': r'^(r?w?[xX]?)?$'},
                    'group': {'type': 'string', 'pattern': r'^(r?w?[xX]?)?$'},
                    'other': {'type': 'string', 'pattern': r'^(r?w?[xX]?)?$'},
                },
                'required': ['user', 'group', 'other'],
                'additionalProperties': False,
            },
            'owner': {
                'type': 'object',
                'properties': {
                    'uid': {'type': 'integer'},
                    'gid': {'type': 'integer'},
                },
                'required': ['uid', 'gid'],
                'additionalProperties': False,
            },
            'recursive': {'type': 'boolean'},
            'recursive_ownership': {'type': 'boolean'},
        },
        'required': ['path'],
        'additionalProperties': False,
        'dependencies': {
            'recursive': ['mode'],
            'mode': ['recursive'],
            'owner': ['recursive_ownership'],
            'recursive_ownership': ['owner'],
        },
    }
}


TRUENAS_DATA_HIERARCHY = [
    {
        'path': 'data',
        'mode': {
            'user': 'rwx',
            'group': 'rx',
            'other': 'rx',
        },
        'recursive': False,
    },
    {
        'path':  'data/subsystems',
        'mode': {
            'user': 'rwx',
            'group': 'rx',
            'other': 'rx',
        },
        'recursive': True,
    },
    {
        'path': 'data/subsystems/vm',
    },
    {
        'path': 'data/subsystems/vm/nvram',
        'owner': {
            'uid': 986,
            'gid': 986,
        },
        'recursive_ownership': True,
    },
    {
        'path': 'data/zfs',
        'mode': {
            'user': 'rwx',
            'group': '',
            'other': '',
        },
        'recursive': True,
    },
    {
        'path': 'data/sentinels',
        'mode': {
            'user': 'rwx',
            'group': '',
            'other': '',
        },
        'recursive': False,
    }
]
