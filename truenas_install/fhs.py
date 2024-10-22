"""
TrueNAS Filesysten Heirarchy Standards extensions

The TRUENAS_DATASET dictionary contains the dataset configuration
settings for the root filesystem of the truenas server.

When practical it is best to turn off unnecessary features.
For example, disabling ACL support on system files simplifies
permissions auditing. Disabling ACL support also ensures compliance
with STIGs that require configuration files and libraries to not have ACLs
present.

KEYS
--------------
The following keys are supported:
`name` - the name of the dataset (will be appended to other dataset name
    related components
`options` - Dataset configuration options (explained below). There is no
    default.
`mode` - permissions to set on the dataset's mountpoint during installation
    default is 0o755
`mountpoint` - dataset mountpoint. If no mountpoint is specified then it
    /`name` will be assumed.
`snap` - Take a snapshot named "pristine" after creating the dataset.
    default is False
`clone` - Clone the dataset when updating existing installation.

OPTIONS
--------------
NOSUID - sets a combination of setuid=off and devices=off
NOEXEC - sets exec=off
NOACL - sets acltype=off.
NOATIME - sets atime=off.
RO - sets readonly=on.
NODEV - sets devices=off
DEV - sets devices=on

DATASETS
--------------
audit - dataset used for storing system auditing databases
conf - truenas configuration files - static
data - truenas configuraiton files - dynamic
etc - see FHS
home - see FHS, NOTE: only `admin` account will be present
mnt - TrueNAS does not follow FHS for this path. It is reserved exclusively
    for ZFS pool mountpoints.
opt - see FHS
usr - see FHS
var - see FHS
var/log - separate dataset for system logs. This is to provide flexibility to
    snapshot and replicate log information as needed by administrator.
var/ca-certificates - administrator-provided CA certificates, symlinked
    from /usr/local/share/ca-certificates.
"""


# Following schema is used for validation (e.g. "make validate") in scale-build
# If any changes are made to OPTIONS or KEYS above then schema must be updated
# accordingly.
TRUENAS_DATASET_SCHEMA = {
    'type': 'array',
    'items': {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'options': {
                'type': 'array',
                'items': {
                    'type': 'string',
                    'enum': [
                        'NOSUID',
                        'NOEXEC',
                        'NOACL',
                        'NOATIME',
                        'RO',
                        'NODEV',
                        'DEV',
                        'POSIXACL',
                    ]
                },
                'uniqueItems': True,
            },
            'mode': {'type': 'integer'},
            'mountpoint': {'type': 'string'},
            'snap': {'type': 'boolean'},
            'clone': {'type': 'boolean'},
        },
        'required': ['name', 'options'],
        'additionalProperties': False,
    }
}


TRUENAS_DATASETS = [
    {
        'name':  'audit',
        'options': ['NOSUID', 'NOEXEC', 'NOATIME', 'NOACL'],
        'mode': 0o700,
        'clone': True,
    },
    {
        'name':  'conf',
        'options': ['NOSUID', 'NOEXEC', 'RO', 'NOACL'],
        'mode': 0o700,
        'snap': True
    },
    {
        'name':  'data',
        'options': ['NOSUID', 'NOEXEC', 'NOACL', 'NOATIME'],
        'mode': 0o755,
        'clone': True,
    },
    {
        'name':  'mnt',
        'options': ['NOSUID', 'NOEXEC', 'NOACL', 'NOATIME'],
    },
    {
        'name':  'etc',
        'options': ['NOSUID', 'NOACL'],
        'snap': True
    },
    {
        'name':  'home',
        'options': ['NOSUID', 'NOACL', 'NOEXEC'],
        'clone': True,
    },
    {
        'name':  'opt',
        'options': ['NOSUID', 'NOACL', 'RO'],
        'snap': True
    },
    {
        'name':  'root',
        'options': ['NOSUID', 'NOACL'],
        'mode': 0o700,
        'clone': True,
    },
    {
        'name':  'usr',
        'options': ['NOACL', 'RO', 'NOATIME'],
        'snap': True
    },
    {
        'name':  'var',
        'options': ['NOSUID', 'NOACL', 'NOATIME'],
        'snap': True
    },
    {
        'name':  'var/ca-certificates',
        'options': ['NOSUID', 'NOACL', 'NOEXEC'],
        'mountpoint': '/var/local/ca-certificates'
    },
    {
        'name':  'var/lib',
        'options': ['NOSUID', 'NOACL', 'NOATIME'],
        'snap': True
    },
    {
        'name':  'var/lib/incus',
        'options': ['NOSUID', 'NOACL', 'NOATIME', 'DEV'],
        'snap': True
    },
    {
        'name':  'var/log',
        'options': ['NOSUID', 'NOEXEC', 'NOACL', 'NOATIME'],
        'clone': True,
    },
    {
        'name':  'var/log/journal',
        'options': ['NOSUID', 'NOEXEC', 'POSIXACL', 'NOATIME'],
    },
]
