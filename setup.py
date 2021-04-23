from setuptools import find_packages, setup


install_requires = [
    'pyyaml',
]


setup(
    name='scale_build',
    description='A build framework for TrueNAS SCALE',
    packages=find_packages(),
    include_package_data=True,
    license='BSD',
    platforms='any',
    install_requires=install_requires,
    entry_points={
        'console_scripts': [
            'scale_build = scale_build.main:main',
        ],
    },
    scripts=[
        'scripts/parse_deps.pl',
    ]
)
