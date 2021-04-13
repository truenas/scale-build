class BinaryPackage:
    def __init__(self, name, build_dependencies, source_package, source_name, install_dependencies):
        self.name = name
        self.build_dependencies = build_dependencies
        self.source_package = source_package
        self.source_name = source_name
        self.install_dependencies = install_dependencies

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self.name == other.name
