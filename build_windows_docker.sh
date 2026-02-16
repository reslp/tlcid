#!/bin/bash
set -e

echo "Building Docker image for Windows build..."
docker build -t tlc-windows-builder -f Dockerfile.windows .

echo "Running PyInstaller in Docker..."
# Mount current directory to /src in container
# Artifacts will be generated in dist/windows and build/windows
docker run --rm -v "$(pwd):/src" tlc-windows-builder

echo "Build complete. Check dist/windows/ for the executable."
