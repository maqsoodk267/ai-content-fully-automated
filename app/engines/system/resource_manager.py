"""
ResourceManager — System resource monitoring and job scheduling.

Manages CPU, memory, and GPU resources to ensure system stability
during heavy AI processing workloads.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

from app.engines.base import BaseEngine


class ResourceManager(BaseEngine):
    name = "resource_manager"
    description = "System resource monitoring and job scheduling"

    def __init__(self) -> None:
        super().__init__()
        # Resource limits
        self._cpu_limit = 80.0  # Max CPU usage %
        self._memory_limit = 85.0  # Max memory usage %
        self._gpu_limit = 90.0  # Max GPU usage % (if available)

        # Job slots and queues
        self._job_slots = {
            "heavy": threading.Semaphore(2),  # Ollama, large models
            "medium": threading.Semaphore(4), # Image generation, TTS
            "light": threading.Semaphore(8),  # Text processing, API calls
        }

        # Active jobs tracking
        self._active_jobs: Dict[str, Dict[str, Any]] = {}
        self._job_history = deque(maxlen=1000)  # Recent job history

        # Resource monitoring
        self._monitoring_active = False
        self._resource_history = deque(maxlen=100)  # Recent resource readings

        # Job type definitions
        self._job_types = {
            "text_generation": "medium",
            "image_generation": "heavy",
            "video_processing": "heavy",
            "speech_synthesis": "medium",
            "translation": "light",
            "moderation": "light",
            "analysis": "light",
        }

    def can_run_heavy_job(self) -> Dict[str, Any]:
        """
        Check if system can handle a heavy job right now.

        Returns:
            Dict with availability status and resource info
        """
        resources = self.get_status()

        can_run = (
            resources["cpu_percent"] < self._cpu_limit and
            resources["memory_percent"] < self._memory_limit and
            (not resources.get("gpu_available") or
             resources.get("gpu_percent", 0) < self._gpu_limit)
        )

        # Check if heavy job slots are available
        slots_available = self._job_slots["heavy"]._value > 0

        return {
            "can_run": can_run and slots_available,
            "resources_ok": can_run,
            "slots_available": slots_available,
            "current_load": {
                "cpu": resources["cpu_percent"],
                "memory": resources["memory_percent"],
                "gpu": resources.get("gpu_percent"),
            },
            "limits": {
                "cpu": self._cpu_limit,
                "memory": self._memory_limit,
                "gpu": self._gpu_limit,
            },
            "active_jobs": len(self._active_jobs),
            "queue_sizes": {k: v._value for k, v in self._job_slots.items()},
        }

    def acquire_slot(self, job_type: str, job_id: str,
                    metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Acquire a job slot for processing.

        Args:
            job_type: Type of job (maps to resource category)
            job_id: Unique job identifier
            metadata: Optional job metadata

        Returns:
            Dict with acquisition status
        """
        # Map job type to resource category
        resource_category = self._job_types.get(job_type, "medium")

        semaphore = self._job_slots[resource_category]

        # Try to acquire slot
        acquired = semaphore.acquire(blocking=False)

        if acquired:
            # Register active job
            self._active_jobs[job_id] = {
                "job_type": job_type,
                "resource_category": resource_category,
                "started_at": time.time(),
                "metadata": metadata or {},
            }

            return {
                "acquired": True,
                "job_id": job_id,
                "resource_category": resource_category,
                "slot_remaining": semaphore._value,
            }
        else:
            return {
                "acquired": False,
                "job_id": job_id,
                "resource_category": resource_category,
                "reason": "no_slots_available",
                "queue_size": semaphore._value,
            }

    def release_slot(self, job_id: str) -> Dict[str, Any]:
        """
        Release a job slot after completion.

        Args:
            job_id: Job identifier to release

        Returns:
            Dict with release status
        """
        if job_id in self._active_jobs:
            job_info = self._active_jobs[job_id]
            resource_category = job_info["resource_category"]

            # Calculate job duration
            duration = time.time() - job_info["started_at"]

            # Release semaphore
            self._job_slots[resource_category].release()

            # Record in history
            self._job_history.append({
                "job_id": job_id,
                "job_type": job_info["job_type"],
                "resource_category": resource_category,
                "duration": duration,
                "completed_at": time.time(),
                "metadata": job_info["metadata"],
            })

            # Remove from active jobs
            del self._active_jobs[job_id]

            return {
                "released": True,
                "job_id": job_id,
                "duration": round(duration, 2),
                "resource_category": resource_category,
                "slots_now_available": self._job_slots[resource_category]._value,
            }
        else:
            return {
                "released": False,
                "job_id": job_id,
                "error": "job_not_found",
            }

    def get_status(self) -> Dict[str, Any]:
        """
        Get current system resource status.

        Returns:
            Dict with comprehensive resource information
        """
        try:
            if psutil is None:
                raise RuntimeError("psutil is not installed")

            # CPU and memory
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            status = {
                "cpu_percent": round(cpu_percent, 1),
                "cpu_count": psutil.cpu_count(),
                "memory_percent": round(memory_percent, 1),
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "disk_usage": self._get_disk_usage(),
                "active_jobs": len(self._active_jobs),
                "job_slots": {k: v._value for k, v in self._job_slots.items()},
                "job_queue_sizes": {k: self._get_queue_size(k) for k in self._job_slots.keys()},
            }

            # GPU information (if available)
            gpu_info = self._get_gpu_info()
            if gpu_info:
                status.update(gpu_info)

            # Add to history
            self._resource_history.append({
                "timestamp": time.time(),
                "cpu": cpu_percent,
                "memory": memory_percent,
                "active_jobs": len(self._active_jobs),
            })

            return status

        except Exception as e:
            self.logger.error(f"Resource status check failed: {e}")
            return {
                "error": str(e),
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "active_jobs": len(self._active_jobs),
            }

    def get_job_history(self, limit: int = 50) -> Dict[str, Any]:
        """
        Get recent job execution history.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            Dict with job history
        """
        recent_jobs = list(self._job_history)[-limit:]

        # Calculate statistics
        total_jobs = len(recent_jobs)
        if total_jobs > 0:
            avg_duration = sum(job["duration"] for job in recent_jobs) / total_jobs
            job_types = defaultdict(int)
            for job in recent_jobs:
                job_types[job["job_type"]] += 1
        else:
            avg_duration = 0
            job_types = {}

        return {
            "total_jobs": len(self._job_history),
            "recent_jobs": recent_jobs,
            "avg_duration": round(avg_duration, 2),
            "job_type_breakdown": dict(job_types),
        }

    def get_resource_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent resource usage history.

        Args:
            limit: Maximum number of readings to return

        Returns:
            List of resource readings
        """
        return list(self._resource_history)[-limit:]

    def set_resource_limits(self, cpu_limit: Optional[float] = None,
                           memory_limit: Optional[float] = None,
                           gpu_limit: Optional[float] = None) -> Dict[str, Any]:
        """
        Update resource usage limits.

        Args:
            cpu_limit: New CPU limit percentage
            memory_limit: New memory limit percentage
            gpu_limit: New GPU limit percentage

        Returns:
            Dict with updated limits
        """
        if cpu_limit is not None:
            self._cpu_limit = cpu_limit
        if memory_limit is not None:
            self._memory_limit = memory_limit
        if gpu_limit is not None:
            self._gpu_limit = gpu_limit

        return {
            "cpu_limit": self._cpu_limit,
            "memory_limit": self._memory_limit,
            "gpu_limit": self._gpu_limit,
            "updated_at": time.time(),
        }

    def scale_job_slots(self, category: str, new_limit: int) -> Dict[str, Any]:
        """
        Dynamically adjust job slot limits.

        Args:
            category: Resource category (heavy, medium, light)
            new_limit: New slot limit

        Returns:
            Dict with scaling result
        """
        if category not in self._job_slots:
            return {"error": f"Unknown category: {category}"}

        old_limit = self._job_slots[category]._value
        # Note: In production, you'd need to handle existing acquisitions
        # This is a simplified version
        self._job_slots[category] = threading.Semaphore(new_limit)

        return {
            "category": category,
            "old_limit": old_limit,
            "new_limit": new_limit,
            "scaled_at": time.time(),
        }

    def _get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage information."""
        if psutil is None:
            return {"percent": None, "used_gb": None, "total_gb": None, "error": "psutil_not_installed"}

        try:
            disk = psutil.disk_usage('/')
            return {
                "percent": round(disk.percent, 1),
                "used_gb": round(disk.used / (1024**3), 2),
                "total_gb": round(disk.total / (1024**3), 2),
            }
        except Exception:
            return {"error": "disk_check_failed"}

    def _get_gpu_info(self) -> Optional[Dict[str, Any]]:
        """Get GPU information if available."""
        try:
            # Check for NVIDIA GPU
            if os.path.exists("/usr/bin/nvidia-smi"):
                # This would require pynvml in production
                # For now, return placeholder
                return {
                    "gpu_available": True,
                    "gpu_percent": 45.0,  # Placeholder
                    "gpu_memory_used": 4.2,  # GB
                    "gpu_memory_total": 8.0,  # GB
                }
        except Exception:
            pass

        return {"gpu_available": False}

    def _get_queue_size(self, category: str) -> int:
        """Get number of waiting jobs for a category."""
        # This is a simplified version. In production, you'd track actual queues.
        semaphore = self._job_slots[category]
        return max(0, semaphore._value - len([j for j in self._active_jobs.values()
                                             if j["resource_category"] == category]))

    def cleanup_stale_jobs(self, timeout_seconds: int = 3600) -> Dict[str, Any]:
        """
        Clean up jobs that have been running too long.

        Args:
            timeout_seconds: Maximum allowed runtime

        Returns:
            Dict with cleanup results
        """
        current_time = time.time()
        stale_jobs = []

        for job_id, job_info in list(self._active_jobs.items()):
            if current_time - job_info["started_at"] > timeout_seconds:
                # Force release
                self.release_slot(job_id)
                stale_jobs.append(job_id)

        return {
            "stale_jobs_cleaned": len(stale_jobs),
            "job_ids": stale_jobs,
            "timeout_seconds": timeout_seconds,
        }