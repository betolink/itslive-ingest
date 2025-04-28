# Use Miniforge3 base image
FROM condaforge/miniforge3

# Set working directory

# Copy environment.yml first to leverage Docker layer caching
COPY conda-linux-64.lock .

# Create the conda environment
RUN conda create --name itslive-ingest --file conda-linux-64.lock && \
    conda run -n itslive-ingest pip install pypgstac[psycopg] && \
    conda clean --all --yes && \
    rm -rf /opt/conda/pkgs

# Activate conda environment in all subsequent RUN, CMD, ENTRYPOINT commands
SHELL ["conda", "run", "-n", "itslive-ingest", "/bin/bash", "-c"]

WORKDIR /app
COPY ./app .

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

