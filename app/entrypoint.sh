#!/bin/bash
set -e

exec micromamba run -p /opt/conda uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info


