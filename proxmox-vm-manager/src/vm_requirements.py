"""
VM Requirements Parser - extracts VM requirements from tags and notes.
"""
import logging
import re
import yaml
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class VMRequirements:
    """Parse and manage VM requirements from config."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize VM requirements from VM config.

        Args:
            config: VM configuration dict from Proxmox API
        """
        self.vmid = config.get('vmid')
        self.name = config.get('name', f'VM-{self.vmid}')
        self.cores = config.get('cores', 1)
        self.memory = config.get('memory', 512)  # MB
        self.tags = self._parse_tags(config.get('tags', ''))
        self.notes = config.get('description', '')

        # Parse requirements from notes and tags
        self.cpu_type = self._extract_cpu_type()
        self.cpu_flags = self._extract_cpu_flags()
        self.min_memory = self._extract_min_memory()
        self.min_cores = self._extract_min_cores()
        self.node_affinity = self._extract_node_affinity()
        self.node_anti_affinity = self._extract_node_anti_affinity()
        self.custom_requirements = self._extract_custom_requirements()

    def _parse_tags(self, tags_str: str) -> List[str]:
        """Parse tags from semicolon-separated string."""
        if not tags_str:
            return []
        return [tag.strip() for tag in tags_str.split(';') if tag.strip()]

    def _extract_cpu_type(self) -> Optional[str]:
        """
        Extract required CPU type from tags or notes.

        Looks for tags like:
        - cpu:host
        - cpu:kvm64
        - cpu-type:x86-64-v3
        """
        # Check tags first
        for tag in self.tags:
            if tag.startswith('cpu:') or tag.startswith('cpu-type:'):
                return tag.split(':', 1)[1]

        # Check notes
        match = re.search(r'cpu[-_]?type:\s*([a-zA-Z0-9\-_]+)', self.notes, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _extract_cpu_flags(self) -> List[str]:
        """
        Extract required CPU flags.

        Looks for tags like:
        - cpu-flags:aes,avx,avx2
        - requires:aes
        """
        flags = []

        # Check tags
        for tag in self.tags:
            if tag.startswith('cpu-flags:'):
                flags_str = tag.split(':', 1)[1]
                flags.extend([f.strip() for f in flags_str.split(',') if f.strip()])
            elif tag.startswith('requires:'):
                req = tag.split(':', 1)[1]
                flags.append(req)

        # Check notes
        match = re.search(r'cpu[-_]?flags:\s*([a-zA-Z0-9,\s\-_]+)', self.notes, re.IGNORECASE)
        if match:
            flags_str = match.group(1)
            flags.extend([f.strip() for f in flags_str.split(',') if f.strip()])

        return list(set(flags))  # Remove duplicates

    def _extract_min_memory(self) -> int:
        """Extract minimum required memory in MB."""
        # Use configured memory as minimum
        min_mem = self.memory

        # Check for explicit requirement in tags
        for tag in self.tags:
            if tag.startswith('min-memory:'):
                try:
                    min_mem = int(tag.split(':', 1)[1])
                except ValueError:
                    pass

        return min_mem

    def _extract_min_cores(self) -> int:
        """Extract minimum required CPU cores."""
        # Use configured cores as minimum
        min_cores = self.cores

        # Check for explicit requirement in tags
        for tag in self.tags:
            if tag.startswith('min-cores:'):
                try:
                    min_cores = int(tag.split(':', 1)[1])
                except ValueError:
                    pass

        return min_cores

    def _extract_node_affinity(self) -> List[str]:
        """
        Extract preferred nodes (affinity).

        Looks for tags like:
        - node:pve01
        - affinity:pve01,pve02
        """
        nodes = []

        for tag in self.tags:
            if tag.startswith('node:'):
                nodes.append(tag.split(':', 1)[1])
            elif tag.startswith('affinity:'):
                nodes_str = tag.split(':', 1)[1]
                nodes.extend([n.strip() for n in nodes_str.split(',') if n.strip()])

        return list(set(nodes))

    def _extract_node_anti_affinity(self) -> List[str]:
        """
        Extract nodes to avoid (anti-affinity).

        Looks for tags like:
        - anti-affinity:pve03
        - exclude:pve04
        """
        nodes = []

        for tag in self.tags:
            if tag.startswith('anti-affinity:') or tag.startswith('exclude:'):
                nodes_str = tag.split(':', 1)[1]
                nodes.extend([n.strip() for n in nodes_str.split(',') if n.strip()])

        return list(set(nodes))

    def _extract_custom_requirements(self) -> Dict[str, Any]:
        """
        Extract custom requirements from YAML in notes.

        Looks for a YAML block in notes like:
        ```yaml
        requirements:
          storage: local-lvm
          network: vmbr0
        ```
        """
        try:
            # Look for YAML code block
            yaml_match = re.search(r'```ya?ml\s*\n(.+?)\n```', self.notes, re.DOTALL | re.IGNORECASE)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                data = yaml.safe_load(yaml_content)
                if isinstance(data, dict) and 'requirements' in data:
                    return data['requirements']
        except Exception as e:
            logger.debug(f"Failed to parse YAML from notes for VM {self.vmid}: {e}")

        return {}

    def matches_node(self, node_name: str, node_cpu_info: Dict[str, Any],
                     node_resources: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Check if a node meets this VM's requirements.

        Args:
            node_name: Name of the node
            node_cpu_info: CPU information from the node
            node_resources: Resource availability on the node

        Returns:
            Tuple of (matches: bool, reasons: List[str])
        """
        reasons = []

        # Check anti-affinity first (hard constraint)
        if node_name in self.node_anti_affinity:
            reasons.append(f"Node {node_name} is in anti-affinity list")
            return False, reasons

        # Check CPU type if specified
        if self.cpu_type:
            node_cpu_model = node_cpu_info.get('model', '').lower()
            required_cpu = self.cpu_type.lower()

            # Simple substring match for now
            # Could be enhanced with better CPU model matching
            if required_cpu not in node_cpu_model and required_cpu != 'host':
                reasons.append(f"CPU type mismatch: requires {self.cpu_type}, node has {node_cpu_info.get('model')}")
                return False, reasons

        # Check CPU flags if specified
        if self.cpu_flags:
            node_flags = node_cpu_info.get('flags', '').lower().split()
            for required_flag in self.cpu_flags:
                if required_flag.lower() not in node_flags:
                    reasons.append(f"Missing CPU flag: {required_flag}")
                    return False, reasons

        # Check available memory
        available_memory_mb = node_resources.get('mem_free', 0) / (1024 * 1024)  # Convert to MB
        if available_memory_mb < self.min_memory:
            reasons.append(f"Insufficient memory: needs {self.min_memory}MB, available {available_memory_mb:.0f}MB")
            return False, reasons

        # Check available CPU cores
        node_cpu_count = node_cpu_info.get('cpus', 0)
        cpu_usage = node_resources.get('cpu_usage', 1.0)

        # Rough estimate: if CPU usage is very high, might not have cores available
        if cpu_usage > 0.95:
            reasons.append(f"CPU heavily loaded: {cpu_usage*100:.1f}% usage")
            return False, reasons

        if node_cpu_count < self.min_cores:
            reasons.append(f"Insufficient CPU cores: needs {self.min_cores}, node has {node_cpu_count}")
            return False, reasons

        # All checks passed
        reasons.append("All requirements met")
        return True, reasons

    def get_affinity_score(self, node_name: str) -> int:
        """
        Get affinity score for a node (higher is better).

        Returns:
            Score (0-100), where higher means more preferred
        """
        if node_name in self.node_affinity:
            return 100
        return 50  # Neutral score for nodes not in affinity list

    def __repr__(self) -> str:
        return (f"VMRequirements(vmid={self.vmid}, name={self.name}, "
                f"cores={self.min_cores}, memory={self.min_memory}MB, "
                f"cpu_type={self.cpu_type}, cpu_flags={self.cpu_flags})")
