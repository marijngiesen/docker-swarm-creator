from enum import Enum


class Node(object):
    def __init__(self):
        self.name = None
        self.shortname = None
        self.node_type = None
        self.state = NodeState.new
        self.public_ip = None
        self.cluster_ip = None
        self.cluster_iface = None
        self.is_primary = False
        self.domain = None
        self.config = None
        self.machine_path = None

    @classmethod
    def load(cls, **kwargs):
        node = cls()
        node.__dict__.update(kwargs)
        return node


class NodeType(Enum):
    master = 1
    worker = 2


class NodeState(Enum):
    new = 1
    bare = 2
    running = 3
    swarm_configured = 4
    swarm_running = 5
