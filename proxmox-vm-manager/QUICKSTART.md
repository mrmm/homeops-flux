# Proxmox VM Manager - Quick Start Guide

Get up and running in 5 minutes!

## Prerequisites

- Proxmox VE cluster (7.x or 8.x)
- Python 3.7+ on your management machine
- API access to Proxmox
- Root access to install the service

## Step 1: Create Proxmox API Token

In Proxmox Web UI:

1. Navigate to **Datacenter → Permissions → API Tokens**
2. Click **Add**
3. Fill in:
   - User: `root@pam`
   - Token ID: `automation`
   - Uncheck "Privilege Separation" (or set appropriate permissions)
4. Click **Add**
5. **Copy the token value** (you won't see it again!)

## Step 2: Install the Service

```bash
cd /path/to/homeops-flux/proxmox-vm-manager

# Install (requires root)
sudo ./install.sh

# This will:
# - Install Python dependencies
# - Copy files to /opt/proxmox-vm-manager
# - Create config at /etc/proxmox-vm-manager/config.yaml
# - Install systemd service
```

## Step 3: Configure

Edit the configuration file:

```bash
sudo nano /etc/proxmox-vm-manager/config.yaml
```

Update these values:

```yaml
proxmox:
  host: "192.168.1.100"        # Your Proxmox host IP
  user: "root@pam"
  token_name: "automation"
  token_value: "paste-your-token-here"  # From Step 1
  verify_ssl: true             # Set to false if using self-signed cert
```

Save and exit (Ctrl+X, Y, Enter in nano).

## Step 4: Test Configuration

```bash
task proxmox:test

# You should see:
# - Connection successful
# - List of cluster nodes
# - No errors
```

## Step 5: Tag Your VMs

Tag VMs you want to be auto-started:

```bash
# Enable auto-start for VM 100
qm set 100 --tags "auto-start"

# With CPU requirements
qm set 101 --tags "auto-start;cpu:host"

# With memory requirements
qm set 102 --tags "auto-start;min-memory:4096"
```

**Via Proxmox Web UI:**
1. Select your VM
2. Go to **Options** tab
3. Double-click **Tags**
4. Add: `auto-start`
5. Click OK

## Step 6: Start the Service

```bash
# Enable auto-start on boot
sudo task proxmox:enable

# Start the service
sudo task proxmox:start

# Check status
task proxmox:status

# Watch logs
task proxmox:logs
```

## Step 7: Test It!

Stop a tagged VM and watch it auto-start:

```bash
# In one terminal, watch the logs
task proxmox:logs

# In another terminal, stop a VM
qm stop 100

# Watch the logs - you should see:
# 1. VM state change detected
# 2. Checking node resources
# 3. Starting VM on best node
```

## That's It!

Your Proxmox VM auto-start system is now running.

## Quick Reference

### Common Tasks

```bash
# View logs (live)
task proxmox:logs

# Recent logs
task proxmox:logs-recent

# Restart service
task proxmox:restart

# Stop service
task proxmox:stop

# Edit config
task proxmox:edit-config

# Test config
task proxmox:test
```

### VM Tag Examples

```bash
# Basic auto-start
qm set <vmid> --tags "auto-start"

# Require host CPU
qm set <vmid> --tags "auto-start;cpu:host"

# Minimum 8GB RAM
qm set <vmid> --tags "auto-start;min-memory:8192"

# Prefer specific nodes
qm set <vmid> --tags "auto-start;affinity:pve01,pve02"

# Exclude specific nodes
qm set <vmid> --tags "auto-start;exclude:pve03"

# Complex requirements
qm set <vmid> --tags "auto-start;cpu:host;min-memory:16384;min-cores:4;affinity:pve01"
```

## Troubleshooting

### VM not auto-starting?

1. **Check if tagged:**
   ```bash
   qm config <vmid> | grep tags
   ```

2. **Check service is running:**
   ```bash
   task proxmox:status
   ```

3. **Check logs for errors:**
   ```bash
   task proxmox:logs-recent
   ```

4. **Verify node has resources:**
   - Enough free memory?
   - CPU not maxed out?
   - Meets VM requirements?

### Service won't start?

```bash
# Check for config errors
task proxmox:test

# View detailed error
sudo journalctl -u proxmox-vm-manager -n 50
```

### Can't connect to Proxmox?

```bash
# Test manually
curl -k https://your-proxmox-ip:8006/api2/json/version

# Check firewall
# Check token is correct
# Try verify_ssl: false for self-signed certs
```

## Next Steps

- Read the full [README.md](README.md) for advanced features
- Check [vm-tagging-examples.md](config/vm-tagging-examples.md) for more examples
- Set up monitoring and alerting
- Fine-tune the `migration_threshold_score` based on your needs

## Need Help?

- Check the logs: `task proxmox:logs`
- Run in debug mode: `task proxmox:run`
- Review configuration: `task proxmox:edit-config`
- Test connection: `task proxmox:test`

Happy auto-starting! 🚀
