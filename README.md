# itslive-ingest
ITS_LIVE STAC ingest app

## Overview

This application initializes a PGSTAC database and ingests ITS_LIVE collections:
- **velocity-granules**: Large dataset processed from S3 (Landsat image-pair velocities)
- **itslive-cubes**: Cloud-optimized Zarr cubes (small dataset, loaded from local files)
- **velocity-mosaics**: Regional glacier velocities (small dataset, loaded from local files)

The STAC endpoint can be reached at https://stac.itslive.cloud

## Usage

### Database Initialization

Initialize database with all collections and items:

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

For the velocity-granules collection, multiple ingestion strategies are available depending on your data volume and format. See **[ingest.md](./ingest.md)** for detailed documentation on all ingestion methods including:

- **Single Item API** - Real-time ingest of 1-5K items
- **Bulk API** - Batch ingest of 1K-10K items from JSON
- **Ingest Agent (URL)** - NDJSON from HTTP endpoints (10K-100K+ items)
- **Ingest Agent (S3)** - Large-scale batch processing from S3 (10K-100K+ items)

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
- `POST /ingest/granules` - Ingest granules from HTTP URL
- `GET /jobs/{job_id}` - Check job status
- `GET /health` - Health check
- `GET /database` - Test database connection

