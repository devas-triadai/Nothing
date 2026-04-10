#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AGRA — Node.js Upgrade Script
# RunPod pods often ship with Node.js v12 which is too old.
# This installs Node.js 20 LTS (required by Vite and React).
# Run this ONCE on pod setup.
# ═══════════════════════════════════════════════════════════════

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        AGRA — Node.js Upgrade Script                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

CURRENT_NODE=$(node -v 2>/dev/null || echo "none")
echo "Current Node.js version: $CURRENT_NODE"

# Check if already >= 18
MAJOR=$(echo "$CURRENT_NODE" | sed 's/v//' | cut -d. -f1)
if [ "$MAJOR" -ge 18 ] 2>/dev/null; then
    echo "✅ Node.js $CURRENT_NODE is already sufficient (>= 18). No upgrade needed."
    exit 0
fi

echo ""
echo "⚠  Node.js $CURRENT_NODE is too old. Vite requires Node >= 18."
echo "   Installing Node.js 20 LTS via NodeSource..."
echo ""

# Remove conflicting older Ubuntu node binaries
apt-get remove --purge -y nodejs npm libnode-dev || true
apt-get autoremove -y

# Install Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get -o Dpkg::Options::="--force-overwrite" install -y nodejs
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
NEW_NODE=$(node -v)
NEW_NPM=$(npm -v)
echo "  ✅ Upgraded successfully!"
echo "  Node.js: $CURRENT_NODE → $NEW_NODE"
echo "  npm: $NEW_NPM"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
