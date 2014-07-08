import sys
import traceback
import yaml


def safe_load_yaml(filename):
    with open(filename) as f:
        return yaml.safe_load(f)


def load_class(import_path):
    mod_str, _sep, class_str = import_path.rpartition('.')
    try:
        __import__(mod_str)
        return getattr(sys.modules[mod_str], class_str)
    except (ValueError, AttributeError):
        raise ImportError('Class %s cannot be found (%s)' %
                          (class_str,
                           traceback.format_exception(*sys.exc_info())))
