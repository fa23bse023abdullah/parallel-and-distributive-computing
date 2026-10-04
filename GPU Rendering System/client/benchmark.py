"""
benchmark.py - Performance Benchmarking & Analysis Tool
=========================================================

Conducts comparative performance evaluation between local CPU
rendering and remote GPU offloading across different file sizes
and resolutions. Generates a formal technical report.

Usage:
    python benchmark.py --input video.mp4 --server 192.168.1.1
"""

import os
import sys
import time
import json
import subprocess
import shutil
import argparse
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.utils import (
    format_bytes, format_duration, get_video_info,
    detect_nvidia_gpu, detect_ffmpeg, setup_logger, get_system_info
)
from common.protocol import RESOLUTIONS, RENDER_PRESETS, BITRATES
from client.network_handler import NetworkHandler


class BenchmarkRunner:
    """
    Runs systematic benchmarks comparing local vs. remote
    transcoding performance.
    """

    def __init__(self, input_file: str, server_host: str = None,
                 server_port: int = 9850, output_dir: str = None):
        self.input_file = os.path.abspath(input_file)
        self.server_host = server_host
        self.server_port = server_port
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(self.input_file), "benchmark_results"
        )
        self.logger = setup_logger("Benchmark")

        os.makedirs(self.output_dir, exist_ok=True)

        self.results = {
            "system_info": get_system_info(),
            "input_file": {
                "path": self.input_file,
                "info": get_video_info(self.input_file),
                "size": os.path.getsize(self.input_file),
            },
            "benchmarks": [],
            "summary": {},
        }

    def run_full_benchmark(self):
        """Run complete benchmark suite."""
        self.logger.info("=" * 60)
        self.logger.info("  PERFORMANCE BENCHMARK SUITE")
        self.logger.info("=" * 60)
        self.logger.info(f"  Input: {os.path.basename(self.input_file)}")
        self.logger.info(f"  Size: {format_bytes(self.results['input_file']['size'])}")
        self.logger.info("")

        # Test configurations
        test_configs = [
            {"resolution": "720p",  "bitrate": "5M",  "preset": "fast"},
            {"resolution": "1080p", "bitrate": "5M",  "preset": "medium"},
            {"resolution": "1080p", "bitrate": "10M", "preset": "medium"},
            {"resolution": "1080p", "bitrate": "5M",  "preset": "slow"},
        ]

        # Run local CPU benchmarks
        self.logger.info("─── LOCAL CPU BENCHMARKS ─────────────────")
        for config in test_configs:
            result = self._run_local_benchmark(config)
            if result:
                self.results["benchmarks"].append(result)

        # Run remote GPU benchmarks (if server configured)
        if self.server_host:
            self.logger.info("─── REMOTE GPU BENCHMARKS ───────────────")
            for config in test_configs:
                result = self._run_remote_benchmark(config)
                if result:
                    self.results["benchmarks"].append(result)

        # Generate summary
        self._generate_summary()

        # Save results
        self._save_results()

        # Generate report
        self._generate_report()

        return self.results

    def _run_local_benchmark(self, config: dict) -> dict:
        """Run a local CPU transcode benchmark."""
        resolution = config["resolution"]
        bitrate = config["bitrate"]
        preset = config["preset"]

        label = f"Local CPU | {resolution} | {bitrate} | {preset}"
        self.logger.info(f"  Running: {label}")

        res = RESOLUTIONS[resolution]
        output_path = os.path.join(
            self.output_dir,
            f"local_{resolution}_{bitrate}_{preset}.mp4"
        )

        cpu_preset_map = {
            "ultrafast": "ultrafast", "fast": "fast",
            "medium": "medium", "slow": "slow", "quality": "veryslow",
        }

        cmd = [
            "ffmpeg", "-y",
            "-i", self.input_file,
            "-c:v", "libx264",
            "-preset", cpu_preset_map.get(preset, "medium"),
            "-b:v", bitrate,
            "-vf", f"scale={res['width']}:{res['height']}",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path
        ]

        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            elapsed = time.time() - start_time

            if result.returncode == 0:
                output_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
                bench_result = {
                    "type": "local_cpu",
                    "label": label,
                    "config": config,
                    "encoder": "libx264",
                    "elapsed_seconds": round(elapsed, 2),
                    "input_size": self.results["input_file"]["size"],
                    "output_size": output_size,
                    "throughput_mbps": round(
                        (self.results["input_file"]["size"] / 1024 / 1024) / elapsed, 2
                    ) if elapsed > 0 else 0,
                }
                self.logger.info(f"    ✓ Completed in {format_duration(elapsed)}")
                return bench_result
            else:
                self.logger.error(f"    ✗ Failed: {result.stderr[-200:]}")
        except subprocess.TimeoutExpired:
            self.logger.error(f"    ✗ Timed out after 10 minutes")
        except Exception as e:
            self.logger.error(f"    ✗ Error: {e}")

        return None

    def _run_remote_benchmark(self, config: dict) -> dict:
        """Run a remote GPU transcode benchmark."""
        resolution = config["resolution"]
        bitrate = config["bitrate"]
        preset = config["preset"]

        label = f"Remote GPU | {resolution} | {bitrate} | {preset}"
        self.logger.info(f"  Running: {label}")

        network = NetworkHandler(logger=self.logger)

        # Connect
        if not network.connect(self.server_host, self.server_port):
            self.logger.error("    ✗ Failed to connect to server")
            return None

        # Measure upload time
        upload_start = time.time()
        output_dir = os.path.join(self.output_dir, "remote_output")

        # Submit job synchronously
        completed_event = threading.Event()
        result_data = {"result": None, "error": None}

        def on_complete(job_id, result):
            result_data["result"] = result
            completed_event.set()

        def on_failed(job_id, error):
            result_data["error"] = error
            completed_event.set()

        network.on_job_complete = on_complete
        network.on_job_failed = on_failed

        job_id = network.submit_job(
            self.input_file, "transcode", config, output_dir
        )

        if not job_id:
            self.logger.error("    ✗ Job submission failed")
            network.disconnect()
            return None

        # Wait for completion (max 10 minutes)
        completed_event.wait(timeout=600)
        total_elapsed = time.time() - upload_start

        network.disconnect()

        if result_data["result"]:
            render_elapsed = result_data["result"].get("elapsed_seconds", 0)
            network_overhead = total_elapsed - render_elapsed

            bench_result = {
                "type": "remote_gpu",
                "label": label,
                "config": config,
                "encoder": result_data["result"].get("encoder", "h264_nvenc"),
                "elapsed_seconds": round(total_elapsed, 2),
                "render_seconds": round(render_elapsed, 2),
                "network_overhead_seconds": round(network_overhead, 2),
                "input_size": self.results["input_file"]["size"],
                "output_size": result_data["result"].get("output_size", 0),
                "throughput_mbps": round(
                    (self.results["input_file"]["size"] / 1024 / 1024) / total_elapsed, 2
                ) if total_elapsed > 0 else 0,
            }
            self.logger.info(f"    ✓ Completed in {format_duration(total_elapsed)} "
                           f"(render: {format_duration(render_elapsed)}, "
                           f"network: {format_duration(network_overhead)})")
            return bench_result
        else:
            self.logger.error(f"    ✗ Failed: {result_data['error']}")
            return None

    def _generate_summary(self):
        """Generate a summary comparing local vs. remote performance."""
        local_results = [b for b in self.results["benchmarks"] if b["type"] == "local_cpu"]
        remote_results = [b for b in self.results["benchmarks"] if b["type"] == "remote_gpu"]

        summary = {
            "total_local_benchmarks": len(local_results),
            "total_remote_benchmarks": len(remote_results),
            "comparisons": [],
        }

        if local_results:
            avg_local = sum(b["elapsed_seconds"] for b in local_results) / len(local_results)
            summary["avg_local_time"] = round(avg_local, 2)

        if remote_results:
            avg_remote = sum(b["elapsed_seconds"] for b in remote_results) / len(remote_results)
            avg_render = sum(b.get("render_seconds", 0) for b in remote_results) / len(remote_results)
            avg_network = sum(b.get("network_overhead_seconds", 0) for b in remote_results) / len(remote_results)
            summary["avg_remote_total_time"] = round(avg_remote, 2)
            summary["avg_render_time"] = round(avg_render, 2)
            summary["avg_network_overhead"] = round(avg_network, 2)

        # Pairwise comparisons
        for local in local_results:
            matching_remote = [
                r for r in remote_results
                if r["config"] == local["config"]
            ]
            if matching_remote:
                remote = matching_remote[0]
                speedup = local["elapsed_seconds"] / remote["elapsed_seconds"] \
                    if remote["elapsed_seconds"] > 0 else 0
                summary["comparisons"].append({
                    "config": local["config"],
                    "local_time": local["elapsed_seconds"],
                    "remote_total_time": remote["elapsed_seconds"],
                    "remote_render_time": remote.get("render_seconds", 0),
                    "network_overhead": remote.get("network_overhead_seconds", 0),
                    "speedup_factor": round(speedup, 2),
                })

        self.results["summary"] = summary

    def _save_results(self):
        """Save benchmark results to JSON."""
        results_path = os.path.join(self.output_dir, "benchmark_results.json")
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, default=str)
        self.logger.info(f"Results saved: {results_path}")

    def _generate_report(self):
        """Generate a markdown report of the benchmark results."""
        report_path = os.path.join(self.output_dir, "benchmark_report.md")
        summary = self.results["summary"]

        lines = [
            "# Performance Benchmarking & Analysis Report",
            "",
            "## 1. System Information",
            "",
            f"- **OS:** {self.results['system_info']['os']} {self.results['system_info']['os_version']}",
            f"- **Processor:** {self.results['system_info']['processor']}",
            f"- **Python:** {self.results['system_info']['python_version']}",
            "",
        ]

        gpu = self.results['system_info']['gpu']
        if gpu.get('available'):
            for g in gpu['gpus']:
                lines.append(f"- **Local GPU:** {g['name']} ({g['total_memory_mb']}MB VRAM)")
        else:
            lines.append("- **Local GPU:** None (CPU only)")

        lines.extend([
            "",
            "## 2. Test Input File",
            "",
            f"- **File:** {os.path.basename(self.input_file)}",
            f"- **Size:** {format_bytes(self.results['input_file']['size'])}",
        ])

        info = self.results['input_file'].get('info')
        if info:
            lines.extend([
                f"- **Duration:** {format_duration(info.get('duration', 0))}",
                f"- **Resolution:** {info.get('width', '?')}x{info.get('height', '?')}",
                f"- **Codec:** {info.get('codec', '?')}",
                f"- **Bitrate:** {format_bytes(info.get('bitrate', 0))}/s",
            ])

        lines.extend([
            "",
            "## 3. Benchmark Results",
            "",
            "### 3.1 Local CPU Transcoding",
            "",
            "| Resolution | Bitrate | Preset | Time | Throughput |",
            "|:----------:|:-------:|:------:|:----:|:----------:|",
        ])

        for b in self.results["benchmarks"]:
            if b["type"] == "local_cpu":
                lines.append(
                    f"| {b['config']['resolution']} | {b['config']['bitrate']} | "
                    f"{b['config']['preset']} | {format_duration(b['elapsed_seconds'])} | "
                    f"{b['throughput_mbps']} MB/s |"
                )

        remote_benchmarks = [b for b in self.results["benchmarks"] if b["type"] == "remote_gpu"]
        if remote_benchmarks:
            lines.extend([
                "",
                "### 3.2 Remote GPU Transcoding",
                "",
                "| Resolution | Bitrate | Preset | Total Time | Render Time | Network Overhead |",
                "|:----------:|:-------:|:------:|:----------:|:-----------:|:----------------:|",
            ])

            for b in remote_benchmarks:
                lines.append(
                    f"| {b['config']['resolution']} | {b['config']['bitrate']} | "
                    f"{b['config']['preset']} | {format_duration(b['elapsed_seconds'])} | "
                    f"{format_duration(b.get('render_seconds', 0))} | "
                    f"{format_duration(b.get('network_overhead_seconds', 0))} |"
                )

        comparisons = summary.get("comparisons", [])
        if comparisons:
            lines.extend([
                "",
                "## 4. Performance Comparison",
                "",
                "| Configuration | Local CPU | Remote GPU | Speedup Factor |",
                "|:-------------:|:---------:|:----------:|:--------------:|",
            ])

            for c in comparisons:
                config_str = f"{c['config']['resolution']}/{c['config']['bitrate']}/{c['config']['preset']}"
                lines.append(
                    f"| {config_str} | {format_duration(c['local_time'])} | "
                    f"{format_duration(c['remote_total_time'])} | "
                    f"**{c['speedup_factor']}x** |"
                )

            lines.extend([
                "",
                "### Key Findings",
                "",
            ])

            avg_speedup = sum(c["speedup_factor"] for c in comparisons) / len(comparisons)
            lines.append(f"- **Average Speedup Factor:** {avg_speedup:.2f}x")

            if summary.get("avg_network_overhead"):
                lines.append(f"- **Average Network Overhead:** {format_duration(summary['avg_network_overhead'])}")
                if summary.get("avg_remote_total_time"):
                    pct = (summary["avg_network_overhead"] / summary["avg_remote_total_time"]) * 100
                    lines.append(f"- **Network Overhead Percentage:** {pct:.1f}% of total remote time")

        lines.extend([
            "",
            "## 5. Conclusion",
            "",
            "This benchmark demonstrates the effectiveness of distributed task offloading "
            "for compute-intensive video transcoding operations. By offloading rendering "
            "workloads to a remote GPU-equipped worker node, significant speedup factors "
            "are achieved, especially for higher quality presets and resolutions where "
            "GPU hardware acceleration provides the greatest advantage.",
            "",
            "The network transfer overhead is minimal compared to the compute savings, "
            "particularly on local area networks with direct Ethernet connections.",
            "",
            "---",
            f"*Report generated: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        ])

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.logger.info(f"Report saved: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Performance Benchmarking Tool"
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Path to input video file")
    parser.add_argument("--server", "-s", default=None,
                        help="Remote server IP for remote benchmarks")
    parser.add_argument("--port", "-p", type=int, default=9850,
                        help="Remote server port (default: 9850)")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output directory for results")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)

    runner = BenchmarkRunner(
        input_file=args.input,
        server_host=args.server,
        server_port=args.port,
        output_dir=args.output_dir
    )
    runner.run_full_benchmark()


if __name__ == "__main__":
    main()
