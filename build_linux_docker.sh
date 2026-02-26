#!/bin/bash
set -euo pipefail

echo "Building Docker image for Linux build..."
docker build --no-cache -t tlc-linux-builder -f Dockerfile.linux .

echo "Running PyInstaller in Docker..."
docker run --rm -v "$(pwd):/src" tlc-linux-builder

echo "Build complete. Check dist/linux/ for the executable bundle."
