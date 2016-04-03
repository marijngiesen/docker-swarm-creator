import json
import os
import re
from collections import OrderedDict

import sys
import yaml
from subprocess import Popen, PIPE, STDOUT


def get_machine_config(node, raise_error=False):
    try:
        with open(os.path.join(node.machine_path, "config.json")) as config_file:
            return json.load(config_file)
    except FileNotFoundError as ex:
        if raise_error: raise
        print("Machine config (config.json) not found: {}".format(ex))
        sys.exit(1)


def save_machine_config(node, config):
    try:
        with open(os.path.join(node.machine_path, "config.json"), "w") as config_file:
            return json.dump(config, config_file)
    except Exception as ex:
        print("Error writing machine config: {}".format(ex))
        sys.exit(1)


def read_file(file):
    try:
        with open(file) as handle:
            return handle.read()
    except FileNotFoundError as ex:
        print("File not found: {}".format(ex))
        sys.exit(1)


def write_file(file, data):
    try:
        with open(file, "w") as handle:
            return handle.write(data)
    except Exception as ex:
        print("Error writing file: {}".format(ex))
        sys.exit(1)


def get_env_for_node(node, is_swarm=False):
    if node.public_ip is None:
        return {}
    return {
        "DOCKER_TLS_VERIFY": "1",
        "DOCKER_HOST": "tcp://{public_ip}:{port}".format(public_ip=node.public_ip, port=2376 if not is_swarm else 3376),
        "DOCKER_CERT_PATH": node.machine_path,
        "DOCKER_MACHINE_NAME": node.name,
    }


def build_command(command):
    command = re.sub(r"\"", "'", command)
    return [part.replace("\x00", " ") for part in
            re.sub("'(.+?)'", lambda m: m.group(1).replace(" ", "\x00"), command).split()]


def run_command(program, command, raise_error=True, use_shell=False, show_output=True, extra_env=None):
    if not use_shell:
        command = re.sub(r"\s+", " ", command)
        command = [program] + build_command(command)
    else:
        command = "{} {}".format(program, command)

    env = os.environ.copy()
    env["PATH"] += ":/usr/local/bin"
    if extra_env is not None:
        env.update(extra_env)

    process = Popen(command, stdin=PIPE, stdout=PIPE, stderr=STDOUT, shell=use_shell, env=env)

    output = ""
    while True:
        nextline = process.stdout.readline()
        if process.poll() is not None:
            break
        output += nextline.decode().strip()
        if show_output:
            sys.stdout.write("++ {}".format(nextline.decode()))
            sys.stdout.flush()

    exit_code = process.returncode

    if exit_code and raise_error:
        raise RuntimeError("command error %s: %s" % (exit_code, output))

    return output


def dict_has_item(data, key, value):
    if key not in data:
        return False

    if data[key] != value:
        return False

    return True


def load_yaml(filename):
    try:
        with open(filename, encoding="utf-8") as conf_file:
            # If configuration file is empty YAML returns None
            # We convert that to an empty dict
            return yaml.safe_load(conf_file) or {}
    except yaml.YAMLError:
        print("Error reading YAML configuration file {}".format(filename))
        return {}
    except FileNotFoundError:
        print("Configuration file not found: {}".format(filename))
        return {}


def _ordered_dict(loader, node):
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node))


yaml.SafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                _ordered_dict)
