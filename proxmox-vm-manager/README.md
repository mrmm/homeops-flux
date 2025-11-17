# Proxmox VM Auto-Start Manager

Intelligent VM auto-start and placement system for Proxmox clusters.

## Overview

This system monitors VMs in a Proxmox cluster and automatically starts stopped VMs on the most suitable node based on:

- **Resource availability** (CPU, memory)
- **VM requirements** (CPU type, flags, minimum resources)
- **Node affinity/anti-affinity** rules
- **Intelligent load balancing** across cluster nodes

When a VM stops (planned or unplanned), the system:

1. Detects the state change
2. Evaluates if the current node can host the VM
3. If not, finds the best node based on requirements and available resources
4. Migrates the VM to the optimal node (if needed)
5. Starts the VM

## Features

- **Automatic VM startup** with intelligent node placement
- **Resource-aware scheduling** - considers CPU, memory availability
- **VM requirements parsing** from tags and notes
- **CPU compatibility checking** (CPU type, flags)
- **Node affinity and anti-affinity** rules
- **Retry limits** to prevent startup loops
- **Migration support** to better nodes
- **Tag-based VM management** (opt-in system)
- **RESTful Proxmox API integration**
- **Systemd service** for production deployment
- **Comprehensive logging** and monitoring

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│               Proxmox VM Auto-Start Manager             │
└─────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐
    │  VM Monitor │ │   Node      │ │  Proxmox   │
    │             │ │  Selector   │ │   API      │
    │  - State    │ │             │ │  Client    │
    │    tracking │ │  - Resource │ │            │
    │  - Change   │ │    scoring  │ │  - VM ops  │
    │    detection│ │  - Affinity │ │  - Node    │
    │             │ │    rules    │ │    info    │
    └─────────────┘ └─────────────┘ └────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐
    │     VM      │ │  Migration  │ │  Resource  │
    │ Requirements│ │  Orchestr.  │ │  Monitor   │
    │             │ │             │ │            │
    │  - Parse    │ │  - Offline  │ │  - CPU     │
    │    tags     │ │  - Online   │ │  - Memory  │
    │  - Parse    │ │  - Safety   │ │  - Load    │
    │    notes    │ │             │ │            │
    └─────────────┘ └─────────────┘ └────────────┘
```

## Components

### 1. Proxmox API Client (`proxmox_client.py`)

Wrapper for Proxmox API operations:
- Cluster node discovery
- VM status and configuration queries
- Resource usage monitoring
- VM start/stop/migrate operations
- CPU information retrieval

### 2. VM Requirements Parser (`vm_requirements.py`)

Extracts and validates VM requirements from:
- **Tags**: `cpu:host`, `min-memory:4096`, `affinity:node1`
- **Notes**: YAML blocks with detailed requirements
- **Configuration**: Cores, memory from VM config

Supports:
- CPU type requirements
- CPU flag requirements (AES, AVX, etc.)
- Minimum memory/core requirements
- Node affinity (preferred nodes)
- Node anti-affinity (excluded nodes)

### 3. Node Selector (`node_selector.py`)

Intelligent node selection algorithm:

**Scoring System** (0-100 points):
- **Memory availability** (40 points): More free memory = higher score
- **CPU availability** (30 points): Lower CPU usage = higher score
- **VM affinity** (20 points): Preferred nodes get bonus
- **Load balancing** (10 points): Emptier nodes preferred

**Hard Constraints** (must match):
- Node is online
- Not in anti-affinity list
- Has required CPU type/flags
- Has sufficient memory
- Has available CPU capacity

### 4. VM Manager (`vm_manager.py`)

Main orchestration engine:
- Monitors VM state changes
- Tracks managed VMs (via tags)
- Handles startup attempts with retry limits
- Coordinates migration and startup
- Prevents startup loops

### 5. Main Application (`main.py`)

Entry point with:
- Configuration loading (YAML)
- Logging setup
- Connection management
- Test mode for validation

## Installation

### Prerequisites

- Python 3.7+
- `pip3` (Python package manager)
- Proxmox VE cluster (tested on 7.x and 8.x)
- API access to Proxmox (token or password)

### Quick Install

```bash
# Clone or navigate to the repository
cd /path/to/homeops-flux/proxmox-vm-manager

# Run installation script (requires root)
sudo ./install.sh

# Edit configuration
sudo nano /etc/proxmox-vm-manager/config.yaml

# Test configuration
task proxmox:test

# Enable and start service
sudo task proxmox:enable
sudo task proxmox:start
```

### Manual Installation

```bash
# Install Python dependencies
pip3 install -r requirements.txt

# Copy files to installation directory
sudo mkdir -p /opt/proxmox-vm-manager
sudo cp -r src /opt/proxmox-vm-manager/

# Create configuration directory
sudo mkdir -p /etc/proxmox-vm-manager
sudo cp config/config.example.yaml /etc/proxmox-vm-manager/config.yaml

# Edit configuration
sudo nano /etc/proxmox-vm-manager/config.yaml

# Install systemd service
sudo cp systemd/proxmox-vm-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## Configuration

### Proxmox API Access

#### Option 1: API Token (Recommended)

Create an API token in Proxmox:

```bash
# Via Proxmox Web UI:
# Datacenter → Permissions → API Tokens → Add

# Or via CLI:
pveum user token add root@pam automation --privsep=0
```

Configure in `config.yaml`:

```yaml
proxmox:
  host: "192.168.1.100"
  auth_type: "token"
  user: "root@pam"
  token_name: "automation"
  token_value: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  verify_ssl: true
```

#### Option 2: Password Authentication

```yaml
proxmox:
  host: "192.168.1.100"
  auth_type: "password"
  user: "root@pam"
  password: "your-password"
  verify_ssl: true
```

### VM Manager Settings

```yaml
vm_manager:
  # Enable automatic VM startup
  auto_start_enabled: true

  # Enable automatic migration to better nodes
  auto_migrate_enabled: true

  # Monitoring interval (seconds)
  monitor_interval_seconds: 30

  # Startup retry limits
  max_startup_attempts: 3
  startup_attempt_window_seconds: 300  # 5 minutes

  # Migration threshold (0-100)
  # Higher = less aggressive migration
  migration_threshold_score: 20.0

  # Tags for VM management
  managed_tags:
    - "auto-start"
    - "managed"

  excluded_tags:
    - "no-auto-start"
    - "manual"
```

## VM Configuration

### Tagging VMs for Management

VMs must have one of the `managed_tags` to be monitored:

```bash
# Enable auto-start for a VM
qm set 100 --tags "auto-start"

# With additional requirements
qm set 100 --tags "auto-start;cpu:host;min-memory:4096"
```

### Specifying VM Requirements

#### Via Tags

```bash
# CPU requirements
qm set 100 --tags "auto-start;cpu:host"
qm set 101 --tags "auto-start;cpu-type:x86-64-v3"
qm set 102 --tags "auto-start;cpu-flags:aes,avx2"

# Resource requirements
qm set 100 --tags "auto-start;min-memory:8192;min-cores:4"

# Node affinity
qm set 100 --tags "auto-start;affinity:pve01,pve02"
qm set 101 --tags "auto-start;exclude:pve03"
```

#### Via Notes

Add requirements to VM notes/description:

```bash
qm set 100 --description "Production database
cpu_type: host
cpu_flags: aes,avx2
min_memory: 16384"
```

#### Advanced YAML Configuration

Include a YAML block in VM notes:

```yaml
Production application server

```yaml
requirements:
  storage: local-lvm
  network: vmbr0
  gpu: false
```
```

### Examples

See [config/vm-tagging-examples.md](config/vm-tagging-examples.md) for comprehensive examples.

## Usage

### Using Task Commands

```bash
# Install the service
sudo task proxmox:install

# Test configuration
task proxmox:test

# Run in foreground (for testing)
task proxmox:run

# Service management
task proxmox:start
task proxmox:stop
task proxmox:restart
task proxmox:status

# View logs
task proxmox:logs          # Follow logs
task proxmox:logs-recent   # Recent logs

# Enable/disable auto-start
task proxmox:enable
task proxmox:disable

# Edit configuration
task proxmox:edit-config

# Uninstall
sudo task proxmox:uninstall
```

### Direct Commands

```bash
# Test configuration
python3 src/main.py --config /etc/proxmox-vm-manager/config.yaml --test

# Run in foreground with debug logging
python3 src/main.py --config /etc/proxmox-vm-manager/config.yaml --log-level DEBUG

# Service management
sudo systemctl start proxmox-vm-manager
sudo systemctl status proxmox-vm-manager
sudo journalctl -u proxmox-vm-manager -f
```

## How It Works

### Startup Flow

```
1. VM stops (detected via monitoring)
   │
   ├─→ Check if VM is managed (has required tags)
   │   └─→ No: Ignore
   │   └─→ Yes: Continue
   │
   ├─→ Check retry limits
   │   └─→ Too many attempts: Skip
   │   └─→ OK: Continue
   │
   ├─→ Parse VM requirements
   │
   ├─→ Check current node suitability
   │   ├─→ Has resources + meets requirements?
   │   │   └─→ Yes: Start on current node
   │   │   └─→ No: Find better node
   │
   ├─→ Find best node
   │   ├─→ Filter nodes by requirements
   │   ├─→ Score each node
   │   └─→ Select highest score
   │
   ├─→ Migrate (if needed)
   │   └─→ Offline migration (VM is stopped)
   │
   └─→ Start VM on target node
```

### Node Scoring Example

For a VM requiring 4GB RAM, 2 cores:

```
Node pve01:
  CPU usage: 20% → 24 points (80% free * 30)
  Memory: 50% free → 20 points (50% * 40)
  Affinity: Preferred → 20 points
  Balance: 65% free → 6.5 points (65% * 10)
  Total: 70.5 points

Node pve02:
  CPU usage: 80% → 6 points (20% free * 30)
  Memory: 30% free → 12 points (30% * 40)
  Affinity: Neutral → 10 points
  Balance: 25% free → 2.5 points (25% * 10)
  Total: 30.5 points

→ Select pve01 (higher score)
```

## Monitoring and Troubleshooting

### View Logs

```bash
# Live logs
task proxmox:logs

# Recent logs
task proxmox:logs-recent

# Filter for errors
sudo journalctl -u proxmox-vm-manager -p err
```

### Common Issues

#### VM not starting automatically

1. Check if VM has required tags:
   ```bash
   qm config <vmid> | grep tags
   ```

2. Check logs for errors:
   ```bash
   task proxmox:logs-recent
   ```

3. Verify no suitable node found:
   - Check resource requirements
   - Check anti-affinity rules
   - Check CPU requirements

#### Too many startup attempts

The system limits retries to prevent loops:
- Default: 3 attempts in 5 minutes
- Check logs to see why startup is failing
- Fix the underlying issue
- Wait for the retry window to expire

#### Migration fails

- Ensure shared storage is accessible
- Check network connectivity between nodes
- Verify VM is not locked
- Check Proxmox cluster status

### Debug Mode

Run in foreground with debug logging:

```bash
task proxmox:run
# or
python3 src/main.py --config /etc/proxmox-vm-manager/config.yaml --log-level DEBUG
```

## Security Considerations

### API Token Permissions

The API token needs these permissions:

- **VM.Audit**: Read VM configurations
- **VM.PowerMgmt**: Start/stop VMs
- **VM.Migrate**: Migrate VMs
- **Sys.Audit**: Read node information

Create a dedicated user with minimal permissions:

```bash
# Create user
pveum user add automation@pve

# Create role with minimal permissions
pveum role add VMAutoStart -privs "VM.Audit VM.PowerMgmt VM.Migrate Sys.Audit"

# Assign role to user
pveum acl modify / -user automation@pve -role VMAutoStart

# Create token
pveum user token add automation@pve automation --privsep=0
```

### Network Security

- Use HTTPS for Proxmox API (verify_ssl: true)
- Store API tokens in secure configuration files
- Restrict access to `/etc/proxmox-vm-manager/config.yaml`
- Consider using SOPS or other secret management

### File Permissions

```bash
# Secure configuration file
sudo chmod 600 /etc/proxmox-vm-manager/config.yaml
sudo chown root:root /etc/proxmox-vm-manager/config.yaml
```

## Performance Considerations

### Monitoring Interval

- Default: 30 seconds
- Lower interval = faster response, more API calls
- Higher interval = slower response, fewer API calls
- Recommended: 20-60 seconds

### Cluster Scale

Tested on:
- Up to 20 nodes
- Up to 200 VMs
- Monitoring overhead: < 1% CPU, < 100MB RAM

## Roadmap

- [ ] Prometheus metrics export
- [ ] Web UI for management
- [ ] HA support (run on multiple nodes)
- [ ] Advanced scheduling policies
- [ ] Integration with external CMDB
- [ ] Support for VM groups/dependencies
- [ ] Backup-aware scheduling
- [ ] Storage availability checking

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is part of the homeops-flux repository.

## Support

For issues, questions, or contributions:

- Create an issue in the repository
- Check the logs for error messages
- Review the configuration examples
- Test your setup with `task proxmox:test`

## Acknowledgments

Built with:
- [Proxmoxer](https://github.com/proxmoxer/proxmoxer) - Proxmox API wrapper
- [PyYAML](https://pyyaml.org/) - YAML parsing
- [Task](https://taskfile.dev/) - Task automation
