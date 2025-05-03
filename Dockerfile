# Use a minimal base image
FROM mambaorg/micromamba:latest

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 

# Work in the /app directory
WORKDIR /app

# Copy only the conda-lock file first (for better caching)
COPY --chown=$MAMBA_USER:$MAMBA_USER conda-lock.yaml /tmp/conda-lock.yaml

# Install dependencies from the lock file
# Using micromamba's explicit environment creation for maximum reproducibility
RUN micromamba install -y -n base -f conda-lock.yml && \
    micromamba install -y -n base pip && \
    micromamba run pip install pypgstac[psycopg] uvicorn && \
    micromamba clean --all --yes 

COPY ./app .

ARG MAMBA_DOCKERFILE_ACTIVATE=1

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
