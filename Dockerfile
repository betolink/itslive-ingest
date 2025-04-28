# Use Miniforge3 base image
FROM condaforge/miniforge3

# Set working directory
WORKDIR /app

# Copy environment.yml first to leverage Docker layer caching
COPY conda-linux-64.lock .

# Create the conda environment
RUN conda create --name itslive-ingest --file conda-linux-64.lock && \
    conda clean --all --yes && \
    rm -rf /opt/conda/pkgs

# Activate conda environment in all subsequent RUN, CMD, ENTRYPOINT commands
# SHELL ["conda", "run", "-n", "itslive-ingest", "/bin/bash", "-c"]

# Copy rest of the app
COPY ./app .


EXPOSE 8000
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["conda", "run", "-n", "itslive-ingest", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
