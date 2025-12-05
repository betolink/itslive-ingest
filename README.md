# itslive-ingest
ITS_LIVE STAC ingest app

## Overview

This application initializes a PGSTAC database and ingests ITS_LIVE collections:
- **velocity-granules**: Large dataset processed from S3 (Landsat image-pair velocities)
- **itslive-cubes**: Cloud-optimized Zarr cubes (small dataset, loaded from local files)
- **velocity-mosaics**: Regional glacier velocities (small dataset, loaded from local files)

## Usage

### Database Initialization

Initialize the database with all collections and items:

```bash
curl -X POST "http://localhost:8000/initdb?migrate=true" \
  -H "X-API-Token: your-token"
```

This will:
1. Run PGSTAC migrations (if `migrate=true`)
2. Load all three collections
3. Load items for cubes and mosaics from local files
4. Load queryables and run custom migrations

### Granule Ingestion

For the large velocity-granules collection, use the S3-based ingestion:

```bash
curl -X POST "http://localhost:8000/ingest?bucket=its-live-data&path=velocity_mosaic/2024/&recursive=true" \
  -H "X-API-Token: your-token"
```

## Collections

### velocity-granules
- **ID**: `velocity-granules`
- **Source**: S3-based processing
- **Size**: Large dataset processed in batches
- **Items**: Loaded dynamically from S3 NDJSON files

### itslive-cubes
- **ID**: `itslive-cubes`
- **Source**: Local file (`migrations/collections/items/cube-items.json`)
- **Size**: 3,160 items
- **Items**: Loaded automatically during DB initialization

### velocity-mosaics
- **ID**: `velocity-mosaics`
- **Source**: Local file (`migrations/collections/items/velocity-mosaics-items.json`)
- **Size**: 582 items
- **Items**: Loaded automatically during DB initialization

## API Endpoints

- `POST /initdb` - Initialize database with all collections
- `POST /ingest` - Ingest granules from S3
- `GET /jobs/{job_id}` - Check job status
- `GET /health` - Health check
- `GET /database` - Test database connection
