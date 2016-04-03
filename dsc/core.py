import re
import sys
from typing import List

from dsc.const import *
from dsc.nodes import NodeType, Node, NodeState
from dsc.startup import get_default_config_dir
from dsc.util import dict_has_item, get_machine_config, run_command, get_env_for_node, \
    save_machine_config, write_file, read_file


class DSC(object):
    def __init__(self):
        self.config = Config()
        self.masters = None
        self.workers = None

    def start(self) -> None:
        """
        Create and configure the swarm
        """
        self.masters = self._create_nodes(NodeType.master)
        print("Swarm master(s): {}".format(", ".join([node.name for node in self.masters])))

        self.workers = self._create_nodes(NodeType.worker)
        print("Swarm worker(s): {}".format(", ".join([node.name for node in self.workers])))

        print("Creating swarm master(s)...")
        self._create_machines(self.masters)

        print("Creating swarm worker(s)...")
        self._create_machines(self.workers)

        print("All done!")

    def _create_machines(self, nodes: List[Node]) -> None:
        """
        Create and configure machines
        :param nodes:
        """
        for node in nodes:
            self._create_machine(node)
        for node in nodes:
            self._config_machine(node)

    def _create_machine(self, node: Node) -> None:
        """
        Create a new machine
        :param node:
        """
        if node.config["machine-driver"] not in MACHINE_DRIVERS:
            print("Machine driver not supported/valid: {}".format(node.config["machine-driver"]))
            sys.exit(1)

        print("* create {}: {}".format(node.name, node.config["machine-driver"]))

        # Set machine path
        node.machine_path = os.path.join(os.path.expanduser("~"), ".docker", "machine", "machines", node.name)

        # Determine current state of the node
        node.state = self._get_state(node)
        print("+ current state: {}".format(node.state.name.upper()))

        try:
            if node.state == NodeState.new:
                options = {
                    "driver": node.config["machine-driver"],
                    "driver_options": node.config["driver-opts"] if node.config["driver-opts"] is not None else "",
                    "engine_options": node.config["engine-opts"] if node.config["engine-opts"] is not None else "",
                    "name": node.name
                }
                self._run_machine("create -d {driver} {driver_options} {engine_options} {name}".format(**options))
                node.state = NodeState.bare

            node = self._save_node_data(node)
            print("+ public IP: {}, cluster IP: {}".format(node.public_ip, node.cluster_ip))
        except RuntimeError as rte:
            print("Failed to create machine: {}".format(rte))
            sys.exit(1)

    def _config_machine(self, node: Node) -> None:
        """
        Configure a machine as a swarm master or worker
        :param node:
        """
        print("* configure {}: {}".format(node.name, node.config["machine-driver"]))

        # Determine current state of the node
        node.state = self._get_state(node)
        print("+ current state: {}".format(node.state.name.upper()))

        # Setup and start consul
        self._setup_consul(node)

        # Set up DNS (/etc/resolv.conf)
        print("+ setup DNS")
        self._run_machine(
            "ssh {} 'sudo rm -f /etc/resolv.conf && sudo echo \"nameserver {}\" | sudo tee /etc/resolv.conf'".format(
                node.name, node.cluster_ip))

        # Global config
        if node.state == NodeState.swarm_running:
            return

        self._update_machine_config(node)

        # Make sure docker is still running
        self._run_machine("ssh {node} 'sudo systemctl start docker || sudo /etc/init.d/docker start'".format(node=node.name), raise_error=False,
                          show_output=False)

        # Somehow the provisioning fails when the consul image is still running on nodes except the primary master
        if not node.is_primary:
            self._run_machine("ssh {node} 'docker stop consul-agent-server consul-agent'".format(node=node.name),
                              raise_error=False, show_output=False)

        # Re-provision node
        try:
            self._run_machine("provision {}".format(node.name))
        except RuntimeError as rte:
            print("Error provisioning node: {}".format(rte))

    def _update_machine_config(self, node: Node) -> None:
        """
        Update docker-machine config (config.json) with swarm config
        :param node:
        """
        machine_config = get_machine_config(node)
        consul_service = CONSUL_SERVICE.format(domain=node.domain)
        engine_values = [node.cluster_iface, consul_service, node.cluster_ip, node.domain]
        engine_options = machine_config["HostOptions"]["EngineOptions"]
        engine_options["ArbitraryFlags"].extend(
            [option.format(value) for option, value in zip(ENGINE_OPTIONS, engine_values)])
        machine_config["HostOptions"]["EngineOptions"] = engine_options
        driver_options = machine_config["Driver"]
        driver_options["SwarmDiscovery"] = consul_service
        swarm_options = machine_config["HostOptions"]["SwarmOptions"]
        swarm_options["Discovery"] = consul_service
        swarm_options["IsSwarm"] = True
        auth_options = machine_config["HostOptions"]["AuthOptions"]
        tls_sans = [
            node.shortname,
            node.cluster_ip,
        ]
        if node.cluster_ip != node.public_ip:
            tls_sans.append(node.public_ip)
        auth_options["ServerCertSANs"].extend(tls_sans)
        if node.node_type == NodeType.master:
            driver_options["SwarmMaster"] = True
            swarm_options["Master"] = True
            swarm_options["ArbitraryFlags"].extend(
                [option.format(node.cluster_ip) for option in SWARM_MASTER_OPTIONS])
        machine_config["Driver"] = driver_options
        machine_config["HostOptions"]["SwarmOptions"] = swarm_options
        machine_config["HostOptions"]["AuthOptions"] = auth_options
        save_machine_config(node, machine_config)

    def _create_nodes(self, node_type: NodeType) -> List[Node]:
        """
        Create a list of nodes of specified type
        :param node_type:
        :return: nodes
        """
        nodes = [Node.load(name="{}.{}".format(name, self.config.network["cluster-domain"]), config=config,
                           shortname=name, node_type=node_type, domain=self.config.network["cluster-domain"])
                 for name, config in self.config.nodes.items()
                 if dict_has_item(config, "type", node_type.name)]

        if len(nodes) == 0:
            print("No swarm {nodetype} configured. Please add at least one node with type: {nodetype}".format(
                nodetype=node_type.name))
            sys.exit(1)

        # Set the first master node as primary
        if node_type == NodeType.master:
            nodes[0].is_primary = True

        return nodes

    def _setup_consul(self, node: Node) -> None:
        """
        Setup Consul on a node
        :param node:
        """
        print("+ setup consul")
        files = [
            "ca.pem",
            "server.pem",
            "server-key.pem",
        ]

        for file in files:
            self._run_machine("scp {machine_path}/{file} {node}:/tmp/".format(machine_path=node.machine_path, file=file,
                                                                              node=node.name))

        self._run_machine("ssh {node} 'sudo mv /tmp/*.pem /etc/docker/'".format(node=node.name))

        # Get compose dir of consul
        compose_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "compose", "consul"))

        # Copy consul config
        consul_config = os.path.join(compose_dir, "config", "consul.json")
        self._run_machine("scp {consul_config} {node}:/tmp/".format(consul_config=consul_config, node=node.name))
        self._run_machine("ssh {node} 'sudo mkdir -p /etc/consul/ && sudo mv /tmp/consul.json /etc/consul/'".format(
            node=node.name))

        # Set up compose file and start consul
        self._build_consul_compose_file(node, compose_dir)

    def _build_consul_compose_file(self, node: Node, compose_dir: str) -> None:
        """
        Create the Consul docker-compose file for this node
        :param node:
        :param compose_dir:
        """
        if node.node_type == NodeType.master:
            compose_data = read_file(os.path.join(compose_dir, "server.yml"))
            compose_file = os.path.join(node.machine_path, "consul-server.yml")
            retry_join = ""

            if len(self.masters) > 1:
                params = ["-retry-interval 10s", "-retry-max 3"]
                params.extend(["--retry-join {cluster_ip}".format(cluster_ip=master.cluster_ip)
                               for master in self.masters if node.name != master.name])

                retry_join = " ".join(params)

            write_file(compose_file,
                       compose_data.format(master_count=len(self.masters), cluster_ip=node.cluster_ip,
                                           domain=node.domain, retry_join=retry_join, nodename=node.shortname))
        else:
            compose_data = read_file(os.path.join(compose_dir, "agent.yml"))
            compose_file = os.path.join(node.machine_path, "consul-agent.yml")
            params = ["-retry-interval 10s"]
            for master in self.masters:
                params.append("-retry-join {cluster_ip}".format(cluster_ip=master.cluster_ip))

            retry_join = " ".join(params)
            write_file(os.path.join(node.machine_path, compose_file),
                       compose_data.format(cluster_ip=node.cluster_ip, domain=node.domain, retry_join=retry_join,
                                           nodename=node.shortname))

        self.start_consul(node, compose_file, restart=(node.state == NodeState.swarm_running))

    def start_consul(self, node: Node, compose_file: str, restart: bool = False) -> None:
        """
        Start or restart Consul on node
        :param node:
        :param compose_file:
        :param restart:
        """
        print("+ start consul")
        compose_command = "restart" if restart else "up -d"
        try:
            self._run_compose("-f {} {}".format(os.path.join(node.machine_path, compose_file), compose_command),
                              env=get_env_for_node(node))
        except RuntimeError as rte:
            print("Start consul failed: {}".format(rte))

    def _save_node_data(self, node: Node) -> Node:
        """
        Save machine data to node
        :param node:
        :return:
        """
        node.public_ip = self._run_machine("ip {}".format(node.name), show_output=False)
        node.cluster_iface = node.config.get("cluster-interface", DEFAULT_CLUSTER_INTERFACE)

        result = self._run_machine("ssh {} \"ip addr sh {} | awk '/inet / {{ print \$2 }}'\"".format(
            node.name, node.cluster_iface),
            use_shell=True, show_output=False)

        node.cluster_ip = re.sub("/[0-9]+$", "", result)

        return node

    def _get_state(self, node: Node) -> NodeState:
        """
        Get state of a node
        :param node:
        :return:
        """
        state = NodeState.new
        # Check if the machine exists
        if os.path.isdir(os.path.join(os.path.expanduser("~"), ".docker", "machine", "machines", node.name)):
            state = NodeState.bare

        # Check if docker is running
        try:
            self._run_docker("info", show_output=False, env=get_env_for_node(node))
            state = NodeState.running
        except RuntimeError:
            pass

        # Check if swarm has been configured
        try:
            swarm_options = get_machine_config(node, True)["HostOptions"]["SwarmOptions"]
            if not swarm_options["IsSwarm"]:
                return state
        except FileNotFoundError:
            return state

        state = NodeState.swarm_configured

        # If docker is running on a worker node and swarm is configured, we assume swarm is running (might need a
        # better way to determine this in the future)
        if node.node_type == NodeType.worker and state.value >= NodeState.running.value:
            return NodeState.swarm_running

        # Check if docker swarm is running on the masters
        try:
            self._run_docker("info", show_output=False, env=get_env_for_node(node, True))
            return NodeState.swarm_running
        except RuntimeError:
            return state

    def _run_machine(self, command, raise_error=True, use_shell=False, show_output=True, env=None):
        return run_command(self.config.machine_bin, command, raise_error, use_shell, show_output, env)

    def _run_compose(self, command, raise_error=True, use_shell=False, show_output=True, env=None):
        return run_command(self.config.compose_bin, command, raise_error, use_shell, show_output, env)

    def _run_docker(self, command, raise_error=True, use_shell=False, show_output=True, env=None):
        return run_command(self.config.docker_bin, command, raise_error, use_shell, show_output, env)


class Config(object):
    def __init__(self):
        self.nodes = None
        self.machine_bin = None
        self.compose_bin = None
        self.docker_bin = None
        self.network = None
        self.config_dir = get_default_config_dir()

    def path(self, *path):
        return os.path.join(self.config_dir, *path)

    def from_dict(self, config_dict: dict):
        self.nodes = config_dict.get("nodes", {})
        self.network = config_dict.get("network", {})
