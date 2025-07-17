#!/bin/bash

# Install Chromium and matching chromedriver on Raspberry Pi
echo "Updating system..."
sudo apt update && sudo apt upgrade -y

echo "Installing Chromium and Chromium driver..."
sudo apt install -y chromium-browser chromium-chromedriver

echo "Creating symlink for chromedriver..."
sudo ln -sf /usr/lib/chromium-browser/chromedriver /usr/bin/chromedriver

echo "Chromedriver installed at $(which chromedriver)"
chromedriver --version
