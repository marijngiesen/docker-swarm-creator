import os
import shutil

os.environ["PATH"] += ":/usr/local/bin"
CONFIG_FILENAME = "dsc.yaml"
DOCKER_MACHINE_BIN = shutil.which("docker-machine")
DOCKER_COMPOSE_BIN = shutil.which("docker-compose")
DOCKER_BIN = shutil.which("docker")

DEFAULT_CLUSTER_INTERFACE = "eth1"

MACHINE_DRIVERS = [
    "amazonec2", "azure", "digitalocean", "exoscale", "generic", "google", "hyperv", "openstack",
    "rackspace", "softlayer", "virtualbox", "vmwarevcloudair", "vmwarefusion", "vmwarevsphere"
]

CONSUL_SERVICE = "consul://consul.service.{domain}:8500"

SWARM_MASTER_OPTIONS = [
    "replication=true",
    "advertise={}:3376",
]

ENGINE_OPTIONS = [
    "cluster-advertise={}:2376",
    "cluster-store={}",
    "dns={}",
    "dns-search={}",
]

SWARM_OPTIONS = [
    "tls-san={nodeshortname}",
    "tls-san={nodename}",
    "tls-san={cluster_ip}",
    "tls-san={public_ip}",
]