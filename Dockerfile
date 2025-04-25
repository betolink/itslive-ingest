# Use Miniforge3 base image
FROM condaforge/miniforge3

# Set working directory
WORKDIR /app

# Copy environment.yml first to leverage Docker layer caching
COPY environment.yml .

# Create the conda environment
RUN conda env create -f environment.yml

# Activate conda environment in all subsequent RUN, CMD, ENTRYPOINT commands
SHELL ["conda", "run", "-n", "itslive-ingest", "/bin/bash", "-c"]

# Copy rest of the app
COPY ./app .


EXPOSE 8000
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["conda", "run", "-n", "itslive-ingest", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
