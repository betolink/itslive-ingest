import os
import asyncio
import time
from fastapi import (
    FastAPI,
    HTTPException,
    BackgroundTasks,
    Query,
    Depends,
    Request,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from datetime import datetime
import logging

from fastapi.logger import logger as fastapi_logger

from tasks import process_files, initialize_database_task, dummy_task, check_database_connection
from tracker import active_processes, job_tracker as tracker

# Setup logging
# logging.basicConfig(
#     level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# )


app = FastAPI()

logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')

# Console Handler for stdout logging
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
fastapi_logger.handlers = logger.handlers
fastapi_logger.setLevel(logger.level)



# Authentication settings
API_TOKEN = os.getenv("API_TOKEN", "itslive")
API_KEY_NAME = "X-API-Token"
DATABASE_URL = os.getenv("DATABASE_URL")
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Process tracking
process_lock = asyncio.Lock()


# Dependency for token authentication
async def verify_token(api_key: str = Depends(api_key_header)):
    if not API_TOKEN:
        logger.warning("API token not configured, allowing unauthenticated access")
        return True

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if api_key != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True


# Rate limiting
class RateLimiter:
    def __init__(self, rate_limit=30, per_seconds=60):
        self.rate_limit = rate_limit
        self.per_seconds = per_seconds
        self.requests = {}

    async def check(self, client_id):
        now = time.time()
        client_requests = self.requests.get(client_id, [])

        # Remove old requests
        client_requests = [
            req for req in client_requests if now - req < self.per_seconds
        ]

        if len(client_requests) >= self.rate_limit:
            return False

        client_requests.append(now)
        self.requests[client_id] = client_requests
        return True


rate_limiter = RateLimiter()


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host

    # Skip rate limiting for specific paths or local IPs
    if (
        request.url.path == "/health"
        or client_ip.startswith("10.")
        or client_ip.startswith("172.")
    ):
        return await call_next(request)
    if not await rate_limiter.check(client_ip):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Rate limit exceeded",
                "status_code": 429,
                "timestamp": datetime.now().isoformat(),
            },
        )

    return await call_next(request)


# Performance monitoring middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(
        f"Request to {request.url.path} processed in {process_time:.4f} seconds"
    )
    return response


@app.get("/health")
async def health_check():
    logger.info("🚀 Application is healthy!")
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/database")
async def database_test():
    check = await run_in_threadpool(check_database_connection)
    return {"status": check,
            "dbconn": DATABASE_URL,
            "timestamp": datetime.now().isoformat()}

@app.post("/ingest", dependencies=[Depends(verify_token)])
async def create_ingest_job(
    bucket: str = Query(..., description="S3 bucket name"),
    path: str = Query(..., description="S3 path prefix"),
    recursive: bool = Query(False),
    year: int = Query(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    current_job = await run_in_threadpool(tracker.has_active_jobs)
    if current_job:
        job_id = current_job["job_id"]
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": f"Ingest job {job_id} is already in progress. Only one concurrent ingest is allowed.",
                "status_code": 429,
                "timestamp": datetime.now().isoformat(),
            },
        )

    job_id = await run_in_threadpool(tracker.create_job, bucket, path, recursive, year)
    background_tasks.add_task(process_files, job_id)

    return {
        "job_id": job_id,
        "status": "pending",
        "links": {
            "status": f"/jobs/{job_id}",
            "details": f"/jobs/{job_id}?details=true",
        },
    }


@app.post("/dummy", dependencies=[Depends(verify_token)])
async def ingest_dummy_task(
    background_tasks: BackgroundTasks = BackgroundTasks(),
    name: str = Query(False, description="Name for the test task"),
    tasks_to_run: int = Query(1, description="Number of tasks to run"),
    concurrent_tasks: int = Query(1, description="Number of concurrent tasks to run"),
):
    current_job = await run_in_threadpool(tracker.has_active_jobs)
    logger.info(f"Current job: {current_job}")
    if current_job:
        logger.warning(f"Dummy task already in progress: {current_job}")
        job_id = current_job["job_id"]
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": f"Ingest job {job_id} is already in progress. Only one concurrent ingest is allowed.",
                "status_code": 429,
                "timestamp": datetime.now().isoformat(),
            },
        )

    job_id = await run_in_threadpool(tracker.create_job, "dummy", name, False, None)
    background_tasks.add_task(dummy_task, job_id, name, tasks_to_run, concurrent_tasks)
    return {
        "job_id": job_id,
        "status": "pending",
        "links": {
            "status": f"/jobs/{job_id}",
            "details": f"/jobs/{job_id}?details=true",
        },
    }


@app.post("/initdb", dependencies=[Depends(verify_token)])
async def initialize_database(
    background_tasks: BackgroundTasks = BackgroundTasks(),
    migrate: bool = Query(False, description="Run database migrations if needed"),
):
    job_id = await run_in_threadpool(tracker.create_job, "initdb", "", False, None)
    await run_in_threadpool(
        tracker.update_job,  # Pass the function reference
        job_id,  # Pass the first argument
        lambda data: {  # Pass the second argument (the lambda)
            "parameters": {"task": "initdb", "migrate": migrate, **data["parameters"]},
            **data,
        },
    )

    background_tasks.add_task(initialize_database_task, job_id, migrate)

    return {
        "job_id": job_id,
        "status": "pending",
        "links": {"status": f"/jobs/{job_id}"},
    }


@app.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str, details: bool = Query(False, description="Show detailed file statuses")
):
    job_data = await run_in_threadpool(tracker.get_job, job_id, details)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_data


@app.get("/jobs/page/{page_number}/status/{status}")
async def list_jobs_page(page_number: int = 0, status: str = "all"):
    jobs_count = await run_in_threadpool(tracker.count_jobs, status)
    jobs_list = await run_in_threadpool(
        tracker.list_jobs, page_number=page_number, status=status
    )
    return {
        "total": jobs_count,
        "jobs": jobs_list,
    }


@app.get("/jobs")
async def list_jobs():
    jobs = await run_in_threadpool(tracker.list_jobs)
    return {"jobs": jobs}


@app.post("/jobs/{job_id}/cancel", dependencies=[Depends(verify_token)])
async def cancel_job(job_id: str):
    cancelled_job = await run_in_threadpool(tracker.cancel_job, job_id)
    if not cancelled_job:
        raise HTTPException(status_code=404, detail="Job not found")

    async with process_lock:
        processes = active_processes.get(job_id, [])
        for proc in processes:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (ProcessLookupError, asyncio.TimeoutError):
                pass
        if job_id in active_processes:
            del active_processes[job_id]

    return {"status": "cancelled", "message": "Terminated all subprocesses"}


# Run if called directly
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting ingest service app...")

    uvicorn.run(app, host="0.0.0.0", port=8000)
