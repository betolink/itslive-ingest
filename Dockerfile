# Use a minimal base image
FROM mambaorg/micromamba:latest

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    MAMBA_ROOT_PREFIX="/opt/conda" \
    PATH="/opt/conda/bin:$PATH"

# Work in the /app directory
WORKDIR /app

# Copy only the conda-lock file first (for better caching)
COPY conda-lock.yml ./

# Install dependencies from the lock file
# Using micromamba's explicit environment creation for maximum reproducibility
RUN micromamba create -y -p /opt/conda -f conda-lock.yml && \
    micromamba run -p /opt/conda pip install pypgstac[psycopg] && \
    micromamba clean --all --yes && \
    find /opt/conda/ -follow -type f -name '*.a' -delete && \
    find /opt/conda/ -follow -type f -name '*.js.map' -delete && \
    find /opt/conda/ -name '*.pyc' -delete && \
    find /opt/conda/ -name '__pycache__' -exec rm -rf {} + || true

COPY ./app .

EXPOSE 8000


ENTRYPOINT ["/app/entrypoint.sh"]

