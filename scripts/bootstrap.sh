#!/bin/bash
# Master bootstrap script
# Initializes the HomeSight system with default zones and attribute definitions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🏠 HomeSight System Bootstrap"
echo "=============================="
echo ""

# Bootstrap zones first
echo "Step 1: Creating default zones..."
"$SCRIPT_DIR/bootstrap-zones.sh"

echo ""
echo "Step 2: Creating attribute definitions..."
"$SCRIPT_DIR/bootstrap-attributes.sh"

echo ""
echo "=============================="
echo "✅ HomeSight system bootstrapped successfully!"
echo ""
echo "Next steps:"
echo "  - Configure zone attributes through the UI (Settings → Zone Attributes)"
echo "  - Add custom zones via UI or API"
echo "  - Add custom attribute definitions via UI (Settings → Attribute Schema)"
