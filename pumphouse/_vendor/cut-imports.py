#!/usr/bin/env python

import os
import re
import sys


IMPORT_RE = re.compile("^(\s*(?:from|import)\s+)([\w.]+)(.*)$")


def modules(package):
    for dirpath, dirnames, filenames in os.walk(package):
        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext == ".py":
                yield os.path.join(dirpath, filename)


def relative_imports(package, module):
    def relative(line):
        matched = IMPORT_RE.match(line)
        if not matched:
            return line
        head, import_path, tail = matched.groups()

        if not import_path.startswith(package):
            return line

        import_parts = import_path.split(".")

        parts = enumerate(zip(module_parts, import_parts))
        for i, (module_part, import_part) in parts:
            if module_part != import_part:
                break
        else:
            i += 1
        lead = len(module_parts) - i + 1
        lead_dots = "." * lead
        if "import" in head and "as" in tail:
            # import ..smth as another
            head = head.replace("import", "from")
            fmt = "{} import {}"
        else:
            fmt = "{}{}"
        relative_import_path = fmt.format(lead_dots,
                                          ".".join(import_parts[i:]))
        relative_parts = [head, relative_import_path, tail, "\n"]
        relative_line = "".join(relative_parts)
        return relative_line

    module_parts = module[:-3].split(os.path.sep)[:-1]
    return relative


def replace_import(package, module):
    relative = relative_imports(package, module)
    with open(module, "rb+") as f:
        lines = f.readlines()
        f.seek(0)
        f.truncate()
        for line in lines:
            stripped_line = line.strip()
            if (stripped_line.startswith("import") or
                    stripped_line.startswith("from")):
                line = relative(line)
            f.write(line)


def main(argv):
    package = argv[0]
    for module in modules(package):
        try:
            replace_import(package, module)
        except Exception:
            print("Failed to replace imports for module: {}".format(module))
            raise
        else:
            print(module)


if __name__ == "__main__":
    main(sys.argv[1:])
