#!/bin/bash
set -e

# Print installed packages for debugging
echo "=== CONDA-INSTALLED PACKAGES ==="
micromamba run -p /opt/conda micromamba list
echo "================================"

echo "=== PIP-INSTALLED PACKAGES ==="
micromamba run -p /opt/conda pip list
echo "=============================="

# Print the Python executable path (to verify we're using the right environment)
echo "=== PYTHON EXECUTABLE PATH ==="
micromamba run -p /opt/conda which python
echo "=============================="

# Option 1: Use python -m to call uvicorn (more reliable)
exec micromamba run -p /opt/conda python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info

# Option 2 (Alternative): Use the full path if needed
# UVICORN_PATH=$(micromamba run -p /opt/conda which uvicorn)
# exec micromamba run -p /opt/conda $UVICORN_PATH main:app --host 0.0.0.0 --port 8000 --log-level info
