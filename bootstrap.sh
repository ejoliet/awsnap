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
  cloudformation:ListResources (Cloud Control API)
  tag:GetResources
  ec2:DescribeRegions
Note: cloudformation:ListResources also requires the read permissions of each
resource type's handler (ec2:Describe*, s3:List*, ...). ViewOnlyAccess or
ReadOnlyAccess covers them; a policy with only the actions above returns
AccessDeniedException for every type.
EOF

# uv brings its own Python and runs awsnap from a throwaway env, so nothing is
# installed into the system or user site-packages.
if ! command -v uv > /dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$PATH"
    export PATH
fi

if ! command -v uv > /dev/null 2>&1; then
    echo "Error: uv not found after install; see https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

# Run awsnap with all arguments
exec uvx --from "git+https://github.com/${AWSNAP_REPO}.git@${AWSNAP_VERSION}" awsnap "$@"
