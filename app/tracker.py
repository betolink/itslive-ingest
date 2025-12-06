import json
import uuid
import threading
import time
import os
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import logging

logger = logging.getLogger(__name__)


STATE_DIR = os.getenv("STATE_DIRECTORY", "./state")


class JobTracker:
    def __init__(self, jobs_dir=f"{STATE_DIR}/jobs"):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.s3 = boto3.client(
            "s3", config=Config(signature_version=UNSIGNED, max_pool_connections=50)
        )
        # In-memory cache for metadata
        self.metadata_cache = {}
        self.cache_expiry = {}
        self.CACHE_TTL = 3600  # 1 hour

        # Locks for thread safety - job level and global
        self.job_locks = {}
        self.global_lock = threading.RLock()  # Reentrant lock

    def _get_job_lock(self, job_id):
        """Get a lock for a specific job, creating it if it doesn't exist"""
        logger.debug(f"Getting lock for job {job_id}")
        if not isinstance(job_id, str):
            # Convert to string or raise an error
            job_id = str(job_id)  # or job_id["job_id"] if it's expected to be a dict

        with self.global_lock:
            if job_id not in self.job_locks:
                self.job_locks[job_id] = threading.RLock()
            return self.job_locks[job_id]

    def create_job(self, bucket, path, recursive, year=None, collection_id=None):
        """Create a new job with thread safety"""
        job_id = str(uuid.uuid4())
        job_file = self.jobs_dir / f"{job_id}.json"

        initial_state = {
            "job_id": job_id,
            "parameters": {
                "bucket": bucket,
                "path": path,
                "recursive": recursive,
                "year": year,
                "collection_id": collection_id,
            },
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "summary": {
                "total_files": 0,
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "progress": 0.0,
            },
            "details": {},
        }

        # Get a lock for this job
        job_lock = self._get_job_lock(job_id)

        with job_lock:
            with open(job_file, "w") as f:
                json.dump(initial_state, f, indent=2)

        return job_id

    def has_active_jobs(self):
        """Check if there are any active jobs with thread safety"""
        with self.global_lock:
            for job_data in self.list_jobs():
                job_id = job_data["job_id"]
                logger.debug(f"Job ID: {job_id}, Status: {job_data['status']}")
                if job_data and job_data.get("status") in ["pending", "processing"]:
                    return job_data
        return False

    def get_jobs_by_status(self, status):
        """Get all jobs with a specific status, with thread safety"""
        jobs = []

        # First get all job IDs under global lock
        with self.global_lock:
            job_ids = self.list_jobs()

        for job_id in job_ids:
            job_data = self.get_job(job_id)
            if job_data and job_data.get("status") == status:
                jobs.append(job_data)
        return jobs

    def update_job(self, job_id, update_fn):
        logger.debug(f"Updating job {job_id}")
        job_file = self.jobs_dir / f"{job_id}.json"
        temp_file = job_file.with_suffix(".tmp")

        job_lock = self._get_job_lock(job_id)
        with job_lock:
            if not job_file.exists():
                logger.warning(f"Attempted to update non-existent job {job_id}")
                return False

            try:
                with open(job_file, "r") as f:
                    data = json.load(f)

                # Apply the update function
                result = update_fn(data)

                # If the update function returns a dict, replace data with it
                if isinstance(result, dict):
                    data = result

                data["updated_at"] = datetime.now().isoformat()

                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2)

                temp_file.replace(job_file)
                return True
            except Exception as e:
                logger.error(f"Error updating job {job_id}: {str(e)}")
                if temp_file.exists():
                    temp_file.unlink()
                return False

    def get_job(self, job_id, details=False):
        logger.debug(f"Getting job {job_id}")
        job_file = self.jobs_dir / f"{job_id}.json"
        job_lock = self._get_job_lock(job_id)

        with job_lock:
            if not job_file.exists():
                return None

            try:
                logger.debug(f"Reading job file {job_file}")
                with open(job_file, "r") as f:
                    data = json.load(f)
                logger.debug(f"Job data: {data}")

                if not details:
                    return {
                        "job_id": data["job_id"] if "job_id" in data else job_id,
                        "status": data["status"] if "status" in data else "unknown",
                        "progress": data["summary"]["progress"]
                        if "summary" in data
                        else 0.0,
                        "created_at": data["created_at"]
                        if "created_at" in data
                        else "unknown",
                        "updated_at": data["updated_at"]
                        if "updated_at" in data
                        else "unknown",
                        "summary": data["summary"] if "summary" in data else {},
                    }

                return data
            except Exception as e:
                logger.error(f"Error reading job {job_id}: {str(e)}")
                return None

    def count_jobs(self, status="all"):
        job_files = list(self.jobs_dir.glob("*.json"))
        count = 0
        for job_file in job_files:
            try:
                with open(job_file, "r") as f:
                    data = json.load(f)
                # Filter by status
                if status == "all" or status == data["status"]:
                    count += 1
            except Exception:
                logger.error(f"Error reading job file {job_file}: {str(e)}")
                continue
        return count

    def list_jobs(
        self, page_number=0, status="all", sort_by="created_at", sort_order="desc"
    ):
        """List jobs with pagination and sorting options"""
        with self.global_lock:
            job_files = list(self.jobs_dir.glob("*.json"))
            if len(job_files) == 0:
                return []

            # Basic metadata for sorting
            jobs_meta = []
            for job_file in job_files:
                job_file_id = job_file.stem
                try:
                    with open(job_file, "r") as f:
                        data = json.load(f)
                    # Filter by status
                    if status == "all" or status == data["status"]:
                        jobs_meta.append(
                            {
                                "job_id": data["job_id"]
                                if "job_id" in data
                                else job_file_id,
                                "created_at": data["created_at"],
                                "updated_at": data["updated_at"],
                                "status": data["status"],
                                "bucket": data["parameters"].get("bucket"),
                                "path": data["parameters"].get("path"),
                            }
                        )
                except Exception as e:
                    # Skip corrupt job files
                    logger.error(f"Error reading job file {job_file}: {str(e)}")
                    continue

            # Sort jobs
            reverse = sort_order.lower() == "desc"
            sorted_jobs = sorted(
                jobs_meta, key=lambda x: x.get(sort_by, ""), reverse=reverse
            )

            # Apply pagination
            offset = page_number * 10
            limit = 10
            if offset >= len(sorted_jobs):
                return []
            paginated = sorted_jobs[offset : offset + limit]

            return [job for job in paginated]

    def get_file_metadata(self, bucket, key):
        """Get file metadata with caching"""
        cache_key = f"{bucket}:{key}"

        with self.global_lock:
            now = time.time()
            if cache_key in self.metadata_cache:
                if now - self.cache_expiry.get(cache_key, 0) < self.CACHE_TTL:
                    return self.metadata_cache[cache_key]

        try:
            response = self.s3.head_object(Bucket=bucket, Key=key)
            metadata = {
                "size_bytes": response["ContentLength"],
                "last_modified": response["LastModified"].isoformat(),
                "etag": response["ETag"].strip('"'),
            }

            # Update cache
            self.metadata_cache[cache_key] = metadata
            self.cache_expiry[cache_key] = now

            return metadata
        except Exception as e:
            logger.error(f"Error getting metadata for {bucket}/{key}: {str(e)}")
            raise

    def cancel_job(self, job_id):
        job_file = self.jobs_dir / f"{job_id}.json"

        job_lock = self._get_job_lock(job_id)
        with job_lock:
            if not job_file.exists():
                return False

            return self.update_job(
                job_id,
                lambda data: data.update(
                    {
                        **data,
                        "status": "cancelled",
                        "cancelled_at": datetime.now().isoformat(),
                    }
                ),
            )

    def clean_old_jobs(self, days=30):
        """Remove old job files to save disk space"""
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        with self.global_lock:
            job_files = list(self.jobs_dir.glob("*.json"))

        for job_file in job_files:
            job_lock = self._get_job_lock(job_file.stem)
            with job_lock:
                try:
                    # Check file modification time
                    if job_file.stat().st_mtime < cutoff:
                        # Check if job is complete or failed before deleting
                        with open(job_file, "r") as f:
                            data = json.load(f)

                        if data.get("status") in ["completed", "failed", "cancelled"]:
                            job_file.unlink()
                            logger.debug(f"Removed old job file: {job_file.name}")
                except Exception as e:
                    logger.error(f"Error cleaning old job {job_file.name}: {str(e)}")

    def resume_interrupted_jobs(self):
        """Find and resume jobs that were interrupted, with thread safety"""
        resumed = []

        # Get all job IDs under global lock
        with self.global_lock:
            job_ids = self.list_jobs()

        for job_id in job_ids:
            job_data = self.get_job(job_id, details=True)
            if not job_data:
                continue

            # Check for processing jobs that haven't been updated in a while
            if job_data.get("status") == "processing":
                updated_at = datetime.fromisoformat(job_data.get("updated_at"))
                now = datetime.now()

                # If job hasn't been updated in 30 minutes, mark for resume
                if (now - updated_at).total_seconds() > 1800:  # 30 minutes
                    job_lock = self._get_job_lock(job_id)

                    with job_lock:
                        if self.update_job(
                            job_id,
                            lambda data: data.update(
                                {
                                    "status": "pending",
                                    "message": "Job resumed after interruption",
                                }
                            )
                            or data,
                        ):
                            resumed.append(job_id)

        return resumed


metadata_cache = {}
active_processes = defaultdict(list)
job_tracker = JobTracker()
