#!/bin/bash

# Install Chromium and matching chromedriver on Raspberry Pi
echo "Updating system..."
sudo apt update && sudo apt upgrade -y

echo "Installing Chromium and Chromium driver..."
sudo apt install -y chromium-browser chromium-chromedriver

# Find where chromedriver is actually installed
echo "Locating chromedriver..."
CHROMEDRIVER_PATH=$(find /usr -name chromedriver 2>/dev/null | head -n 1)

if [ -z "$CHROMEDRIVER_PATH" ]; then
    echo "Error: chromedriver not found after installation"
    echo "Trying alternative installation method..."
    
    # Try to install via snap as fallback
    if command -v snap &> /dev/null; then
        sudo snap install chromium
        CHROMEDRIVER_PATH="/snap/bin/chromium.chromedriver"
    fi
fi

if [ -n "$CHROMEDRIVER_PATH" ]; then
    echo "Found chromedriver at: $CHROMEDRIVER_PATH"
    
    # Create symlink in /usr/local/bin (which should be in PATH)
    sudo ln -sf "$CHROMEDRIVER_PATH" /usr/local/bin/chromedriver
    
    # Also create symlink in /usr/bin as backup
    sudo ln -sf "$CHROMEDRIVER_PATH" /usr/bin/chromedriver
    
    # Make sure it's executable
    sudo chmod +x "$CHROMEDRIVER_PATH"
    
    echo "Created symlinks for chromedriver"
else
    echo "Error: Could not find chromedriver installation"
    echo "Please check if chromium-chromedriver package installed correctly"
    exit 1
fi

# Verify installation
echo "Verifying installation..."
if command -v chromedriver &> /dev/null; then
    echo "✓ Chromedriver is now accessible"
    chromedriver --version
else
    echo "✗ Chromedriver still not in PATH"
    echo "You may need to add it manually or restart your terminal"
fi

# Check Chromium browser
if command -v chromium-browser &> /dev/null; then
    echo "✓ Chromium browser found"
    chromium-browser --version
elif command -v chromium &> /dev/null; then
    echo "✓ Chromium browser found"
    chromium --version
else
    echo "✗ Chromium browser not found"
fi

# Display PATH for debugging
echo ""
echo "Current PATH: $PATH"
echo ""
echo "If chromedriver is still not found, try:"
echo "1. Restart your terminal"
echo "2. Run: export PATH=\$PATH:/usr/local/bin"
echo "3. Or add the above line to your ~/.bashrc"