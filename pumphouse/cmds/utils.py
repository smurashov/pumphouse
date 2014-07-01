import yaml


def safe_load_yaml(filename):
    with open(filename) as f:
        return yaml.safe_load(f)
