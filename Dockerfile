# Use a minimal base image
FROM mambaorg/micromamba:latest

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 

# Work in the /app directory
WORKDIR /app

# Copy only the conda-lock file first (for better caching)
COPY --chown=$MAMBA_USER:$MAMBA_USER conda-lock.yml /tmp/conda-lock.yml

# Install dependencies from the lock file
# Using micromamba's explicit environment creation for maximum reproducibility
RUN micromamba install -y -n base -f /tmp/conda-lock.yml && \
    micromamba run pip install pypgstac[psycopg] && \
    micromamba clean --all --yes 

COPY ./app .

ARG MAMBA_DOCKERFILE_ACTIVATE=1

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
