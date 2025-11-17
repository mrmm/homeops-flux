"""
Proxmox API Client wrapper for VM management operations.
"""
import logging
from typing import Dict, List, Optional, Any
from proxmoxer import ProxmoxAPI
from proxmoxer.core import ResourceException

logger = logging.getLogger(__name__)


class ProxmoxClient:
    """Wrapper for Proxmox API operations."""

    def __init__(self, host: str, user: str, password: str = None, token_name: str = None,
                 token_value: str = None, verify_ssl: bool = True):
        """
        Initialize Proxmox API client.

        Args:
            host: Proxmox host address
            user: Username (format: user@realm)
            password: Password for user authentication
            token_name: API token name (alternative to password)
            token_value: API token value (alternative to password)
            verify_ssl: Whether to verify SSL certificates
        """
        self.host = host
        self.verify_ssl = verify_ssl

        if token_name and token_value:
            self.proxmox = ProxmoxAPI(
                host,
                user=user,
                token_name=token_name,
                token_value=token_value,
                verify_ssl=verify_ssl
            )
        elif password:
            self.proxmox = ProxmoxAPI(
                host,
                user=user,
                password=password,
                verify_ssl=verify_ssl
            )
        else:
            raise ValueError("Either password or token credentials must be provided")

        logger.info(f"Connected to Proxmox cluster at {host}")

    def get_cluster_nodes(self) -> List[Dict[str, Any]]:
        """Get list of all nodes in the cluster."""
        try:
            nodes = self.proxmox.nodes.get()
            logger.debug(f"Found {len(nodes)} nodes in cluster")
            return nodes
        except ResourceException as e:
            logger.error(f"Failed to get cluster nodes: {e}")
            return []

    def get_node_status(self, node: str) -> Optional[Dict[str, Any]]:
        """Get status information for a specific node."""
        try:
            status = self.proxmox.nodes(node).status.get()
            return status
        except ResourceException as e:
            logger.error(f"Failed to get status for node {node}: {e}")
            return None

    def get_node_resources(self, node: str) -> Optional[Dict[str, Any]]:
        """
        Get resource usage for a node.

        Returns:
            Dict with keys: cpu_usage, mem_usage, mem_total, mem_free, disk_usage, etc.
        """
        status = self.get_node_status(node)
        if not status:
            return None

        return {
            'cpu_count': status.get('cpuinfo', {}).get('cpus', 0),
            'cpu_usage': status.get('cpu', 0),  # 0-1 range
            'mem_total': status.get('memory', {}).get('total', 0),
            'mem_used': status.get('memory', {}).get('used', 0),
            'mem_free': status.get('memory', {}).get('free', 0),
            'mem_usage': status.get('memory', {}).get('used', 0) / max(status.get('memory', {}).get('total', 1), 1),
            'uptime': status.get('uptime', 0),
            'status': status.get('status', 'unknown')
        }

    def get_all_vms(self) -> List[Dict[str, Any]]:
        """Get all VMs across all nodes in the cluster."""
        vms = []
        nodes = self.get_cluster_nodes()

        for node in nodes:
            node_name = node['node']
            try:
                node_vms = self.proxmox.nodes(node_name).qemu.get()
                for vm in node_vms:
                    vm['node'] = node_name
                    vms.append(vm)
            except ResourceException as e:
                logger.error(f"Failed to get VMs from node {node_name}: {e}")

        logger.debug(f"Found {len(vms)} VMs across cluster")
        return vms

    def get_vm_config(self, node: str, vmid: int) -> Optional[Dict[str, Any]]:
        """Get VM configuration including notes and tags."""
        try:
            config = self.proxmox.nodes(node).qemu(vmid).config.get()
            return config
        except ResourceException as e:
            logger.error(f"Failed to get config for VM {vmid} on node {node}: {e}")
            return None

    def get_vm_status(self, node: str, vmid: int) -> Optional[Dict[str, Any]]:
        """Get current status of a VM."""
        try:
            status = self.proxmox.nodes(node).qemu(vmid).status.current.get()
            return status
        except ResourceException as e:
            logger.error(f"Failed to get status for VM {vmid} on node {node}: {e}")
            return None

    def start_vm(self, node: str, vmid: int) -> bool:
        """Start a VM."""
        try:
            self.proxmox.nodes(node).qemu(vmid).status.start.post()
            logger.info(f"Started VM {vmid} on node {node}")
            return True
        except ResourceException as e:
            logger.error(f"Failed to start VM {vmid} on node {node}: {e}")
            return False

    def stop_vm(self, node: str, vmid: int, force: bool = False) -> bool:
        """Stop a VM."""
        try:
            if force:
                self.proxmox.nodes(node).qemu(vmid).status.stop.post(forceStop=1)
            else:
                self.proxmox.nodes(node).qemu(vmid).status.shutdown.post()
            logger.info(f"Stopped VM {vmid} on node {node}")
            return True
        except ResourceException as e:
            logger.error(f"Failed to stop VM {vmid} on node {node}: {e}")
            return False

    def migrate_vm(self, node: str, vmid: int, target_node: str, online: bool = False) -> bool:
        """
        Migrate a VM to another node.

        Args:
            node: Current node hosting the VM
            vmid: VM ID
            target_node: Target node to migrate to
            online: Whether to perform online (live) migration
        """
        try:
            params = {
                'target': target_node,
                'online': 1 if online else 0
            }
            self.proxmox.nodes(node).qemu(vmid).migrate.post(**params)
            logger.info(f"Migrating VM {vmid} from {node} to {target_node} (online={online})")
            return True
        except ResourceException as e:
            logger.error(f"Failed to migrate VM {vmid} from {node} to {target_node}: {e}")
            return False

    def get_node_cpu_info(self, node: str) -> Optional[Dict[str, Any]]:
        """Get CPU information for a node."""
        status = self.get_node_status(node)
        if not status:
            return None

        cpu_info = status.get('cpuinfo', {})
        return {
            'model': cpu_info.get('model', 'unknown'),
            'cpus': cpu_info.get('cpus', 0),
            'cores': cpu_info.get('cores', 0),
            'sockets': cpu_info.get('sockets', 0),
            'flags': cpu_info.get('flags', '')
        }
