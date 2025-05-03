import os
import asyncio
import random
import boto3
from botocore import UNSIGNED
from botocore.compat import total_seconds
from botocore.config import Config

from pathlib import Path
from datetime import datetime
import logging
from tracker import active_processes, metadata_cache, job_tracker as tracker

from sqlalchemy import create_engine, text

# Configuration
MAX_CONCURRENT_FILES = int(os.getenv("MAX_CONCURRENT_FILES", 2))
PROCESS_SEM = asyncio.Semaphore(MAX_CONCURRENT_FILES)
TMP_DIR = Path(os.getenv("TMP_DIR", "/tmp/shared"))
TMP_DIR.mkdir(parents=True, exist_ok=True)
MAX_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", 1500)) * 1024 * 1024
DATABASE_URL = os.getenv("DATABASE_URL")

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


process_lock = asyncio.Lock()
CACHE_TTL = 3600  # 1 hour
# S3 Client with connection pooling
s3 = boto3.client(
    "s3",
    config=Config(
        signature_version=UNSIGNED,
        max_pool_connections=20,  # Increased connection pool
    ),
)


def run_migrations(engine):
    migration_dir = "migrations"

    # Ensure the directory exists
    if not os.path.isdir(migration_dir):
        logger.info(f"Migration directory '{migration_dir}' not found.")
        return

    with engine.begin() as conn:  # auto-commits or rolls back on failure
        # 1. Create tracking table if it doesn't exist
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        )

        # 2. Collect all SQL files sorted by filename
        files = sorted(f for f in os.listdir(migration_dir) if f.endswith(".sql"))

        for filename in files:
            # 3. Check if the file has already been applied
            result = conn.execute(
                text("SELECT 1 FROM schema_migrations WHERE filename = :filename"),
                {"filename": filename},
            )
            if result.scalar():
                logger.info(f"✓ {filename} already applied, skipping")
                continue

            # 4. Read and execute the SQL file
            logger.info(f"🔁 Applying {filename}...")
            path = os.path.join(migration_dir, filename)
            with open(path, "r") as f:
                sql = f.read()
                conn.execute(text(sql))  # Execute file content

            # 5. Record the migration as applied
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (filename, applied_at) VALUES (:filename, :applied_at)"
                ),
                {"filename": filename, "applied_at": datetime.utcnow()},
            )
            logger.info(f"✅ {filename} applied")
    logger.info("🎉 All migrations complete.")


def check_database_connection():
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful.")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return False


async def load_collections():
    collections_dir = "migrations/collections"
    try:
        files = sorted(f for f in os.listdir(collections_dir) if f.endswith(".json"))
        for filename in files:
            logger.info(f"🔁 Inserting collection: {filename}...")

            file_path = os.path.join(collections_dir, filename)

            proc = await asyncio.create_subprocess_exec(
                "micromamba", "run", "-p", "/opt/conda", "pypgstac",
                "load",
                "collections",
                file_path,
                f"--dsn={DATABASE_URL}",
                "--method=insert_ignore",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise Exception(f"Database migration failed: {stderr.decode().strip()}")

            logger.info(f"Collection {filename} loaded successfully 🎉")
    except Exception as e:
        logger.error(f"Failed to load collections: {str(e)}")
        return False


async def load_queryables(index_fields: list):
    queryables_dir = "migrations/queryables"
    try:
        files = sorted(f for f in os.listdir(queryables_dir) if f.endswith(".json"))
        for filename in files:
            logger.info(f"🔁 Inserting queryables: {filename}...")

            file_path = os.path.join(queryables_dir, filename)

            proc = await asyncio.create_subprocess_exec(
                "micromamba", "run", "-p", "/opt/conda", "pypgstac",
                "load_queryables",
                file_path,
                f"--dsn={DATABASE_URL}",
                f"--index-fields={','.join(index_fields)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise Exception(
                    f"Database migration for queryables failed: {stderr.decode().strip()}"
                )

            logger.info(f"Queryables {filename} loaded successfully 🎉")
    except Exception as e:
        logger.error(f"Failed to load queryables: {str(e)}")
        return False


async def initialize_database_task(job_id: str, migrate: bool):
    try:
        tracker.update_job(
            job_id,
            lambda data: data.update(
                {
                    **data,
                    "status": "processing",
                    "message": "Starting database initialization",
                }
            ),
        )
        engine = create_engine(DATABASE_URL)

        # Run migrations if requested
        if migrate:
            tracker.update_job(
                job_id,
                lambda data: data.update(
                    {**data, "message": "Running database migrations"}
                ),
            )

            proc = await asyncio.create_subprocess_exec(
                "micromamba", "run", "-p", "/opt/conda", "pypgstac",
                "migrate",
                f"--dsn={DATABASE_URL}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info(f"Running migrations with command: pypgstac migrate")

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise Exception(f"Database migration failed: {stderr.decode().strip()}")

            tracker.update_job(
                job_id,
                lambda data: data.update(
                    {**data, "message": "Built-in database migrations complete"}
                ),
            )

        await load_collections()
        await load_queryables(["dt_days", "created"])
        run_migrations(engine)

        tracker.update_job(
            job_id,
            lambda data: data.update(
                {
                    **data,
                    "status": "completed",
                    "message": "Database initialization completed successfully 🎉",
                    "completed_at": datetime.now().isoformat(),
                }
            ),
        )

    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        tracker.update_job(
            job_id,
            lambda data: data.update(
                {
                    **data,
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now().isoformat(),
                }
            ),
        )


async def process_files(job_id: str):
    try:
        job_data = tracker.get_job(job_id, details=True)
        if job_data.get("status") == "cancelled":
            return

        params = job_data["parameters"]
        files = discover_files(
            params["bucket"], params["path"], params["recursive"], params["year"]
        )

        tracker.update_job(
            job_id,
            lambda data: data["summary"].update(
                {**data["summary"], "total_files": len(files), "progress": 0.0}
            ),
        )
        total_files = len(files)

        for batch_start in range(0, total_files):
            job = tracker.get_job(job_id)
            logger.info(f"Processing batch for job {job_id}")
            if job and job.get("status") == "cancelled":
                tracker.update_job(
                    job_id,
                    lambda data: data.update(
                        {
                            **data,
                            "status": "cancelled",
                            "error": "Job was cancelled during processing",
                        }
                    ),
                )
                break

            logger.info(f"Job: {batch_start}, Job status: {job.get('status')}")
            bucket = params["bucket"]
            key = files[batch_start][1]
            await process_file(job_id, bucket, key, batch_start, total_files)

        current_status = tracker.get_job(job_id).get("status")
        if current_status != "cancelled":
            tracker.update_job(
                job_id,
                lambda data: data.update(
                    {
                        **data,
                        "status": "completed",
                        "summary": {
                            "progress": 100.0,
                            "processed": len(files),
                            "succeeded": data["summary"]["succeeded"],
                            "failed": data["summary"]["failed"],
                        },
                    }
                ),
            )

    except asyncio.CancelledError:
        tracker.update_job(
            job_id,
            lambda data: data.update(
                {
                    **data,
                    "status": "cancelled",
                    "error": "Job was cancelled during processing",
                }
            ),
        )
        raise
    except Exception as e:
        logger.error(f"Job processing failed: {str(e)}")
        tracker.update_job(
            job_id,
            lambda data: data.update({**data, "status": "failed", "error": str(e)}),
        )


async def process_file(job_id: str, bucket: str, key: str, index: int, total: int):
    s3_path = f"s3://{bucket}/{key}"
    tmp_path = TMP_DIR / f"{job_id}_{os.path.basename(key)}"
    proc = None

    try:
        # Use cached metadata if available
        cache_key = f"{bucket}:{key}"
        if cache_key in metadata_cache:
            metadata = metadata_cache[cache_key]
            logger.info(f"Using cached metadata for {cache_key}")
        else:
            metadata = tracker.get_file_metadata(bucket, key)
            metadata_cache[cache_key] = metadata
            logger.info(f"Fetched metadata for {cache_key}")

        size_mb = round(metadata["size_bytes"] / 1024 / 1024, 2)
        etag = metadata["etag"]

        # Check for existing successful ingest
        existing = check_existing_ingest(job_id, bucket, key, size_mb, etag)

        if existing:
            logger.info(f"File {s3_path} already ingested successfully, skipping")
            tracker.update_job(
                job_id,
                lambda data: {
                    **data,
                    "summary": {
                        "total_files": data["summary"]["total_files"],
                        "processed": data["summary"]["processed"] + 1,
                        "skipped": data["summary"].get("skipped", 0) + 1,
                        "succeeded": data["summary"]["succeeded"],
                        "failed": data["summary"]["failed"],
                    },
                    "details": {
                        **data["details"],
                        s3_path: {
                            "status": "skipped",
                            "reason": "Duplicate file - already ingested with same size and checksum",
                            "size_mb": size_mb,
                            "etag": etag,
                            "skipped_at": datetime.now().isoformat(),
                        },
                    },
                },
            )
            return

        tracker.update_job(
            job_id,
            lambda data: data["details"].update(
                {
                    s3_path: {
                        **data["details"].get(s3_path, {}),
                        "status": "processing",
                        "started_at": datetime.now().isoformat(),
                        "size_mb": metadata["size_bytes"] / 1024 / 1024,
                    }
                }
            ),
        )

        if metadata["size_bytes"] > MAX_SIZE:
            logger.error(f"File {key} exceeds size limit")
            raise ValueError(
                f"File {key} exceeds size limit "
                f"({metadata['size_bytes'] / 1024 / 1024:.2f}MB > {MAX_SIZE / 1024 / 1024}MB)"
            )

        # Fetch file with optimized chunk size
        logger.info(f"Downloading {s3_path} to {tmp_path}")
        download_file(bucket, key, tmp_path)

        count_proc = await asyncio.create_subprocess_exec(
            "wc",
            "-l",
            str(tmp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await count_proc.communicate()

        if count_proc.returncode != 0:
            raise Exception(f"Count failed: {stderr.decode().strip()}")

        try:
            count = int(stdout.decode().strip().split()[0])
        except (IndexError, ValueError) as e:
            raise Exception(f"Invalid count output: {stdout.decode()}, Error: {e}")

        proc = await asyncio.create_subprocess_exec(
            "micromamba", "run", "-p", "/opt/conda", "pypgstac",
            "load",
            "items",
            str(tmp_path),
            "--method=insert_ignore",
            f"--dsn={DATABASE_URL}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async with process_lock:
            active_processes[job_id].append(proc)

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise Exception(f"PGStac failed: {stderr.decode().strip()}")
        logger.info(f"File {s3_path} processed successfully 🎉")

        tracker.update_job(
            job_id,
            lambda data: {
                **data,
                "summary": {
                    **data["summary"],
                    "processed": data["summary"]["processed"] + 1,
                    "succeeded": data["summary"]["succeeded"] + 1,
                    "progress": (data["summary"].get("processed", 0) + 1) / total * 100,
                },
                "details": {
                    **data["details"],
                    s3_path: {
                        **data["details"].get(s3_path, {}),
                        "status": "success",
                        "item_count": count,
                        "size_mb": round(size_mb, 2),
                        "etag": etag,
                        "completed_at": datetime.now().isoformat(),
                        "ingest_time": round((datetime.now() - datetime.fromisoformat(data["details"][s3_path]["started_at"])).total_seconds() / 60)
                    },
                },
            },
        )

    except asyncio.CancelledError:
        tracker.update_job(
            job_id,
            lambda data: {
                **data,
                "summary": {
                    **data["summary"],
                    "processed": data["summary"]["processed"] + 1,
                    "failed": data["summary"]["failed"] + 1,
                },
                "details": {
                    **data["details"],
                    s3_path: {
                        "status": "cancelled",
                        "error": "Processing cancelled",
                        "completed_at": datetime.now().isoformat(),
                    },
                },
            },
        )
        raise
    except Exception as e:
        logger.error(f"File processing failed: {str(e)}", exc_info=True)
        tracker.update_job(
            job_id,
            lambda data: {
                **data,
                "summary": {
                    **data["summary"],
                    "processed": data["summary"]["processed"] + 1,
                    "failed": data["summary"]["failed"] + 1,
                },
                "details": {
                    **data["details"],
                    s3_path: {
                        "status": "failed",
                        "error": str(e),
                        "completed_at": datetime.now().isoformat(),
                    },
                },
            },
        )
    finally:
        if proc:
            async with process_lock:
                try:
                    active_processes[job_id].remove(proc)
                except ValueError:
                    pass
        if tmp_path.exists():
            logger.info(f"Cleaning up temporary file {tmp_path}")
            tmp_path.unlink()


def download_file(bucket, key, target_path):
    """Optimized file download with better chunking"""
    with open(target_path, "wb") as f:
        response = s3.get_object(Bucket=bucket, Key=key)
        chunk_size = 10 * 1024 * 1024  # 10MB chunks
        body = response["Body"]

        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)


def check_existing_ingest(job_id, bucket, key, size_mb, etag):
    """Check if file was already successfully ingested in previous jobs"""
    s3_path = f"s3://{bucket}/{key}"

    for past_job_id in tracker.list_jobs():
        if past_job_id == job_id:
            continue
        past_job = tracker.get_job(past_job_id, details=True)
        if not past_job:
            continue
        file_entry = past_job.get("details", {}).get(s3_path)
        if file_entry and file_entry["status"] == "success":
            if file_entry["size_mb"] == size_mb and file_entry["etag"] == etag:
                return True
    return False


async def dummy_subtask(job_id: str, index: int, total: int):
    """Simulate a dummy subtask and update progress atomically"""
    sleep_time = random.randint(10, 30)
    await asyncio.sleep(sleep_time)  # Simulate work

    # Update summary with incremented counters and recalculated progress
    tracker.update_job(
        job_id,
        lambda data: {
            **data,
            "summary": {
                **data["summary"],
                "processed": data["summary"].get("processed", 0) + 1,
                "succeeded": data["summary"].get("succeeded", 0) + 1,
                "progress": data["summary"].get("processed", 0) / total * 100,
                "total_files": total,
            },
        },
    )

    # Update task-specific details
    tracker.update_job(
        job_id,
        lambda data: {
            **data,
            "details": {
                **data.get("details", {}),
                f"dummy_task_{index}": {
                    "status": "completed",
                    "message": f"Dummy task {index} completed",
                    "completed_at": datetime.now().isoformat(),
                },
            },
        },
    )


async def dummy_task(job_id: str, name: str, tasks_to_run: int, concurrent_tasks: int):
    try:
        # Initial job setup
        tracker.update_job(
            job_id,
            lambda data: {
                "summary": {
                    "total_files": tasks_to_run,
                    "progress": 0.0,
                    "succeeded": 0,
                    "name": name,
                },
                **data,
            },
        )
        logger.info(f"Starting dummy task {name} with {tasks_to_run} tasks")

        # Process tasks in batches
        if concurrent_tasks > MAX_CONCURRENT_FILES:
            concurrent_tasks = MAX_CONCURRENT_FILES
            logger.warning(f"Concurrent tasks limited to {MAX_CONCURRENT_FILES}")
        for batch_start in range(0, tasks_to_run, concurrent_tasks):
            job = tracker.get_job(job_id)
            logger.info(f"Processing batch for job {job_id}")
            if job and job.get("status") == "cancelled":
                tracker.update_job(
                    job_id,
                    lambda data: data.update(
                        {
                            **data,
                            "status": "cancelled",
                            "error": "Job was cancelled during processing",
                        }
                    ),
                )
                break

            logger.info(f"Batch start: {batch_start}, Job status: {job.get('status')}")
            batch_end = min(batch_start + concurrent_tasks, tasks_to_run)
            batch_tasks = [
                dummy_subtask(job_id, index, tasks_to_run)
                for index in range(batch_start, batch_end)
            ]
            await asyncio.gather(*batch_tasks)

        # Final completion check
        if tracker.get_job(job_id).get("status") != "cancelled":
            tracker.update_job(
                job_id,
                lambda data: {
                    **data,
                    "status": "completed",
                    "summary": {
                        **data["summary"],
                        "progress": 100.0,
                        "processed": tasks_to_run,
                    },
                },
            )

    except asyncio.CancelledError:
        # tracker.update_job(job_id, {"status": "cancelled"})
        tracker.update_job(
            job_id,
            lambda data: data.update(
                {
                    **data,
                    "status": "cancelled",
                    "error": "Job was cancelled during processing",
                }
            ),
        )
    except Exception as e:
        tracker.update_job(job_id, {"status": "failed", "error": str(e)})


def discover_files(bucket: str, path: str, recursive: bool, year: int = None) -> list:
    """Discover STAC files with more efficient pagination"""
    prefix = path.rstrip("/") + "/"
    files = []

    paginator = s3.get_paginator("list_objects_v2")
    operation_params = {
        "Bucket": bucket,
        "Prefix": prefix,
        "Delimiter": "/" if not recursive else "",
        "MaxKeys": 1000,  # Max allowed by S3
    }

    for page in paginator.paginate(**operation_params):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".ndjson"):
                continue

            filename = key.split("/")[-1].split(".")[0]
            if not (filename.isdigit() and len(filename) == 4):
                continue

            file_year = int(filename)
            if year and file_year != year:
                continue

            files.append((bucket, key))

    return files
