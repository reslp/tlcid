#!/bin/bash
set -e

echo "Building Docker image for Windows build..."
docker build --no-cache -t tlc-windows-builder -f Dockerfile.windows .

echo "Running PyInstaller in Docker..."
docker run --rm -v "$(pwd):/src" tlc-windows-builder

echo "Build complete. Check dist/windows/ for the executable."
