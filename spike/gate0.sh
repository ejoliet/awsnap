#!/bin/sh
# Gate-0 measurement script for CloudShell
# Usage: ./spike/gate0.sh
# Measures the three kill criteria from spike/gate0.md

set -eu

echo "=== Gate-0 Spike Measurements ==="
echo ""

# Criterion 1: Python and boto3 check
echo "1. Python version and boto3 availability:"
python3 --version
python3 -c "import boto3; print('boto3: importable')" 2>/dev/null || echo "boto3: NOT importable"
echo ""

# Criterion 2: duckdb installation time and size
echo "2. duckdb installation (timing and disk impact):"
HOME_BEFORE=$(du -sh ~/.local 2>/dev/null | awk '{print $1}' || echo "N/A")
echo "Home .local size before: $HOME_BEFORE"
echo "Installing duckdb..."
time python3 -m pip install --user duckdb >/dev/null 2>&1 || true
HOME_AFTER=$(du -sh ~/.local 2>/dev/null | awk '{print $1}' || echo "N/A")
echo "Home .local size after: $HOME_AFTER"
echo ""

# Criterion 3: awsnap collection with config tier
echo "3. Running awsnap with config tier..."
mkdir -p ./gate0-out
time python3 -m awsnap --tier config --verbose --out ./gate0-out 2>&1 | grep -E '^Resources:|^Download:' || echo "config tier collection failed or not completed"
echo ""

# Criterion 4: awsnap collection with cloudcontrol tier
echo "4. Running awsnap with cloudcontrol tier..."
time python3 -m awsnap --tier cloudcontrol --verbose --out ./gate0-out 2>&1 | grep -E '^Resources:|^Download:' || echo "cloudcontrol tier collection failed or not completed"
echo ""

echo "=== Gate-0 measurements complete ==="
echo "Review spike/gate0.md and fill in the results table."
