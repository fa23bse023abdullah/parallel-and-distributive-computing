"""
task_executor.py - GPU Execution Engine
=========================================

Handles the actual compute-heavy task execution, leveraging:
- FFmpeg with NVENC (h264_nvenc) for hardware-accelerated video transcoding
- PyTorch CUDA for tensor/compute operations
- Fallback to CPU-based processing when GPU is unavailable
"""

import subprocess
import os
import re
import time
import threading
from typing import Callable, Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.utils import (
    detect_nvidia_gpu, detect_ffmpeg, format_bytes,
    format_duration, get_video_info
)
from common.protocol import RENDER_PRESETS, RESOLUTIONS


class GPUExecutionEngine:
    """
    Executes render and compute tasks using GPU hardware acceleration.
    Falls back to CPU encoding when NVENC is not available.
    """

    def __init__(self, work_dir: str, logger=None):
        self.work_dir = work_dir
        self.output_dir = os.path.join(work_dir, "output")
        self.logger = logger
        self._progress_callback: Optional[Callable] = None

        os.makedirs(self.output_dir, exist_ok=True)

        # Detect hardware capabilities
        self.gpu_info = detect_nvidia_gpu()
        self.ffmpeg_info = detect_ffmpeg()

        self._log_capabilities()

    def _log_capabilities(self):
        """Log detected hardware capabilities."""
        if self.logger:
            if self.gpu_info["available"]:
                for gpu in self.gpu_info["gpus"]:
                    self.logger.info(
                        f"GPU Detected: {gpu['name']} | "
                        f"VRAM: {gpu['total_memory_mb']}MB | "
                        f"Driver: {gpu['driver_version']} | "
                        f"CUDA: {gpu['cuda_version']}"
                    )
            else:
                self.logger.warning("No NVIDIA GPU detected — will use CPU fallback")

            if self.ffmpeg_info["available"]:
                self.logger.info(f"FFmpeg found: {self.ffmpeg_info['path']}")
                self.logger.info(f"NVENC support: {self.ffmpeg_info['nvenc_supported']}")
            else:
                self.logger.error("FFmpeg NOT found — video transcoding unavailable!")

    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates: callback(job_id, progress%, message)."""
        self._progress_callback = callback

    def get_capabilities(self) -> dict:
        """Return a summary of this engine's capabilities."""
        if not self.ffmpeg_info.get("available"):
            self.ffmpeg_info = detect_ffmpeg()

        return {
            "gpu_available": self.gpu_info["available"],
            "gpu_list": self.gpu_info.get("gpus", []),
            "ffmpeg_available": self.ffmpeg_info["available"],
            "nvenc_supported": self.ffmpeg_info.get("nvenc_supported", False),
            "supported_tasks": self._get_supported_tasks(),
        }

    def _get_supported_tasks(self) -> list:
        """List supported task types based on available hardware."""
        if not self.ffmpeg_info.get("available"):
            self.ffmpeg_info = detect_ffmpeg()

        tasks = []
        if self.ffmpeg_info.get("available"):
            tasks.append("transcode")
        try:
            import torch
            if torch.cuda.is_available():
                tasks.append("cuda_compute")
        except ImportError:
            pass
        return tasks

    def execute(self, job) -> dict:
        """
        Main execution entry point. Dispatches to the appropriate
        handler based on job type.
        """
        job_type = job.job_type

        if job_type == "transcode":
            return self._execute_transcode(job)
        elif job_type == "cuda_compute":
            return self._execute_cuda_compute(job)
        else:
            raise ValueError(f"Unsupported job type: {job_type}")

    # ─── FFmpeg NVENC Transcoding ─────────────────────────────────
    def _execute_transcode(self, job) -> dict:
        """Execute a video transcoding job using FFmpeg with NVENC or CPU fallback."""
        if not self.ffmpeg_info["available"]:
            raise RuntimeError("FFmpeg is not installed on this worker node")

        input_path = job.input_file
        config = job.config

        # Parse render configuration
        resolution_key = config.get("resolution", "1080p")
        bitrate = config.get("bitrate", "5M")
        preset_key = config.get("preset", "medium")
        output_format = config.get("output_format", "mp4")

        resolution = RESOLUTIONS.get(resolution_key, RESOLUTIONS["1080p"])
        preset_info = RENDER_PRESETS.get(preset_key, RENDER_PRESETS["medium"])

        # Build output filename
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_filename = f"{base_name}_{resolution_key}_{preset_key}.{output_format}"
        output_path = os.path.join(self.output_dir, output_filename)
        job.output_file = output_path

        # Get input video duration for progress calculation
        video_info = get_video_info(input_path)
        total_duration = video_info["duration"] if video_info else 0

        # Determine encoder
        use_nvenc = (
            self.gpu_info["available"] and
            self.ffmpeg_info["nvenc_supported"]
        )

        if use_nvenc:
            encoder = "h264_nvenc"
            preset_flag = preset_info["nvenc_preset"]
            encoder_opts = [
                "-c:v", encoder,
                "-preset", preset_flag,
                "-b:v", bitrate,
                "-maxrate", bitrate,
                "-bufsize", f"{int(bitrate.replace('M', '')) * 2}M" if 'M' in bitrate else bitrate,
                "-rc", "vbr",
            ]
            self._report_progress(job.job_id, 2, "Using NVIDIA NVENC hardware encoder")
        else:
            encoder = "libx264"
            cpu_preset_map = {
                "ultrafast": "ultrafast", "fast": "fast",
                "medium": "medium", "slow": "slow", "quality": "veryslow",
            }
            preset_flag = cpu_preset_map.get(preset_key, "medium")
            encoder_opts = [
                "-c:v", encoder,
                "-preset", preset_flag,
                "-b:v", bitrate,
            ]
            self._report_progress(job.job_id, 2, "Using CPU software encoder (libx264) — no NVENC available")

        # Build full FFmpeg command
        ffmpeg_bin = self.ffmpeg_info.get("path") or "ffmpeg"
        cmd = [
            ffmpeg_bin, "-y",
            "-i", input_path,
            *encoder_opts,
            "-vf", f"scale={resolution['width']}:{resolution['height']}",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            "-nostats",
            output_path
        ]

        if self.logger:
            self.logger.info(f"FFmpeg command: {' '.join(cmd)}")
            self.logger.info(f"Encoder: {encoder} | Preset: {preset_flag} | "
                           f"Resolution: {resolution_key} | Bitrate: {bitrate}")

        self._report_progress(job.job_id, 5, f"Starting transcoding: {encoder} @ {resolution_key}")

        if total_duration <= 0:
            total_duration = 30.0  # Safe default if metadata missing

        # Execute FFmpeg with real-time progress parsing
        start_time = time.time()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # Prevent Windows pipe buffer deadlock
            universal_newlines=True,
            bufsize=1,
        )

        # Parse FFmpeg progress output
        progress_pattern = re.compile(r"out_time_us=(\d+)")
        speed_pattern = re.compile(r"speed=\s*([0-9.]+)x")

        last_progress_update = 0
        last_update_time = time.time()

        for line in iter(process.stdout.readline, ""):
            line = line.strip()

            time_match = progress_pattern.search(line)
            if time_match and total_duration > 0:
                current_us = int(time_match.group(1))
                current_secs = current_us / 1_000_000
                progress = min((current_secs / total_duration) * 100, 99.5)
                now = time.time()

                # Send updates every 1% or every 0.8s
                if (progress - last_progress_update >= 1.0) or (now - last_update_time >= 0.8):
                    speed_match = speed_pattern.search(line)
                    speed_str = f" @ {speed_match.group(1)}x" if speed_match else ""
                    self._report_progress(
                        job.job_id, min(96.0, 5.0 + progress * 0.90),
                        f"Transcoding: {progress:.1f}%{speed_str} ({current_secs:.1f}s / {total_duration:.1f}s)"
                    )
                    last_progress_update = progress
                    last_update_time = now

        process.wait()

        elapsed = time.time() - start_time

        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg failed with exit code {process.returncode}")

        # Gather output info
        output_info = get_video_info(output_path)
        output_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        input_size = os.path.getsize(input_path) if os.path.exists(input_path) else 0

        self._report_progress(job.job_id, 97, "Transcoding complete, preparing output...")

        result = {
            "output_file": output_path,
            "output_filename": output_filename,
            "encoder": encoder,
            "preset": preset_flag,
            "resolution": resolution_key,
            "bitrate": bitrate,
            "elapsed_seconds": round(elapsed, 2),
            "elapsed_formatted": format_duration(elapsed),
            "input_size": input_size,
            "output_size": output_size,
            "input_size_formatted": format_bytes(input_size),
            "output_size_formatted": format_bytes(output_size),
            "compression_ratio": round(input_size / output_size, 2) if output_size > 0 else 0,
            "output_info": output_info,
        }

        if self.logger:
            self.logger.info(
                f"Transcoding complete: {format_duration(elapsed)} | "
                f"Input: {format_bytes(input_size)} -> Output: {format_bytes(output_size)} | "
                f"Encoder: {encoder}"
            )

        return result

    # ─── CUDA Tensor Compute ──────────────────────────────────────
    def _execute_cuda_compute(self, job) -> dict:
        """Execute a CUDA-based tensor computation job."""
        try:
            import torch
        except ImportError:
            raise RuntimeError("PyTorch is not installed on this worker node")

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available on this worker node")

        config = job.config
        operation = config.get("operation", "matrix_multiply")
        matrix_size = config.get("matrix_size", 2048)

        device = torch.device("cuda")

        self._report_progress(job.job_id, 5, f"Initializing CUDA compute: {operation}")

        if operation == "matrix_multiply":
            return self._cuda_matrix_multiply(job, device, matrix_size)
        elif operation == "convolution":
            return self._cuda_convolution(job, device, config)
        else:
            raise ValueError(f"Unknown CUDA operation: {operation}")

    def _cuda_matrix_multiply(self, job, device, size: int) -> dict:
        """Perform large matrix multiplication on GPU."""
        import torch

        self._report_progress(job.job_id, 10, f"Allocating {size}x{size} matrices on GPU...")

        # Allocate matrices
        A = torch.randn(size, size, device=device, dtype=torch.float32)
        B = torch.randn(size, size, device=device, dtype=torch.float32)

        self._report_progress(job.job_id, 30, "Performing GPU matrix multiplication...")

        # Warm-up
        torch.cuda.synchronize()
        start_time = time.time()

        # Execute
        C = torch.mm(A, B)
        torch.cuda.synchronize()

        elapsed = time.time() - start_time

        # Calculate GFLOPS
        flops = 2 * (size ** 3)
        gflops = flops / elapsed / 1e9

        self._report_progress(job.job_id, 90, f"Computation complete: {gflops:.1f} GFLOPS")

        # Cleanup
        result_norm = float(C.norm().cpu())
        del A, B, C
        torch.cuda.empty_cache()

        return {
            "operation": "matrix_multiply",
            "matrix_size": size,
            "elapsed_seconds": round(elapsed, 4),
            "gflops": round(gflops, 2),
            "result_norm": result_norm,
            "device": str(device),
            "gpu_name": torch.cuda.get_device_name(0),
        }

    def _cuda_convolution(self, job, device, config: dict) -> dict:
        """Perform a 2D convolution on GPU."""
        import torch
        import torch.nn.functional as F

        batch = config.get("batch_size", 16)
        channels = config.get("channels", 64)
        spatial = config.get("spatial_size", 256)
        kernel = config.get("kernel_size", 3)

        self._report_progress(job.job_id, 10, f"Allocating tensors: {batch}x{channels}x{spatial}x{spatial}")

        inp = torch.randn(batch, channels, spatial, spatial, device=device)
        weight = torch.randn(channels, channels, kernel, kernel, device=device)

        self._report_progress(job.job_id, 30, "Running GPU convolution...")

        torch.cuda.synchronize()
        start_time = time.time()

        out = F.conv2d(inp, weight, padding=kernel // 2)
        torch.cuda.synchronize()

        elapsed = time.time() - start_time

        result_shape = list(out.shape)
        del inp, weight, out
        torch.cuda.empty_cache()

        self._report_progress(job.job_id, 90, "Convolution complete")

        return {
            "operation": "convolution",
            "input_shape": [batch, channels, spatial, spatial],
            "kernel_size": kernel,
            "output_shape": result_shape,
            "elapsed_seconds": round(elapsed, 4),
            "device": str(device),
            "gpu_name": torch.cuda.get_device_name(0),
        }

    # ─── Helpers ──────────────────────────────────────────────────
    def _report_progress(self, job_id: str, progress: float, message: str):
        """Report progress via callback and logger."""
        if self._progress_callback:
            self._progress_callback(job_id, progress, message)
        if self.logger:
            self.logger.info(f"[Job {job_id}] {progress:.1f}% — {message}")
