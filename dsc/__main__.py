import os
import sys

from dsc.const import DOCKER_MACHINE_BIN, DOCKER_COMPOSE_BIN, DOCKER_BIN, CONFIG_FILENAME
from dsc.core import DSC, Config
from dsc.startup import load_config_file, get_arguments, ensure_config_path


def bootstrap(args):
    config_dir = os.path.join(os.getcwd(), args.config)
    ensure_config_path(config_dir)

    # Check for docker-machine
    if DOCKER_MACHINE_BIN is None:
        print("Docker Machine not found! Refer to the Docker manual on how to install it for your platform.")
        sys.exit(1)

    # Check for docker-compose
    if DOCKER_COMPOSE_BIN is None:
        print("Docker Compose not found! Refer to the Docker manual on how to install it for your platform.")
        sys.exit(1)

    # Check for docker
    if DOCKER_BIN is None:
        print("Docker not found! Refer to the Docker manual on how to install it for your platform.")
        sys.exit(1)

    app = DSC()
    app.config = Config()
    app.config.config_dir = config_dir
    app.config.machine_bin = DOCKER_MACHINE_BIN
    app.config.compose_bin = DOCKER_COMPOSE_BIN
    app.config.docker_bin = DOCKER_BIN

    app = load_config_file(app.config.path(config_dir, CONFIG_FILENAME), app)

    return app


def main():
    args = get_arguments()

    app = bootstrap(args)
    app.start()


if __name__ == "__main__":
    sys.exit(main())
