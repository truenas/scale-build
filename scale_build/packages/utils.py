from scale_build.config import get_env_variable, get_normalized_value


CONSTRAINT_MAPPING = {
    'boolean': bool,
    'integer': int,
    'string': str,
}
DEPENDS_SCRIPT_PATH = './scripts/parse_deps.pl'


def normalize_bin_packages_depends(depends_str):
    return list(filter(lambda k: k and '$' not in k, map(str.strip, depends_str.split(','))))


def normalize_build_depends(build_depends_str):
    deps = []
    for dep in filter(bool, map(str.strip, build_depends_str.split(','))):
        for subdep in filter(bool, map(str.strip, dep.split('|'))):
            index = subdep.find('(')
            if index != -1:
                subdep = subdep[:index].strip()
            deps.append(subdep)
    return deps


def gather_build_time_dependencies(packages, deps, deps_list):
    for dep in filter(lambda p: p in packages, deps_list):
        deps.add(packages[dep].source_name)
        deps.update(gather_build_time_dependencies(
            packages, deps, packages[dep].install_dependencies | packages[dep].build_dependencies
        ))
    return deps


def get_normalized_specified_build_constraint_value(value_schema):
    return get_env_variable(value_schema['name'], CONSTRAINT_MAPPING[value_schema['type']])


def get_normalized_build_constraint_value(value_schema):
    return get_normalized_value(value_schema['value'], CONSTRAINT_MAPPING[value_schema['type']])
