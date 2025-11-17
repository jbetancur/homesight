#!/bin/bash
# HomeSight verification script

echo "================================"
echo "HomeSight Project Verification"
echo "================================"
echo ""

# Check Go
echo "Checking Go installation..."
if command -v go &> /dev/null; then
    echo "✅ Go: $(go version)"
else
    echo "❌ Go not found"
fi

# Check Python
echo "Checking Python installation..."
if command -v python3 &> /dev/null; then
    echo "✅ Python: $(python3 --version)"
else
    echo "❌ Python3 not found"
fi

# Check binary
echo ""
echo "Checking build..."
if [ -f "bin/homesightd" ]; then
    echo "✅ Binary built: $(du -h bin/homesightd | cut -f1)"
    echo "   $(file bin/homesightd | cut -d: -f2)"
else
    echo "❌ Binary not found. Run: make build"
fi

# Check Python dependencies
echo ""
echo "Checking Python dependencies..."
if [ -f "ai-sidecar/requirements.txt" ]; then
    echo "✅ Python requirements file exists"
else
    echo "❌ Python requirements file missing"
fi

# Check configuration
echo ""
echo "Checking configuration..."
if [ -f "config.yaml" ]; then
    echo "✅ Configuration file exists"
else
    echo "❌ Configuration file missing"
fi

# Check systemd files
echo ""
echo "Checking systemd service files..."
SERVICE_COUNT=$(ls systemd/*.service 2>/dev/null | wc -l)
echo "✅ Found $SERVICE_COUNT systemd service files"

# Check documentation
echo ""
echo "Checking documentation..."
DOC_COUNT=$(ls docs/*.md 2>/dev/null | wc -l)
echo "✅ Found $DOC_COUNT documentation files"

# Check scripts
echo ""
echo "Checking scripts..."
if [ -x "scripts/build.sh" ]; then
    echo "✅ Build script is executable"
else
    echo "⚠️  Build script not executable"
fi

if [ -x "scripts/install.sh" ]; then
    echo "✅ Install script is executable"
else
    echo "⚠️  Install script not executable"
fi

# Project structure
echo ""
echo "Project structure:"
echo "================================"
tree -L 2 -I 'bin|__pycache__|*.pyc' || find . -maxdepth 2 -type d | grep -v '^\./\.' | sort

echo ""
echo "================================"
echo "Verification complete!"
echo "================================"
echo ""
echo "Quick start:"
echo "  1. ./scripts/dev.sh           # Start dev services"
echo "  2. cd ai-sidecar && python main.py"
echo "  3. ./bin/homesightd"
echo ""
echo "For production:"
echo "  sudo ./scripts/install.sh"
