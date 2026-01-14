# ITS_LIVE Ingestion Strategies

This document describes the different methods for ingesting STAC items into the ITS_LIVE catalog, including performance expectations and use cases.

## Overview

There are four primary ingestion pathways:

| Method | Format | Endpoint | Auth Required | Best For |
|--------|--------|----------|---------------|----------|
| Ingest Agent (S3) | NDJSON | `https://ingest.itslive.cloud/ingest` | Yes | Large-scale batch processing from S3 |
| Ingest Agent (URL) | NDJSON | `https://ingest.itslive.cloud/ingest/granules` | Yes | NDJSON from HTTP URLs |
| STAC API Bulk | JSON | `https://stac.itslive.cloud/collections/{id}/bulk_items` | Yes | Programmatic bulk inserts |
| STAC API Single | JSON | `https://stac.itslive.cloud/collections/{id}/items` | Yes | Real-time single item ingest |

---

## 1. Ingest Agent (S3-Based NDJSON Processing)

The ingest-agent is designed for high-volume batch ingestion from NDJSON (newline-delimited JSON) files stored in S3.

### Endpoint

```
POST https://ingest.itslive.cloud/ingest
```

### Usage

```bash
curl -X POST "https://ingest.itslive.cloud/ingest?bucket=its-live-data&path=stac/velocity-granules/&recursive=true" \
  -H "X-API-Token: YOUR_API_TOKEN"
```

### Parameters

| Parameter | Description | Required |
|-----------|-------------|----------|
| `bucket` | S3 bucket name | Yes |
| `path` | S3 prefix path | Yes |
| `recursive` | Search subdirectories (default: false) | No |
| `year` | Filter by year | No |
| `collection_id` | Collection configuration to use | No |

### NDJSON Format

Each line in the S3 files is a complete STAC item JSON object:

```json
{"type": "Feature", "stac_version": "1.0.0", "id": "item-1", "geometry": {...}, "properties": {...}, ...}
{"type": "Feature", "stac_version": "1.0.0", "id": "item-2", "geometry": {...}, "properties": {...}, ...}
{"type": "Feature", "stac_version": "1.0.0", "id": "item-3", "geometry": {...}, "properties": {...}, ...}
```

### When to Use

- Large-scale batch ingestion (100,000+ items)
- Initial catalog population
- Processing pipelines that output to S3
- Background/async processing with job tracking

### Performance (2-core VM)

| Metric | Expected Value |
|--------|----------------|
| Throughput | 500-1,000 items/second |
| Memory usage | ~200-500 MB per file |
| Batch size recommendation | 10,000-50,000 items per file |
| Concurrent files | 2 (default `MAX_CONCURRENT_FILES`) |
| Max file size | 1.5 GB (configurable via `MAX_FILE_SIZE_MB`) |

---

## 2. Ingest Agent (URL-Based NDJSON Processing)

The ingest-agent can also fetch NDJSON directly from HTTP/HTTPS URLs.

### Endpoint

```
POST https://ingest.itslive.cloud/ingest/granules
```

### Usage

```bash
curl -X POST "https://ingest.itslive.cloud/ingest/granules?url=https://example.com/granules.ndjson" \
  -H "X-API-Token: YOUR_API_TOKEN"
```

### Parameters

| Parameter | Description | Required |
|-----------|-------------|----------|
| `url` | HTTP/HTTPS URL pointing to NDJSON content | Yes |

### When to Use

- NDJSON files hosted on web servers
- Integration with external data providers
- Dynamic NDJSON generation from APIs
- When S3 upload is not practical

### Performance (2-core VM)

| Metric | Expected Value |
|--------|----------------|
| Throughput | 500-1,000 items/second |
| Memory usage | ~200-500 MB |
| Network | Limited by source server bandwidth |

---

## 3. STAC API Bulk Items

The native STAC API bulk endpoint accepts JSON with items keyed by ID. This is useful for programmatic inserts when you don't have NDJSON files or need direct API integration.

### Endpoint

```
POST https://stac.itslive.cloud/collections/{collection_id}/bulk_items
```

### Usage

```bash
curl -X POST "https://stac.itslive.cloud/collections/velocity-granules/bulk_items" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_STAC_API_TOKEN" \
  -d '{
    "items": {
      "item-id-1": { ...stac item 1... },
      "item-id-2": { ...stac item 2... }
    },
    "method": "upsert"
  }'
```

### Request Format

```json
{
  "items": {
    "item-id-1": {
      "type": "Feature",
      "stac_version": "1.0.0",
      "geometry": {...},
      "properties": {...},
      "assets": {...}
    },
    "item-id-2": {...}
  },
  "method": "upsert"
}
```

### Methods

| Method | Behavior |
|--------|----------|
| `insert` | Insert new items, fail on duplicates |
| `insert_ignore` | Insert new items, skip duplicates |
| `upsert` | Insert new items, update existing |

### Converting NDJSON to Bulk Format

If you have NDJSON and need to use the bulk API:

```bash
# Convert ndjson to bulk format
jq -s 'map({(.id): .}) | add | {items: ., method: "upsert"}' your-granules.ndjson > bulk.json

# Then POST to bulk_items
curl -X POST "https://stac.itslive.cloud/collections/velocity-granules/bulk_items" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_STAC_API_TOKEN" \
  -d @bulk.json
```

### When to Use

- Programmatic batch inserts from applications
- When items are already in memory as objects
- Integration with processing pipelines that produce JSON

### Performance (2-core VM)

| Metric | Expected Value |
|--------|----------------|
| Throughput | 200-500 items/second |
| Recommended batch size | 500-1,000 items per request |
| Max request size | ~10 MB |
| Latency per request | 1-5 seconds for 500 items |

---

## 4. STAC API Single Item (Real-time)

For real-time ingestion of individual items as they are produced.

### Endpoint

```
POST https://stac.itslive.cloud/collections/{collection_id}/items
```

### Usage

```bash
curl -X POST "https://stac.itslive.cloud/collections/velocity-granules/items" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_STAC_API_TOKEN" \
  -d '{
    "type": "Feature",
    "stac_version": "1.0.0",
    "id": "unique-item-id",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]]]
    },
    "bbox": [-180, -90, 180, 90],
    "properties": {
      "datetime": "2024-01-15T00:00:00Z",
      "created": "2024-01-15T12:00:00Z"
    },
    "links": [],
    "assets": {}
  }'
```

### When to Use

- Real-time ingest as data is produced
- Event-driven pipelines (SNS/SQS triggers)
- Low-to-medium volume updates (up to 5,000 items)
- Webhook integrations

### Performance (2-core VM)

| Metric | Expected Value |
|--------|----------------|
| Throughput | 20-50 items/second (per request) |
| Latency per item | 50-200 ms |
| Max concurrent requests | 10 recommended |
| Pause between batches | 2 seconds |
| Sustained throughput | ~200-300 items/minute |
| Memory overhead | Minimal (~50 MB) |

**Note:** For volumes over 5,000 items, consider using the Bulk API [3] or Ingest Agent [4][5] for better efficiency.

---

## Performance Tuning for 2-Core VM

### Environment Variables

| Variable | Default | Recommended | Description |
|----------|---------|-------------|-------------|
| `MAX_CONCURRENT_FILES` | 2 | 2 | Number of files processed in parallel |
| `MAX_FILE_SIZE_MB` | 1500 | 1500 | Maximum file size in MB |
| `TMP_DIR` | `/tmp/shared` | SSD-backed path | Temporary file storage |

### Resource Estimates

For a 2-core VM with 4 GB RAM:

| Workload | CPU Usage | Memory | Disk I/O |
|----------|-----------|--------|----------|
| Single item ingest | 5-10% | 100 MB | Low |
| Bulk API (500 items) | 20-40% | 200 MB | Medium |
| S3 file processing | 50-80% | 500 MB | High |
| 2 concurrent files | 80-100% | 800 MB | Very High |

### Recommendations

1. **For real-time ingest**: Use single-item endpoint with connection pooling
2. **For batch jobs**: Use S3-based ingestion during off-peak hours
3. **For medium batches**: Use bulk API with 500-item batches
4. **Memory**: Ensure at least 2 GB free for file processing
5. **Disk**: Use SSD-backed storage for `TMP_DIR`

---

## Choosing the Right Strategy

```
                      ┌─────────────────────────────────────┐
                      │         How many items?             │
                      └─────────────────────────────────────┘
                                       │
                      ┌────────────────┼────────────────┐
                      ▼                ▼                ▼
                  1-5,000        1K-10K           10K-100K+
                      │                │                │
                      ▼                ▼                ▼
              ┌───────────┐    ┌───────────┐    ┌───────────────┐
              │  Single   │    │   Bulk    │    │  Ingest Agent │
              │  Item API │    │    API    │    │   (NDJSON)    │
              └───────────┘    └───────────┘    └───────────────┘
                    │                │                │
                    ▼          Already NDJSON?   Where is NDJSON?
              ┌─────────┐            │                │
              │   [1]   │     ┌──────┴──────┐   ┌─────┴─────┐
              └─────────┘     ▼             ▼   ▼           ▼
               10 concurrent ┌─────┐   ┌─────┐ ┌─────┐ ┌─────┐
               + 2s pause    │ [2] │   │ [3] │ │ [4] │ │ [5] │
                             └─────┘   └─────┘ └─────┘ └─────┘
                             Convert   Use      HTTP    S3
                             to JSON   Bulk     URL     Bucket
                                       API
```

---

## Workflow Details

### [1] Single Item API

**Use when:** Ingesting 1-5,000 items in real-time as they are produced.

**Performance:** 20-50 items/sec with concurrency limits

**Concurrency guidance for 2-core VM:**
- Maximum 10 concurrent requests
- Add 2-second pause between batches of 10
- Expected throughput: ~200-300 items/minute sustained

```bash
# Single STAC item ingest
curl -X POST "https://stac.itslive.cloud/collections/velocity-granules/items" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $STAC_API_TOKEN" \
  -d '{
    "type": "Feature",
    "stac_version": "1.0.0",
    "id": "LC08_L1TP_042034_20231215_20231220_02_T1_X_LC08_L1TP_042034_20231201_20231206_02_T1_G0120V02_P095",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[-122.5, 37.5], [-121.5, 37.5], [-121.5, 38.5], [-122.5, 38.5], [-122.5, 37.5]]]
    },
    "bbox": [-122.5, 37.5, -121.5, 38.5],
    "properties": {
      "datetime": "2023-12-15T00:00:00Z",
      "created": "2023-12-20T12:00:00Z",
      "mission": "landsat",
      "satellite": "8",
      "dt_days": 14
    },
    "collection": "velocity-granules",
    "links": [],
    "assets": {
      "data": {
        "href": "s3://its-live-data/velocity_image_pair/landsat/v02/N60W140/LC08_L1TP_042034.nc",
        "type": "application/x-netcdf"
      }
    }
  }'
```

**Python example for multiple items (with rate limiting):**

```python
import httpx
import asyncio

async def ingest_items(items: list[dict], token: str, batch_size: int = 10, pause_seconds: float = 2.0):
    """
    Ingest items with concurrency control to avoid overwhelming the server.
    
    Args:
        items: List of STAC items to ingest
        token: API authentication token
        batch_size: Max concurrent requests (default: 10)
        pause_seconds: Pause between batches (default: 2.0)
    """
    results = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            
            # Process batch concurrently
            tasks = [
                client.post(
                    f"https://stac.itslive.cloud/collections/{item['collection']}/items",
                    json=item,
                    headers={"X-API-Key": token}
                )
                for item in batch
            ]
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for item, response in zip(batch, responses):
                if isinstance(response, Exception):
                    results.append({"id": item["id"], "status": "error", "error": str(response)})
                elif response.status_code < 300:
                    results.append({"id": item["id"], "status": "success"})
                else:
                    results.append({"id": item["id"], "status": "error", "error": response.text})
            
            # Pause between batches to avoid overwhelming the server
            if i + batch_size < len(items):
                await asyncio.sleep(pause_seconds)
    
    return results

# Usage: ingest up to 5,000 items with rate limiting
items = [{"id": f"item-{i}", "collection": "velocity-granules", ...} for i in range(3000)]
results = asyncio.run(ingest_items(items, "your-token"))
succeeded = sum(1 for r in results if r["status"] == "success")
print(f"Ingested {succeeded}/{len(items)} items")
```

---

### [2] Convert NDJSON to Bulk JSON

**Use when:** You have NDJSON files but need to use the bulk API (1,000-10,000 items).

**Performance:** Conversion is fast; bulk API handles 200-500 items/sec

```bash
# Step 1: Convert NDJSON to bulk format
jq -s 'map({(.id): .}) | add | {items: ., method: "upsert"}' granules.ndjson > bulk.json

# Step 2: POST to bulk_items endpoint
curl -X POST "https://stac.itslive.cloud/collections/velocity-granules/bulk_items" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $STAC_API_TOKEN" \
  -d @bulk.json
```

**For large NDJSON files (up to 10K items), split into chunks first:**

```bash
# Split NDJSON into 1000-line chunks (manageable for bulk API)
split -l 1000 granules.ndjson chunk_

# Convert and upload each chunk
for chunk in chunk_*; do
  jq -s 'map({(.id): .}) | add | {items: ., method: "upsert"}' "$chunk" > "${chunk}.json"
  
  curl -X POST "https://stac.itslive.cloud/collections/velocity-granules/bulk_items" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $STAC_API_TOKEN" \
    -d @"${chunk}.json"
  
  rm "$chunk" "${chunk}.json"
done
```

---

### [3] Bulk API with JSON Objects

**Use when:** You have items as JSON objects in memory (1,000-10,000 items).

**Performance:** 200-500 items/sec, 1-5 seconds per batch of 500

```bash
# Direct bulk insert with JSON
curl -X POST "https://stac.itslive.cloud/collections/velocity-granules/bulk_items" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $STAC_API_TOKEN" \
  -d '{
    "items": {
      "item-001": {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": "item-001",
        "geometry": {"type": "Polygon", "coordinates": [[[-122, 37], [-121, 37], [-121, 38], [-122, 38], [-122, 37]]]},
        "bbox": [-122, 37, -121, 38],
        "properties": {"datetime": "2023-12-15T00:00:00Z"},
        "collection": "velocity-granules",
        "links": [],
        "assets": {}
      },
      "item-002": {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": "item-002",
        "geometry": {"type": "Polygon", "coordinates": [[[-120, 36], [-119, 36], [-119, 37], [-120, 37], [-120, 36]]]},
        "bbox": [-120, 36, -119, 37],
        "properties": {"datetime": "2023-12-16T00:00:00Z"},
        "collection": "velocity-granules",
        "links": [],
        "assets": {}
      }
    },
    "method": "upsert"
  }'
```

**Python example for batched bulk insert:**

```python
import httpx

def bulk_ingest(items: list[dict], token: str, batch_size: int = 500):
    """Bulk ingest items in batches"""
    results = []
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        
        # Convert list to dict keyed by ID
        items_dict = {item["id"]: item for item in batch}
        
        response = httpx.post(
            "https://stac.itslive.cloud/collections/velocity-granules/bulk_items",
            json={"items": items_dict, "method": "upsert"},
            headers={"X-API-Key": token},
            timeout=60.0
        )
        response.raise_for_status()
        results.append({"batch": i // batch_size, "count": len(batch)})
    
    return results

# Usage
items = [{"id": f"item-{i}", ...} for i in range(5000)]
bulk_ingest(items, "your-token", batch_size=500)
```

---

### [4] Ingest NDJSON from HTTP URL

**Use when:** You have NDJSON hosted on a web server or API endpoint (10,000-100,000+ items).

**Performance:** 500-1,000 items/sec, runs asynchronously with job tracking

**Batching recommendation:** For datasets larger than 50,000 items, split into multiple NDJSON files of ~50,000 items each and process sequentially to avoid timeouts.

```bash
# Ingest NDJSON directly from a URL
curl -X POST "https://ingest.itslive.cloud/ingest/granules?url=https://example.com/data/granules.ndjson" \
  -H "X-API-Token: $INGEST_API_TOKEN"

# Response includes job_id:
# {"job_id": "abc123", "status": "pending", "links": {"status": "/jobs/abc123"}}
```

**Monitor job progress:**

```bash
# Check job status
curl "https://ingest.itslive.cloud/jobs/abc123"

# Response:
# {
#   "job_id": "abc123",
#   "status": "completed",
#   "summary": {
#     "total_files": 1,
#     "processed": 1,
#     "succeeded": 1,
#     "failed": 0,
#     "progress": 100.0,
#     "items_processed": 15000
#   }
# }
```

**Python example:**

```python
import httpx

def ingest_from_url(ndjson_url: str, token: str) -> dict:
    """Trigger ingestion from an HTTP URL"""
    response = httpx.post(
        "https://ingest.itslive.cloud/ingest/granules",
        params={"url": ndjson_url},
        headers={"X-API-Token": token},
        timeout=30.0
    )
    response.raise_for_status()
    return response.json()

def wait_for_job(job_id: str) -> dict:
    """Poll until job completes"""
    while True:
        response = httpx.get(f"https://ingest.itslive.cloud/jobs/{job_id}")
        job = response.json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(5)

# Usage
job = ingest_from_url("https://example.com/granules.ndjson", "your-token")
result = wait_for_job(job["job_id"])
print(f"Processed {result['summary']['items_processed']} items")
```

---

### [5] Upload NDJSON to S3 for Batch Processing

**Use when:** You have large datasets (10,000-100,000+ items) in S3 that need background processing.

**Performance:** 500-1,000 items/sec, runs asynchronously with job tracking

**Batching recommendation:** For datasets larger than 50,000 items, split into multiple NDJSON files of ~50,000 items each to optimize processing and avoid timeouts.

```bash
# Step 1: Upload NDJSON file(s) to S3
aws s3 cp granules.ndjson s3://its-live-data/stac/velocity-granules/2024/

# Step 2: Trigger S3-based ingestion job
curl -X POST "https://ingest.itslive.cloud/ingest?bucket=its-live-data&path=stac/velocity-granules/2024/&recursive=true" \
  -H "X-API-Token: $INGEST_API_TOKEN"

# Response includes job_id:
# {"job_id": "abc123", "status": "pending", "links": {"status": "/jobs/abc123"}}
```

**Monitor job progress:**

```bash
# Check job status
curl "https://ingest.itslive.cloud/jobs/abc123"

# Response:
# {
#   "job_id": "abc123",
#   "status": "processing",
#   "summary": {
#     "total_files": 5,
#     "processed": 2,
#     "succeeded": 2,
#     "failed": 0,
#     "progress": 40.0
#   }
# }

# Get detailed file-by-file status
curl "https://ingest.itslive.cloud/jobs/abc123?details=true"

# Cancel if needed
curl -X POST "https://ingest.itslive.cloud/jobs/abc123/cancel" \
  -H "X-API-Token: $INGEST_API_TOKEN"
```

**Complete batch workflow script:**

```bash
#!/bin/bash
set -e

BUCKET="its-live-data"
PREFIX="stac/velocity-granules/2024"
TOKEN="$INGEST_API_TOKEN"

# Upload files to S3
echo "Uploading NDJSON files to S3..."
aws s3 sync ./ndjson-output/ "s3://${BUCKET}/${PREFIX}/"

# Start ingestion job
echo "Starting ingestion job..."
RESPONSE=$(curl -s -X POST \
  "https://ingest.itslive.cloud/ingest?bucket=${BUCKET}&path=${PREFIX}/&recursive=true" \
  -H "X-API-Token: ${TOKEN}")

JOB_ID=$(echo "$RESPONSE" | jq -r '.job_id')
echo "Job started: $JOB_ID"

# Poll for completion
while true; do
  STATUS=$(curl -s "https://ingest.itslive.cloud/jobs/${JOB_ID}" | jq -r '.status')
  PROGRESS=$(curl -s "https://ingest.itslive.cloud/jobs/${JOB_ID}" | jq -r '.summary.progress')
  
  echo "Status: $STATUS, Progress: $PROGRESS%"
  
  if [ "$STATUS" = "completed" ]; then
    echo "Ingestion completed successfully!"
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "Ingestion failed!"
    curl -s "https://ingest.itslive.cloud/jobs/${JOB_ID}?details=true" | jq '.details'
    exit 1
  fi
  
  sleep 30
done
```

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Missing or invalid API key | Check `X-API-Key` header |
| 429 Too Many Requests | Rate limit exceeded | Reduce request rate, use batching |
| 413 Payload Too Large | Request body too large | Split into smaller batches |
| 500 Internal Error | Database or processing error | Check logs, retry with backoff |

### Retry Strategy

For production systems, implement exponential backoff:

```python
import time
import random

def ingest_with_retry(items, max_retries=5):
    for attempt in range(max_retries):
        try:
            return post_items(items)
        except (RateLimitError, ServerError) as e:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait)
```

---

## Summary

| Workflow | Use Case | Volume | Method | Expected Rate |
|----------|----------|--------|--------|---------------|
| [1] | Real-time single items | 1-5K | Single Item API | ~300/min (10 concurrent + 2s pause) |
| [2] | NDJSON to bulk API | 1K-10K | Convert + Bulk API | 200-500/sec |
| [3] | Programmatic batches | 1K-10K | Bulk API | 200-500/sec |
| [4] | NDJSON from HTTP URL | 10K-100K+ | Ingest Agent (URL) | 500-1,000/sec |
| [5] | Large-scale S3 files | 10K-100K+ | Ingest Agent (S3) | 500-1,000/sec |

**Note:** For workflows [4] and [5], split NDJSON files into ~50,000 item batches when processing 50,000+ items to optimize performance and avoid timeouts.


