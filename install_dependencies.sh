#!/bin/bash

# Camera Server Dependency Installation Script
# This script installs all required dependencies for the camera server

set -e  # Exit on error

echo "=================================="
echo "Camera Server Dependency Installer"
echo "=================================="
echo ""

# Check if virtual environment is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "⚠️  Warning: No virtual environment detected!"
    echo "It's recommended to use a virtual environment."
    echo ""
    read -p "Do you want to create and activate a virtual environment? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Creating virtual environment..."
        python3 -m venv venv312
        echo "Activating virtual environment..."
        source venv312/bin/activate
        echo "✅ Virtual environment activated"
    fi
fi

echo ""
echo "📦 Installing Python dependencies..."
echo ""

# Upgrade pip, setuptools, and wheel
echo "Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel

# Install dependencies one by one (excluding gstreamer-python)
echo ""
echo "Installing requests..."
pip install requests

echo "Installing opencv-python..."
pip install opencv-python

echo "Installing onvif-zeep..."
pip install onvif-zeep

echo "Installing asyncio..."
pip install asyncio

echo "Installing aiohttp..."
pip install aiohttp

echo "Installing pydantic..."
pip install pydantic

echo "Installing loguru..."
pip install loguru

echo ""
echo "=================================="
echo "✅ Installation Complete!"
echo "=================================="
echo ""
echo "Note: gstreamer-python is not installed (it's optional and can cause issues)."
echo "The server uses OpenCV for video processing instead."
echo ""
echo "Next steps:"
echo "1. Configure config.json with your camera and Shinobi settings"
echo "2. Run: python3 test_setup.py"
echo "3. Run: python3 camera_server.py"
echo ""
