#!/bin/bash
# Script to enable root SSH access on the server
# Run this after SSH'ing as laxman006

echo "Enabling root password login..."

# Set root password (you'll be prompted)
sudo passwd root

# Enable root login via password in SSH config
sudo sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
sudo sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# Restart SSH service
sudo systemctl restart sshd

echo "Root SSH access enabled!"
echo "You can now SSH as: ssh root@159.89.164.11"
