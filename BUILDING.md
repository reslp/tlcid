# Building TLCid

## Prerequisites
- macOS or Windows
- Python 3.x
- `uv` (recommended for dependency management)

## Build Commands

### macOS
To build a standalone `.app` bundle:
```bash
uv run pyinstaller tlcid.spec --clean
```
The resulting application will be located at `dist/TLCid.app`.

### Windows (via Docker)
To build the Windows executable using the provided Docker environment:
```bash
./build_windows_docker.sh
```

## Troubleshooting
- If the icon is missing from the interface, ensure `icon.png` is present in the project root before building.
- For Windows builds, ensure Docker is running.
