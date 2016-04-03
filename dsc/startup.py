import argparse
import os
import sys
from collections import defaultdict

from dsc.util import load_yaml


def get_default_config_dir():
    return "{}/{}".format(os.getcwd(), "config")


def get_arguments(description: str = None):
    parser = argparse.ArgumentParser(
        description=description)
    parser.add_argument(
        "-c", "--config",
        metavar="path_to_config_dir",
        default=get_default_config_dir(),
        help="Directory that contains the configuration")

    return parser.parse_args()


def ensure_config_path(config_dir: str):
    # Test if configuration directory exists
    if not os.path.isdir(config_dir):
        if config_dir != get_default_config_dir():
            print("Fatal Error: Specified configuration directory does not exist {} ".format(config_dir))
            sys.exit(1)

        try:
            os.mkdir(config_dir)
        except OSError:
            print("Fatal Error: Unable to create default configuration directory {}".format(config_dir))
            sys.exit(1)


def load_yaml_config_file(config_path):
    conf_dict = load_yaml(config_path)

    if not isinstance(conf_dict, dict):
        print("The configuration file {} does not contain a dictionary".format(os.path.basename(config_path)))
        raise ValueError()

    return conf_dict


def load_config_file(config_path, app):
    # Set config dir to directory holding config file
    config_dir = os.path.abspath(os.path.dirname(config_path))
    app.config.config_dir = config_dir

    config_dict = load_yaml_config_file(config_path)

    # Translate to default dict, so everything has a value
    config = defaultdict(dict, {key: value or {} for key, value in config_dict.items()})
    app.config.from_dict(config)

    return app
