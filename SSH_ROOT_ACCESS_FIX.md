# Fix SSH Root Access Issue

## Problem
SSH as `root@159.89.164.11` fails with "Permission denied", but `laxman006@159.89.164.11` works.

## Root Cause
Ubuntu/DigitalOcean servers disable root password login by default for security. Root access is typically managed via `sudo`.

## Solutions

### Solution 1: Enable Root Password Login (Recommended for Deployment Scripts)

**Step 1:** SSH as `laxman006`:
```bash
ssh laxman006@159.89.164.11
```

**Step 2:** Set root password:
```bash
sudo passwd root
# Enter new password when prompted
```

**Step 3:** Enable root login in SSH config:
```bash
sudo sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
sudo sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
```

**Step 4:** Restart SSH service:
```bash
sudo systemctl restart sshd
```

**Step 5:** Test root access:
```bash
exit
ssh root@159.89.164.11
# Enter the password you set in Step 2
```

### Solution 2: Use `laxman006` with `sudo` (For Manual Commands)

Instead of SSH'ing as root, SSH as `laxman006` and use `sudo`:

```bash
ssh laxman006@159.89.164.11

# Use sudo for root commands:
sudo apt-get update
sudo docker ps
sudo docker-compose -f docker-compose.ai.yml ps
```

### Solution 3: Switch to Root After Login

```bash
ssh laxman006@159.89.164.11
sudo su -
# Now you're root
```

### Solution 4: Modify Deployment Script to Use `laxman006` with Sudo

If you prefer not to enable root login, modify `deploy-new-server.sh`:

**Change line 23:**
```bash
SERVER_USER="root"
```
**To:**
```bash
SERVER_USER="laxman006"
```

**Then add `sudo` to all commands in the SSH heredoc blocks** (lines 59-83, 88-100, etc.):
- `apt-get update` → `sudo apt-get update`
- `docker ps` → `sudo docker ps`
- `mkdir -p /opt/chatbot` → `sudo mkdir -p /opt/chatbot`
- etc.

**Note:** You may also need to configure passwordless sudo for `laxman006`:
```bash
ssh laxman006@159.89.164.11
sudo visudo
# Add this line:
laxman006 ALL=(ALL) NOPASSWD: ALL
```

## Quick Fix (Copy & Paste)

Run these commands after SSH'ing as `laxman006`:

```bash
ssh laxman006@159.89.164.11
sudo passwd root
# Enter new password twice
sudo sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
sudo sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
sudo systemctl restart sshd
exit
ssh root@159.89.164.11
# Test with the password you set
```

## Security Note

Enabling root password login reduces security. Consider:
- Using SSH keys instead of passwords
- Restricting root login to specific IPs
- Using `laxman006` with sudo for daily operations
