"""
VM Manager - Monitors VMs and handles auto-start with intelligent placement.
"""
import logging
import time
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
from proxmox_client import ProxmoxClient
from vm_requirements import VMRequirements
from node_selector import NodeSelector

logger = logging.getLogger(__name__)


class VMManager:
    """Manages VM auto-start and intelligent placement."""

    def __init__(self, proxmox_client: ProxmoxClient, config: Dict[str, Any]):
        """
        Initialize VM Manager.

        Args:
            proxmox_client: ProxmoxClient instance
            config: Configuration dict
        """
        self.proxmox = proxmox_client
        self.node_selector = NodeSelector(proxmox_client)
        self.config = config

        # State tracking
        self.known_vms: Dict[int, Dict[str, Any]] = {}  # vmid -> last known state
        self.startup_attempts: Dict[int, List[datetime]] = {}  # vmid -> list of attempt times
        self.migration_in_progress: Set[int] = set()  # vmids currently being migrated

        # Configuration
        self.monitor_interval = config.get('monitor_interval_seconds', 30)
        self.max_startup_attempts = config.get('max_startup_attempts', 3)
        self.startup_attempt_window = config.get('startup_attempt_window_seconds', 300)  # 5 minutes
        self.auto_start_enabled = config.get('auto_start_enabled', True)
        self.auto_migrate_enabled = config.get('auto_migrate_enabled', True)
        self.migration_threshold = config.get('migration_threshold_score', 20.0)

        # VM filters
        self.managed_tags = config.get('managed_tags', ['auto-start', 'managed'])
        self.excluded_tags = config.get('excluded_tags', ['no-auto-start'])

    def is_vm_managed(self, vm_config: Dict[str, Any]) -> bool:
        """
        Check if a VM should be managed by this system.

        Args:
            vm_config: VM configuration

        Returns:
            True if VM should be managed
        """
        tags_str = vm_config.get('tags', '')
        tags = [t.strip() for t in tags_str.split(';') if t.strip()]

        # Check excluded tags first
        for excluded_tag in self.excluded_tags:
            if excluded_tag in tags:
                return False

        # Check if any managed tag is present
        for managed_tag in self.managed_tags:
            if managed_tag in tags:
                return True

        return False

    def can_attempt_startup(self, vmid: int) -> bool:
        """
        Check if we can attempt to start a VM based on retry limits.

        Args:
            vmid: VM ID

        Returns:
            True if startup can be attempted
        """
        if vmid not in self.startup_attempts:
            return True

        # Clean up old attempts outside the window
        now = datetime.now()
        cutoff = now.timestamp() - self.startup_attempt_window
        self.startup_attempts[vmid] = [
            attempt for attempt in self.startup_attempts[vmid]
            if attempt.timestamp() > cutoff
        ]

        # Check if we're within the limit
        recent_attempts = len(self.startup_attempts[vmid])
        if recent_attempts >= self.max_startup_attempts:
            logger.warning(
                f"VM {vmid} has {recent_attempts} startup attempts in the last "
                f"{self.startup_attempt_window}s, skipping"
            )
            return False

        return True

    def record_startup_attempt(self, vmid: int):
        """Record a startup attempt for a VM."""
        if vmid not in self.startup_attempts:
            self.startup_attempts[vmid] = []
        self.startup_attempts[vmid].append(datetime.now())

    def handle_stopped_vm(self, vmid: int, node: str, vm_config: Dict[str, Any]):
        """
        Handle a VM that has stopped - potentially start it on best node.

        Args:
            vmid: VM ID
            node: Current node
            vm_config: VM configuration
        """
        if not self.auto_start_enabled:
            logger.debug(f"Auto-start disabled, skipping VM {vmid}")
            return

        if vmid in self.migration_in_progress:
            logger.info(f"VM {vmid} migration in progress, skipping")
            return

        if not self.can_attempt_startup(vmid):
            return

        logger.info(f"Handling stopped VM {vmid} on node {node}")

        # Parse VM requirements
        vm_req = VMRequirements(vm_config)

        # Check if current node has resources
        current_resources = self.proxmox.get_node_resources(node)
        current_cpu_info = self.proxmox.get_node_cpu_info(node)

        can_start_here = False
        if current_resources and current_cpu_info:
            matches, reasons = vm_req.matches_node(node, current_cpu_info, current_resources)
            can_start_here = matches
            logger.info(f"Current node {node} suitable: {matches} - {', '.join(reasons)}")

        target_node = node
        needs_migration = False

        if not can_start_here:
            # Current node cannot host this VM, find a better one
            logger.info(f"Current node {node} cannot host VM {vmid}, finding alternative")
            best_node = self.node_selector.select_best_node(vm_req, current_node=node)

            if not best_node:
                logger.error(f"No suitable node found for VM {vmid}, cannot start")
                self.record_startup_attempt(vmid)
                return

            target_node = best_node
            needs_migration = True
        else:
            # Current node can host VM, but check if there's a significantly better option
            if self.auto_migrate_enabled:
                should_migrate, best_node, reason = self.node_selector.needs_migration(
                    vm_config, node, self.migration_threshold
                )
                if should_migrate and best_node:
                    logger.info(f"Better node available for VM {vmid}: {best_node} - {reason}")
                    target_node = best_node
                    needs_migration = True

        # Perform migration if needed (offline migration since VM is stopped)
        if needs_migration and target_node != node:
            logger.info(f"Migrating VM {vmid} from {node} to {target_node}")
            self.migration_in_progress.add(vmid)

            success = self.proxmox.migrate_vm(node, vmid, target_node, online=False)

            self.migration_in_progress.discard(vmid)

            if not success:
                logger.error(f"Failed to migrate VM {vmid} to {target_node}")
                self.record_startup_attempt(vmid)
                return

            logger.info(f"Successfully migrated VM {vmid} to {target_node}")
            # Give migration some time to complete
            time.sleep(5)

        # Start the VM on the target node
        logger.info(f"Starting VM {vmid} on node {target_node}")
        self.record_startup_attempt(vmid)

        success = self.proxmox.start_vm(target_node, vmid)

        if success:
            logger.info(f"Successfully started VM {vmid} on {target_node}")
        else:
            logger.error(f"Failed to start VM {vmid} on {target_node}")

    def detect_state_changes(self) -> List[Dict[str, Any]]:
        """
        Detect VMs that have changed state since last check.

        Returns:
            List of VMs with state changes
        """
        changes = []

        # Get all current VMs
        all_vms = self.proxmox.get_all_vms()

        for vm in all_vms:
            vmid = vm['vmid']
            current_status = vm.get('status', 'unknown')
            node = vm.get('node')

            # Get VM config to check if it's managed
            vm_config = self.proxmox.get_vm_config(node, vmid)
            if not vm_config:
                continue

            if not self.is_vm_managed(vm_config):
                continue

            # Check if this is a new VM or state changed
            if vmid not in self.known_vms:
                logger.debug(f"Discovered new managed VM {vmid} with status {current_status}")
                self.known_vms[vmid] = {
                    'status': current_status,
                    'node': node,
                    'config': vm_config
                }
                continue

            previous_status = self.known_vms[vmid].get('status')

            if current_status != previous_status:
                logger.info(f"VM {vmid} state changed: {previous_status} -> {current_status}")

                changes.append({
                    'vmid': vmid,
                    'node': node,
                    'previous_status': previous_status,
                    'current_status': current_status,
                    'config': vm_config
                })

                # Update known state
                self.known_vms[vmid] = {
                    'status': current_status,
                    'node': node,
                    'config': vm_config
                }

        return changes

    def monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Starting VM monitoring loop")

        while True:
            try:
                # Detect state changes
                changes = self.detect_state_changes()

                # Handle each change
                for change in changes:
                    vmid = change['vmid']
                    current_status = change['current_status']
                    previous_status = change['previous_status']
                    node = change['node']
                    vm_config = change['config']

                    # If VM transitioned to stopped state, handle it
                    if current_status == 'stopped' and previous_status in ['running', 'unknown']:
                        logger.info(f"VM {vmid} stopped, initiating auto-start logic")
                        self.handle_stopped_vm(vmid, node, vm_config)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)

            # Sleep until next check
            logger.debug(f"Sleeping for {self.monitor_interval} seconds")
            time.sleep(self.monitor_interval)

    def run(self):
        """Run the VM manager."""
        logger.info("VM Manager starting")
        logger.info(f"Auto-start enabled: {self.auto_start_enabled}")
        logger.info(f"Auto-migrate enabled: {self.auto_migrate_enabled}")
        logger.info(f"Managed tags: {self.managed_tags}")
        logger.info(f"Monitor interval: {self.monitor_interval}s")

        try:
            self.monitor_loop()
        except KeyboardInterrupt:
            logger.info("VM Manager shutting down (KeyboardInterrupt)")
        except Exception as e:
            logger.error(f"VM Manager crashed: {e}", exc_info=True)
            raise
