"""
Node Selector - Intelligent node selection based on resources and requirements.
"""
import logging
from typing import Dict, List, Optional, Any, Tuple
from vm_requirements import VMRequirements

logger = logging.getLogger(__name__)


class NodeSelector:
    """Select optimal node for VM placement based on requirements and resources."""

    def __init__(self, proxmox_client):
        """
        Initialize node selector.

        Args:
            proxmox_client: ProxmoxClient instance
        """
        self.proxmox = proxmox_client

    def calculate_node_score(self, node_name: str, node_resources: Dict[str, Any],
                            vm_requirements: VMRequirements) -> float:
        """
        Calculate a score for a node (higher is better).

        Scoring factors:
        - Available memory (weight: 0.4)
        - CPU availability (weight: 0.3)
        - VM affinity (weight: 0.2)
        - Overall load balance (weight: 0.1)

        Returns:
            Score between 0-100
        """
        score = 0.0

        # Memory score (0-40 points)
        mem_total = node_resources.get('mem_total', 1)
        mem_free = node_resources.get('mem_free', 0)
        mem_usage_ratio = node_resources.get('mem_usage', 1.0)

        # Prefer nodes with more free memory relative to total
        # Invert usage ratio to get free ratio
        mem_free_ratio = 1.0 - mem_usage_ratio
        memory_score = mem_free_ratio * 40

        # CPU score (0-30 points)
        cpu_usage = node_resources.get('cpu_usage', 1.0)
        # Prefer nodes with lower CPU usage
        cpu_score = (1.0 - cpu_usage) * 30

        # Affinity score (0-20 points)
        affinity_raw_score = vm_requirements.get_affinity_score(node_name)
        affinity_score = (affinity_raw_score / 100) * 20

        # Load balance score (0-10 points)
        # Prefer nodes that are more "empty" to balance the cluster
        overall_usage = (mem_usage_ratio + cpu_usage) / 2
        balance_score = (1.0 - overall_usage) * 10

        total_score = memory_score + cpu_score + affinity_score + balance_score

        logger.debug(
            f"Node {node_name} score breakdown: "
            f"memory={memory_score:.1f}, cpu={cpu_score:.1f}, "
            f"affinity={affinity_score:.1f}, balance={balance_score:.1f}, "
            f"total={total_score:.1f}"
        )

        return total_score

    def get_candidate_nodes(self, vm_requirements: VMRequirements,
                           exclude_nodes: Optional[List[str]] = None) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Get list of candidate nodes that can host the VM, sorted by score.

        Args:
            vm_requirements: VM requirements object
            exclude_nodes: List of node names to exclude

        Returns:
            List of tuples: (node_name, score, node_info)
            Sorted by score (highest first)
        """
        exclude_nodes = exclude_nodes or []
        candidates = []

        # Get all nodes in cluster
        nodes = self.proxmox.get_cluster_nodes()

        for node in nodes:
            node_name = node['node']

            # Skip if node is not online
            if node.get('status') != 'online':
                logger.debug(f"Skipping node {node_name}: not online (status={node.get('status')})")
                continue

            # Skip excluded nodes
            if node_name in exclude_nodes:
                logger.debug(f"Skipping node {node_name}: in exclude list")
                continue

            # Get node resources and CPU info
            node_resources = self.proxmox.get_node_resources(node_name)
            if not node_resources:
                logger.warning(f"Could not get resources for node {node_name}")
                continue

            node_cpu_info = self.proxmox.get_node_cpu_info(node_name)
            if not node_cpu_info:
                logger.warning(f"Could not get CPU info for node {node_name}")
                continue

            # Check if node meets requirements
            matches, reasons = vm_requirements.matches_node(node_name, node_cpu_info, node_resources)

            if not matches:
                logger.debug(f"Node {node_name} doesn't match requirements: {', '.join(reasons)}")
                continue

            # Calculate score for this node
            score = self.calculate_node_score(node_name, node_resources, vm_requirements)

            candidates.append((
                node_name,
                score,
                {
                    'resources': node_resources,
                    'cpu_info': node_cpu_info,
                    'reasons': reasons
                }
            ))

        # Sort by score (highest first)
        candidates.sort(key=lambda x: x[1], reverse=True)

        logger.info(f"Found {len(candidates)} candidate nodes for VM {vm_requirements.vmid}")
        for i, (node_name, score, _) in enumerate(candidates[:5]):  # Log top 5
            logger.info(f"  {i+1}. {node_name}: score={score:.1f}")

        return candidates

    def select_best_node(self, vm_requirements: VMRequirements,
                        current_node: Optional[str] = None) -> Optional[str]:
        """
        Select the best node for a VM.

        Args:
            vm_requirements: VM requirements
            current_node: Current node (will be excluded from candidates)

        Returns:
            Best node name, or None if no suitable node found
        """
        exclude = [current_node] if current_node else []
        candidates = self.get_candidate_nodes(vm_requirements, exclude_nodes=exclude)

        if not candidates:
            logger.warning(f"No suitable nodes found for VM {vm_requirements.vmid}")
            return None

        best_node, best_score, info = candidates[0]
        logger.info(f"Selected node {best_node} for VM {vm_requirements.vmid} (score={best_score:.1f})")

        return best_node

    def needs_migration(self, vm_config: Dict[str, Any], current_node: str,
                       threshold_score_diff: float = 20.0) -> Tuple[bool, Optional[str], str]:
        """
        Determine if a VM should be migrated to a better node.

        Args:
            vm_config: VM configuration
            current_node: Current node hosting the VM
            threshold_score_diff: Minimum score difference to trigger migration

        Returns:
            Tuple of (should_migrate: bool, target_node: Optional[str], reason: str)
        """
        vm_req = VMRequirements(vm_config)

        # Get current node score
        current_resources = self.proxmox.get_node_resources(current_node)
        if not current_resources:
            return False, None, f"Could not get resources for current node {current_node}"

        current_cpu_info = self.proxmox.get_node_cpu_info(current_node)
        if not current_cpu_info:
            return False, None, f"Could not get CPU info for current node {current_node}"

        # Check if current node still meets requirements
        matches, reasons = vm_req.matches_node(current_node, current_cpu_info, current_resources)
        if not matches:
            # Current node doesn't meet requirements - must migrate
            best_node = self.select_best_node(vm_req, current_node=current_node)
            if best_node:
                return True, best_node, f"Current node doesn't meet requirements: {', '.join(reasons)}"
            else:
                return False, None, f"Current node doesn't meet requirements but no alternative found"

        current_score = self.calculate_node_score(current_node, current_resources, vm_req)

        # Find best alternative node
        candidates = self.get_candidate_nodes(vm_req, exclude_nodes=[current_node])
        if not candidates:
            return False, None, "No alternative nodes available"

        best_node, best_score, _ = candidates[0]

        # Only migrate if there's a significant improvement
        score_diff = best_score - current_score
        if score_diff >= threshold_score_diff:
            return True, best_node, f"Better node available (score improvement: {score_diff:.1f})"

        return False, None, f"Current node is optimal (score={current_score:.1f})"
