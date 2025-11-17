#!/usr/bin/env python3
"""
Proxmox VM Auto-Start Manager

Monitors VMs in a Proxmox cluster and automatically starts stopped VMs
on the most suitable node based on resource availability and VM requirements.
"""
import argparse
import logging
import sys
import yaml
from pathlib import Path
from proxmox_client import ProxmoxClient
from vm_manager import VMManager


def setup_logging(log_level: str, log_file: str = None):
    """Configure logging."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, 'r') as f:
        config = yaml.safe_load(f)

    return config


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Proxmox VM Auto-Start Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default config
  %(prog)s --config /etc/proxmox-vm-manager/config.yaml

  # Run with debug logging
  %(prog)s --config config.yaml --log-level debug

  # Test mode (check configuration without running)
  %(prog)s --config config.yaml --test
        """
    )

    parser.add_argument(
        '--config', '-c',
        required=True,
        help='Path to configuration YAML file'
    )

    parser.add_argument(
        '--log-level', '-l',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )

    parser.add_argument(
        '--log-file',
        help='Path to log file (default: stdout only)'
    )

    parser.add_argument(
        '--test', '-t',
        action='store_true',
        help='Test mode: validate config and connection, then exit'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level, args.log_file)
    logger = logging.getLogger(__name__)

    try:
        # Load configuration
        logger.info(f"Loading configuration from {args.config}")
        config = load_config(args.config)

        # Extract Proxmox connection settings
        proxmox_config = config.get('proxmox', {})
        if not proxmox_config:
            raise ValueError("Missing 'proxmox' section in configuration")

        # Initialize Proxmox client
        logger.info(f"Connecting to Proxmox at {proxmox_config.get('host')}")

        # Support both password and token authentication
        auth_type = proxmox_config.get('auth_type', 'token')

        if auth_type == 'token':
            proxmox = ProxmoxClient(
                host=proxmox_config['host'],
                user=proxmox_config['user'],
                token_name=proxmox_config.get('token_name'),
                token_value=proxmox_config.get('token_value'),
                verify_ssl=proxmox_config.get('verify_ssl', True)
            )
        else:  # password
            proxmox = ProxmoxClient(
                host=proxmox_config['host'],
                user=proxmox_config['user'],
                password=proxmox_config.get('password'),
                verify_ssl=proxmox_config.get('verify_ssl', True)
            )

        # Test connection
        nodes = proxmox.get_cluster_nodes()
        logger.info(f"Successfully connected to Proxmox cluster with {len(nodes)} nodes")

        if args.test:
            # Test mode - just validate and exit
            logger.info("Test mode: configuration valid, connection successful")
            logger.info("Cluster nodes:")
            for node in nodes:
                logger.info(f"  - {node['node']}: {node.get('status', 'unknown')}")
            sys.exit(0)

        # Extract VM manager settings
        manager_config = config.get('vm_manager', {})

        # Initialize and run VM manager
        vm_manager = VMManager(proxmox, manager_config)
        vm_manager.run()

    except KeyboardInterrupt:
        logger.info("Shutting down (KeyboardInterrupt)")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
