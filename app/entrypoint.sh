#!/bin/bash
set -e

# Print environment diagnostic information
echo "=== CONDA ENVIRONMENT DETAILS ==="
micromamba info
echo "================================"

echo "=== CONDA-INSTALLED PACKAGES ==="
micromamba run -p /opt/conda micromamba list
echo "================================"

echo "=== CHECKING FOR PIP ==="
if micromamba run -p /opt/conda which pip > /dev/null 2>&1; then
    echo "pip is installed at: $(micromamba run -p /opt/conda which pip)"
    echo "=== PIP-INSTALLED PACKAGES ==="
    micromamba run -p /opt/conda pip list
else
    echo "pip is NOT installed or not in PATH!"
fi
echo "=============================="

echo "=== CHECKING FOR UVICORN ==="
if micromamba run -p /opt/conda python -c "import uvicorn; print(f'uvicorn version: {uvicorn.__version__}')" 2>/dev/null; then
    echo "uvicorn is properly installed and importable"
else
    echo "Failed to import uvicorn!"
    # List site-packages directory to help diagnose
    echo "Contents of site-packages directory:"
    SITE_PACKAGES=$(micromamba run -p /opt/conda python -c "import site; print(site.getsitepackages()[0])")
    if [ -d "$SITE_PACKAGES" ]; then
        ls -la "$SITE_PACKAGES"
    else
        echo "Site-packages directory not found!"
    fi
fi
echo "=============================="

# Print the Python executable path (to verify we're using the right environment)
echo "=== PYTHON EXECUTABLE PATH ==="
PYTHON_PATH=$(micromamba run -p /opt/conda which python 2>/dev/null || echo "NOT FOUND")
echo "$PYTHON_PATH"
echo "=============================="

# Check if Python is available
if [ "$PYTHON_PATH" != "NOT FOUND" ]; then
    echo "Starting uvicorn with python -m approach..."
    exec micromamba run -p /opt/conda python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
else
    echo "ERROR: Python not found in environment! Cannot start service."
    exit 1
fi
