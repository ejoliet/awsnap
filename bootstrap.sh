#!/bin/sh
set -eu

AWSNAP_VERSION="${AWSNAP_VERSION:-v0.1.0}"
AWSNAP_REPO="${AWSNAP_REPO:-ejoliet/awsnap}"

# Print API allowlist
cat << 'EOF'
API allowlist for awsnap:
  sts:GetCallerIdentity
  config:DescribeConfigurationRecorderStatus
  config:SelectResourceConfig
  cloudcontrol:ListResources
  tag:GetResources
  ec2:DescribeRegions
EOF

# Check Python version
echo "Checking Python..."
python_version=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
echo "Python version: $python_version"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
    echo "Error: Python 3.9+ required" >&2
    exit 1
fi

# Check boto3
echo "Checking boto3..."
if ! python3 -c "import boto3" 2>/dev/null; then
    echo "Installing boto3..."
    python3 -m pip install --user boto3
fi

# Install awsnap from git
echo "Installing awsnap..."
python3 -m pip install --user "git+https://github.com/${AWSNAP_REPO}.git@${AWSNAP_VERSION}"

# Add ~/.local/bin to PATH if not already present
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    export PATH="$HOME/.local/bin:$PATH"
fi

# Run awsnap with all arguments
python3 -m awsnap "$@"
