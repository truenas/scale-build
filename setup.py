from setuptools import setup

# Configuration is now in pyproject.toml
# This setup.py is kept for backward compatibility
setup(
    scripts=[
        'scripts/parse_deps.pl',
    ]
)
