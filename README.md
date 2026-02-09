# TLC Analysis GUI

This is the initial GUI for the TLC Analysis software, built with Python and PyQt6.

## Prerequisites

- Python 3.8+

## Setup and Run

1.  **Install uv** (if not already installed):
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Sync dependencies**:
    ```bash
    uv sync
    ```

3.  **Run the application**:
    ```bash
    uv run main.py
    ```

## Features

- Displays 3 side-by-side image slots.
- "Load Image" button for each slot to load an image from the filesystem.
- Images are scaled to fit the display area.
