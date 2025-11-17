# VM Tagging and Requirements Examples

This document explains how to configure VM requirements using tags and notes in Proxmox.

## Tag-Based Configuration

Tags are semicolon-separated values in the VM configuration. You can set them via the Proxmox web UI or CLI.

### Basic Management Tags

```
# Enable auto-start management for this VM
auto-start

# Explicitly exclude from management
no-auto-start
```

### CPU Requirements

```
# Require specific CPU type
cpu:host
cpu:kvm64
cpu-type:x86-64-v3

# Require specific CPU flags
cpu-flags:aes,avx,avx2
requires:aes
```

### Resource Requirements

```
# Minimum memory (MB)
min-memory:4096

# Minimum CPU cores
min-cores:4
```

### Node Affinity

```
# Prefer specific nodes (soft constraint)
node:pve01
affinity:pve01,pve02

# Avoid specific nodes (hard constraint)
anti-affinity:pve03
exclude:pve04,pve05
```

### Complete Example Tags

```
auto-start;cpu:host;min-memory:8192;min-cores:4;affinity:pve01,pve02
```

## Notes-Based Configuration

For more complex requirements, you can use the VM notes field with structured syntax.

### CPU Type in Notes

```
CPU Type: x86-64-v3
cpu_type: host
```

### CPU Flags in Notes

```
Required CPU Flags: aes, avx, avx2
cpu_flags: aes,avx,avx2
```

### YAML Configuration Block

For advanced requirements, include a YAML block in the notes:

```yaml
requirements:
  storage: local-lvm
  network: vmbr0
  backup_enabled: true
  custom_param: value
```

## Setting Tags via Proxmox CLI

```bash
# Add tags to a VM
qm set 100 --tags "auto-start;cpu:host;min-memory:4096"

# View VM tags
qm config 100 | grep tags
```

## Setting Tags via Proxmox Web UI

1. Navigate to your VM
2. Click "Options" tab
3. Double-click "Tags" or select "Tags" and click "Edit"
4. Enter your tags separated by semicolons
5. Click "OK" to save

## Setting Notes via Proxmox CLI

```bash
# Set notes for a VM
qm set 100 --description "Production database server
CPU Type: host
cpu_flags: aes,avx2"
```

## Real-World Examples

### High-Performance Database Server

**Tags:**
```
auto-start;cpu:host;min-memory:16384;min-cores:8;cpu-flags:aes,avx2
```

**Notes:**
```
Production PostgreSQL database server
Requires:
- Host CPU passthrough for performance
- Minimum 16GB RAM
- AES and AVX2 CPU instructions
- Fast local storage
```

### Web Application Server

**Tags:**
```
auto-start;min-memory:4096;affinity:pve01,pve02
```

**Notes:**
```
Web application server (nginx + PHP-FPM)
Prefers nodes pve01 and pve02 (faster network)
```

### Development VM (No Auto-Start)

**Tags:**
```
no-auto-start;development
```

**Notes:**
```
Development environment
Manually controlled - do not auto-start
```

### GPU-Accelerated Workstation

**Tags:**
```
auto-start;exclude:pve03,pve04;min-memory:32768
```

**Notes:**
```yaml
GPU workstation for rendering
requirements:
  gpu: true
  pci_passthrough: nvidia-rtx-3090

Exclude pve03 and pve04 (no GPU available)
```

## Priority and Precedence

1. **Excluded tags** (`no-auto-start`) take highest precedence
2. **Anti-affinity** (node exclusion) is a hard constraint
3. **CPU requirements** are hard constraints
4. **Memory/CPU minimums** are hard constraints
5. **Affinity** (node preference) is a soft constraint that affects scoring
6. **Resource availability** affects node selection scoring

## Testing Your Configuration

Use the VM manager in test mode to validate your configuration:

```bash
cd /path/to/proxmox-vm-manager
python3 src/main.py --config config/config.yaml --test --log-level debug
```

This will connect to your cluster and show which VMs are managed and their requirements.
