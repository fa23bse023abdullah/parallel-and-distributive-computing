"""
task_queue.py - Thread-Safe Task Queue Manager
=================================================

Manages incoming render/compute jobs with a priority queue, thread-safe
operations, and job lifecycle tracking (PENDING → RUNNING → COMPLETE/FAILED).
"""

import threading
import queue
import uuid
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Callable


class JobStatus(Enum):
    """Lifecycle states for a processing job."""
    PENDING     = "PENDING"
    RUNNING     = "RUNNING"
    COMPLETE    = "COMPLETE"
    FAILED      = "FAILED"
    CANCELLED   = "CANCELLED"


@dataclass
class Job:
    """Represents a single processing job in the queue."""
    job_id: str
    job_type: str               # "transcode", "cuda_compute", etc.
    input_file: str             # Path to input file on server
    output_file: str = ""       # Path to output file on server
    config: dict = field(default_factory=dict)   # Render configuration
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0       # 0.0 to 100.0
    progress_message: str = ""  # Human-readable progress text
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    error_message: str = ""
    result_info: dict = field(default_factory=dict)  # Output metadata

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "input_file": self.input_file,
            "output_file": self.output_file,
            "config": self.config,
            "status": self.status.value,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "result_info": self.result_info,
        }


class TaskQueueManager:
    """
    Thread-safe task queue that manages job lifecycle and dispatches
    jobs to the GPU execution engine.
    """

    def __init__(self, max_concurrent: int = 1, logger=None):
        self._queue = queue.Queue()
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._max_concurrent = max_concurrent
        self._active_count = 0
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._executor_callback: Optional[Callable] = None
        self._progress_callback: Optional[Callable] = None
        self._logger = logger

    def set_executor(self, executor_callback: Callable):
        """Set the function that will execute jobs (e.g., GPU engine)."""
        self._executor_callback = executor_callback

    def set_progress_callback(self, callback: Callable):
        """Set the callback for progress updates to stream to clients."""
        self._progress_callback = callback

    def start(self):
        """Start the queue processing worker thread."""
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._process_loop,
            name="TaskQueueWorker",
            daemon=True
        )
        self._worker_thread.start()
        if self._logger:
            self._logger.info("Task Queue Manager started")

    def stop(self):
        """Stop the queue processing worker thread."""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._queue.put(None)  # Sentinel to unblock
            self._worker_thread.join(timeout=5)
        if self._logger:
            self._logger.info("Task Queue Manager stopped")

    def submit_job(self, job_type: str, input_file: str, config: dict) -> Job:
        """Submit a new job to the queue. Returns the Job object."""
        job = self.create_job(job_type, input_file, config)
        self.enqueue_job(job.job_id)
        return job

    def create_job(self, job_type: str, input_file: str, config: dict) -> Job:
        """Create a new pending job without enqueuing it yet."""
        job_id = str(uuid.uuid4())[:8]
        job = Job(
            job_id=job_id,
            job_type=job_type,
            input_file=input_file,
            config=config,
        )

        with self._lock:
            self._jobs[job_id] = job

        if self._logger:
            self._logger.info(f"Job {job_id} created: type={job_type}")

        return job

    def enqueue_job(self, job_id: str):
        """Enqueue a created job for execution after input file transfer completes."""
        with self._lock:
            job = self._jobs.get(job_id)

        if job:
            self._queue.put(job_id)
            if self._logger:
                self._logger.info(f"Job {job_id} enqueued for execution")

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by its ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def update_job_progress(self, job_id: str, progress: float, message: str = ""):
        """Update a job's progress and notify the progress callback."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.progress = progress
                job.progress_message = message

        if self._progress_callback:
            self._progress_callback(job_id, progress, message)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                if self._logger:
                    self._logger.info(f"Job {job_id} cancelled")
                return True
        return False

    def get_queue_status(self) -> dict:
        """Get a summary of the queue state."""
        with self._lock:
            statuses = {}
            for job in self._jobs.values():
                status_name = job.status.value
                statuses[status_name] = statuses.get(status_name, 0) + 1

            return {
                "total_jobs": len(self._jobs),
                "queue_size": self._queue.qsize(),
                "active_count": self._active_count,
                "status_breakdown": statuses,
            }

    def _process_loop(self):
        """Main worker loop: dequeue and execute jobs."""
        while self._running:
            try:
                job_id = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            if job_id is None:  # Sentinel
                break

            with self._lock:
                job = self._jobs.get(job_id)
                if not job or job.status == JobStatus.CANCELLED:
                    continue
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
                self._active_count += 1

            if self._logger:
                self._logger.info(f"Job {job_id} started processing")

            try:
                if self._executor_callback:
                    result = self._executor_callback(job)
                    with self._lock:
                        job.status = JobStatus.COMPLETE
                        job.progress = 100.0
                        job.completed_at = time.time()
                        job.result_info = result or {}
                        self._active_count -= 1

                    if self._progress_callback:
                        self._progress_callback(job_id, 100.0, "Job completed successfully")

                    if self._logger:
                        elapsed = job.completed_at - job.started_at
                        self._logger.info(f"Job {job_id} completed in {elapsed:.2f}s")
                else:
                    raise RuntimeError("No executor callback configured")

            except Exception as e:
                with self._lock:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)
                    job.completed_at = time.time()
                    self._active_count -= 1

                if self._progress_callback:
                    self._progress_callback(job_id, -1, f"Error: {str(e)}")

                if self._logger:
                    self._logger.error(f"Job {job_id} failed: {e}", exc_info=True)
