"""
server_daemon.py - Remote Worker Node Server Daemon
======================================================

The main server process that runs on the remote worker node (GPU workstation).
It listens for incoming client connections, handles the handshake protocol,
receives files, dispatches GPU-accelerated tasks, streams progress updates,
and sends back rendered output.

Usage:
    python server_daemon.py [--host 0.0.0.0] [--port 9850] [--work-dir ./workspace]
"""

import socket
import threading
import os
import sys
import time
import json
import argparse
import signal
import base64

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.protocol import (
    MessageType, create_message, send_message, receive_message,
    receive_file_chunked, send_file_chunked,
    DEFAULT_SERVER_PORT, HEADER_SIZE, SOCKET_TIMEOUT,
    HANDSHAKE_TIMEOUT, compute_file_checksum, CHUNK_SIZE,
    serialize_message, deserialize_header, deserialize_message,
    RENDER_PRESETS, RESOLUTIONS, BITRATES
)
from common.utils import (
    setup_logger, get_system_info, format_bytes,
    format_duration, format_timestamp, detect_nvidia_gpu,
    get_gpu_live_stats
)
from server.task_queue import TaskQueueManager, JobStatus
from server.task_executor import GPUExecutionEngine


class WorkerDaemon:
    """
    Remote Worker Node Daemon.

    Manages:
    - TCP socket server for client connections
    - Handshake and capability negotiation
    - File reception and checksum validation
    - Job dispatching to GPU engine
    - Real-time progress streaming back to client
    - Output file delivery
    """

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_SERVER_PORT,
                 work_dir: str = "./workspace"):
        self.host = host
        self.port = port
        self.work_dir = os.path.abspath(work_dir)
        self.upload_dir = os.path.join(self.work_dir, "uploads")
        self.output_dir = os.path.join(self.work_dir, "output")
        self.log_dir = os.path.join(self.work_dir, "logs")

        # Create working directories
        for d in [self.upload_dir, self.output_dir, self.log_dir]:
            os.makedirs(d, exist_ok=True)

        # Setup logging
        log_file = os.path.join(self.log_dir, f"server_{format_timestamp().replace(':', '-')}.log")
        self.logger = setup_logger("WorkerDaemon", log_file)

        # Initialize GPU engine
        self.gpu_engine = GPUExecutionEngine(self.work_dir, self.logger)

        # Initialize task queue
        self.task_queue = TaskQueueManager(max_concurrent=1, logger=self.logger)
        self.task_queue.set_executor(self.gpu_engine.execute)
        self.gpu_engine.set_progress_callback(self.task_queue.update_job_progress)

        # Server socket
        self.server_socket: socket.socket = None
        self._running = False
        self._client_sockets: dict = {}  # job_id -> client socket
        self._client_lock = threading.Lock()
        self._send_lock = threading.Lock()

        # System info
        self.system_info = get_system_info()

    def start(self):
        """Start the server daemon."""
        self._running = True

        # Start task queue processor
        self.task_queue.set_progress_callback(self._on_job_progress)
        self.task_queue.start()

        # Create and bind server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1)  # Allow periodic shutdown checks

        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
        except OSError as e:
            self.logger.error(f"Failed to bind to {self.host}:{self.port} — {e}")
            sys.exit(1)

        self.logger.info("=" * 68)
        self.logger.info("  DISTRIBUTED TASK OFFLOADING — REMOTE WORKER NODE")
        self.logger.info("=" * 68)
        self.logger.info(f"  Server listening on {self.host}:{self.port}")
        self.logger.info(f"  Work directory: {self.work_dir}")
        self.logger.info(f"  OS: {self.system_info['os']} {self.system_info['os_version']}")
        self.logger.info(f"  Python: {self.system_info['python_version']}")

        if self.system_info["gpu"]["available"]:
            for gpu in self.system_info["gpu"]["gpus"]:
                self.logger.info(f"  GPU: {gpu['name']} ({gpu['total_memory_mb']}MB VRAM)")
        else:
            self.logger.info("  GPU: None detected (CPU fallback mode)")

        self.logger.info(f"  FFmpeg: {'Available' if self.system_info['ffmpeg']['available'] else 'NOT FOUND'}")
        self.logger.info(f"  NVENC: {'Supported' if self.system_info['ffmpeg'].get('nvenc_supported') else 'Not available'}")
        self.logger.info("=" * 68)
        self.logger.info("Waiting for client connections...")

        # Accept loop
        self._accept_loop()

    def stop(self):
        """Gracefully stop the daemon."""
        self.logger.info("Shutting down server daemon...")
        self._running = False
        self.task_queue.stop()

        with self._client_lock:
            for sock in self._client_sockets.values():
                try:
                    sock.close()
                except Exception:
                    pass

        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

        self.logger.info("Server daemon stopped.")

    def _accept_loop(self):
        """Main loop to accept incoming client connections."""
        while self._running:
            try:
                client_socket, addr = self.server_socket.accept()
                client_socket.settimeout(SOCKET_TIMEOUT)
                self.logger.info(f"New connection from {addr[0]}:{addr[1]}")

                # Handle each client in a new thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, addr),
                    name=f"Client-{addr[0]}:{addr[1]}",
                    daemon=True
                )
                client_thread.start()

            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    self.logger.error("Socket accept error", exc_info=True)
                break

    def _handle_client(self, client_socket: socket.socket, addr: tuple):
        """Handle a single client connection lifecycle."""
        client_id = f"{addr[0]}:{addr[1]}"
        current_job_id = None

        try:
            # ── Step 1: Handshake ─────────────────────────────────
            handshake_ok = self._perform_handshake(client_socket, client_id)
            if not handshake_ok:
                return

            # ── Step 2: Message Processing Loop ──────────────────
            while self._running:
                try:
                    msg = receive_message(client_socket)
                except (socket.timeout, TimeoutError):
                    # Normal timeout while waiting for client message (client is listening)
                    continue
                except (ConnectionError, OSError) as e:
                    self.logger.info(f"Client {client_id} disconnected: {e}")
                    break
                except Exception as e:
                    self.logger.error(f"Error receiving from {client_id}: {e}")
                    break

                msg_type = msg.get("type")
                payload = msg.get("payload", {})

                # ── PING ──────────────────────────────────────────
                if msg_type == MessageType.PING:
                    pong = create_message(MessageType.PONG, {
                        "echo_timestamp": payload.get("timestamp", 0),
                        "server_time": time.time(),
                    })
                    with self._send_lock:
                        send_message(client_socket, pong)

                # ── JOB SUBMIT ────────────────────────────────────
                elif msg_type == MessageType.JOB_SUBMIT:
                    current_job_id = self._handle_job_submit(
                        client_socket, client_id, payload
                    )

                # ── FILE TRANSFER START ───────────────────────────
                elif msg_type == MessageType.FILE_TRANSFER_START:
                    self._handle_file_receive(
                        client_socket, client_id, msg, current_job_id
                    )

                # ── FILE DOWNLOAD REQUEST ─────────────────────────
                elif msg_type == MessageType.FILE_DOWNLOAD_REQ:
                    self._handle_file_download(
                        client_socket, payload
                    )

                # ── SERVER STATUS ─────────────────────────────────
                elif msg_type == MessageType.SERVER_STATUS:
                    status = create_message(MessageType.SERVER_STATUS, {
                        "system_info": self.system_info,
                        "capabilities": self.gpu_engine.get_capabilities(),
                        "queue_status": self.task_queue.get_queue_status(),
                    })
                    send_message(client_socket, status)

                # ── JOB CANCEL ────────────────────────────────────
                elif msg_type == MessageType.JOB_CANCEL:
                    job_id = payload.get("job_id")
                    if job_id:
                        cancelled = self.task_queue.cancel_job(job_id)
                        resp = create_message(
                            MessageType.JOB_COMPLETE if cancelled else MessageType.ERROR,
                            {"job_id": job_id, "cancelled": cancelled}
                        )
                        send_message(client_socket, resp)

                # ── GPU STATS ─────────────────────────────────────
                elif msg_type == MessageType.GPU_STATS_REQUEST:
                    stats = get_gpu_live_stats()
                    resp = create_message(MessageType.GPU_STATS, {
                        "stats": stats,
                        "queue_status": self.task_queue.get_queue_status(),
                    })
                    with self._send_lock:
                        send_message(client_socket, resp)

                # ── SPEED TEST ────────────────────────────────────
                elif msg_type == MessageType.SPEED_TEST_REQ:
                    client_time = payload.get("client_time", time.time())
                    test_data = payload.get("data", "")
                    download_bytes = payload.get("request_download_bytes", 0)
                    
                    # Generate test download payload if requested
                    resp_data = "X" * download_bytes if download_bytes > 0 else ""
                    resp = create_message(MessageType.SPEED_TEST_RES, {
                        "echo_client_time": client_time,
                        "server_time": time.time(),
                        "upload_bytes_received": len(test_data),
                        "download_bytes_sent": len(resp_data),
                        "data": resp_data,
                    })
                    with self._send_lock:
                        send_message(client_socket, resp)

                # ── DISCONNECT ────────────────────────────────────
                elif msg_type == MessageType.DISCONNECT:
                    self.logger.info(f"Client {client_id} sent disconnect")
                    break

                else:
                    self.logger.warning(f"Unknown message type from {client_id}: {msg_type}")

        except Exception as e:
            self.logger.error(f"Unhandled error with client {client_id}: {e}", exc_info=True)
        finally:
            # Cleanup
            if current_job_id:
                with self._client_lock:
                    self._client_sockets.pop(current_job_id, None)
            try:
                client_socket.close()
            except Exception:
                pass
            self.logger.info(f"Connection closed for {client_id}")

    def _perform_handshake(self, client_socket: socket.socket, client_id: str) -> bool:
        """
        Execute the handshake protocol:
        1. Receive HANDSHAKE_REQUEST from client
        2. Validate protocol version
        3. Send HANDSHAKE_RESPONSE with server capabilities
        """
        try:
            client_socket.settimeout(HANDSHAKE_TIMEOUT)
            msg = receive_message(client_socket)
            client_socket.settimeout(SOCKET_TIMEOUT)

            if msg.get("type") != MessageType.HANDSHAKE_REQUEST:
                self.logger.warning(f"Expected handshake from {client_id}, got: {msg.get('type')}")
                error_msg = create_message(MessageType.ERROR, {
                    "message": "Expected HANDSHAKE_REQUEST as first message"
                })
                send_message(client_socket, error_msg)
                return False

            client_version = msg.get("version", "unknown")
            client_info = msg.get("payload", {})

            self.logger.info(
                f"Handshake from {client_id}: "
                f"version={client_version}, "
                f"client_os={client_info.get('os', 'unknown')}"
            )

            # Send handshake response with server capabilities
            response = create_message(MessageType.HANDSHAKE_RESPONSE, {
                "status": "accepted",
                "server_name": self.system_info["hostname"],
                "system_info": {
                    "os": self.system_info["os"],
                    "processor": self.system_info["processor"],
                    "gpu": self.system_info["gpu"],
                    "ffmpeg": self.system_info["ffmpeg"],
                },
                "capabilities": self.gpu_engine.get_capabilities(),
                "supported_presets": list(RENDER_PRESETS.keys()),
                "supported_resolutions": list(RESOLUTIONS.keys()),
            })
            send_message(client_socket, response)

            self.logger.info(f"Handshake completed with {client_id}")
            return True

        except socket.timeout:
            self.logger.warning(f"Handshake timeout with {client_id}")
            return False
        except Exception as e:
            self.logger.error(f"Handshake error with {client_id}: {e}")
            return False

    def _handle_job_submit(self, client_socket: socket.socket,
                           client_id: str, payload: dict) -> str:
        """Handle a job submission request."""
        job_type = payload.get("job_type", "transcode")
        config = payload.get("config", {})
        filename = payload.get("filename", "")

        self.logger.info(f"Job submission from {client_id}: type={job_type}, file={filename}")

        # Check capabilities
        capabilities = self.gpu_engine.get_capabilities()
        if job_type not in capabilities.get("supported_tasks", []):
            reject = create_message(MessageType.JOB_REJECTED, {
                "reason": f"Task type '{job_type}' is not supported on this worker",
                "supported_tasks": capabilities["supported_tasks"],
            })
            send_message(client_socket, reject)
            return None

        # Create input file path
        input_path = os.path.join(self.upload_dir, filename)

        # Create pending job (will be enqueued after file transfer completes)
        job = self.task_queue.create_job(job_type, input_path, config)

        # Register client socket for progress streaming
        with self._client_lock:
            self._client_sockets[job.job_id] = client_socket

        # Send acceptance
        accept = create_message(MessageType.JOB_ACCEPTED, {
            "job_id": job.job_id,
            "position_in_queue": self.task_queue.get_queue_status()["queue_size"],
        })
        with self._send_lock:
            send_message(client_socket, accept)

        self.logger.info(f"Job {job.job_id} accepted (pending file upload)")
        return job.job_id

    def _handle_file_receive(self, client_socket: socket.socket,
                             client_id: str, start_msg: dict, job_id: str):
        """Receive a file from the client and save it to the uploads directory."""
        payload = start_msg.get("payload", {})
        filename = payload.get("filename", "received_file")
        total_size = payload.get("size", 0)
        expected_checksum = payload.get("checksum", "")

        filepath = os.path.join(self.upload_dir, filename)
        self.logger.info(
            f"Receiving file from {client_id}: {filename} "
            f"({format_bytes(total_size)})"
        )

        bytes_received = 0
        try:
            with open(filepath, "wb") as f:
                while True:
                    msg = receive_message(client_socket)

                    if msg["type"] == MessageType.FILE_CHUNK:
                        chunk_data = base64.b64decode(msg["payload"]["data"])
                        f.write(chunk_data)
                        bytes_received += len(chunk_data)

                        # Log progress periodically
                        if total_size > 0 and bytes_received % (CHUNK_SIZE * 16) == 0:
                            pct = (bytes_received / total_size) * 100
                            self.logger.info(
                                f"Upload progress: {pct:.1f}% "
                                f"({format_bytes(bytes_received)}/{format_bytes(total_size)})"
                            )

                    elif msg["type"] == MessageType.FILE_TRANSFER_END:
                        break

            # Verify checksum
            if expected_checksum:
                actual_checksum = compute_file_checksum(filepath)
                if actual_checksum != expected_checksum:
                    os.remove(filepath)
                    error_msg = create_message(MessageType.ERROR, {
                        "message": "File checksum mismatch — transfer corrupted",
                        "expected": expected_checksum[:16],
                        "actual": actual_checksum[:16],
                    })
                    send_message(client_socket, error_msg)
                    self.logger.error(f"Checksum mismatch for {filename}")
                    return

            self.logger.info(f"File received successfully: {filename} ({format_bytes(bytes_received)})")

            # Enqueue job now that input file is completely received and verified
            if job_id:
                self.task_queue.enqueue_job(job_id)

            # Send confirmation
            confirm = create_message(MessageType.LOG_MESSAGE, {
                "message": f"File received: {filename} ({format_bytes(bytes_received)}) — checksum verified ✓",
                "level": "info",
            })
            with self._send_lock:
                send_message(client_socket, confirm)

        except Exception as e:
            self.logger.error(f"File receive error: {e}", exc_info=True)
            error_msg = create_message(MessageType.ERROR, {
                "message": f"File receive failed: {str(e)}"
            })
            try:
                send_message(client_socket, error_msg)
            except Exception:
                pass

    def _handle_file_download(self, client_socket: socket.socket, payload: dict):
        """Send a rendered output file back to the client."""
        job_id = payload.get("job_id")
        job = self.task_queue.get_job(job_id)

        if not job or job.status != JobStatus.COMPLETE:
            error_msg = create_message(MessageType.ERROR, {
                "message": f"Job {job_id} not found or not complete"
            })
            send_message(client_socket, error_msg)
            return

        output_path = job.output_file
        if not os.path.exists(output_path):
            error_msg = create_message(MessageType.ERROR, {
                "message": f"Output file not found: {output_path}"
            })
            send_message(client_socket, error_msg)
            return

        self.logger.info(f"Sending output file for job {job_id}: {output_path}")

        try:
            with self._send_lock:
                send_file_chunked(client_socket, output_path, job_id)
            self.logger.info(f"Output file sent for job {job_id}")
        except Exception as e:
            self.logger.error(f"Failed to send output file: {e}", exc_info=True)

    def _on_job_progress(self, job_id: str, progress: float, message: str):
        """Callback: Stream progress updates to the connected client."""
        with self._client_lock:
            client_socket = self._client_sockets.get(job_id)

        if not client_socket:
            return

        try:
            job = self.task_queue.get_job(job_id)

            if progress < 0:
                # Job failed
                fail_msg = create_message(MessageType.JOB_FAILED, {
                    "job_id": job_id,
                    "error": message,
                })
                with self._send_lock:
                    send_message(client_socket, fail_msg)
            elif progress >= 100:
                # Job complete
                result_info = job.result_info if job else {}
                complete_msg = create_message(MessageType.JOB_COMPLETE, {
                    "job_id": job_id,
                    "result": result_info,
                })
                with self._send_lock:
                    send_message(client_socket, complete_msg)
            else:
                # Progress update with live GPU / host telemetry
                live_gpu = get_gpu_live_stats()
                progress_msg = create_message(MessageType.JOB_PROGRESS, {
                    "job_id": job_id,
                    "progress": round(progress, 1),
                    "message": message,
                    "gpu_stats": live_gpu,
                })
                with self._send_lock:
                    send_message(client_socket, progress_msg)

        except (ConnectionError, OSError) as e:
            self.logger.warning(f"Failed to stream progress to client for job {job_id}: {e}")
            with self._client_lock:
                self._client_sockets.pop(job_id, None)


def main():
    """Entry point for the server daemon."""
    parser = argparse.ArgumentParser(
        description="Distributed Task Offloading — Remote Worker Node Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python server_daemon.py
    python server_daemon.py --host 192.168.1.1 --port 9850
    python server_daemon.py --work-dir /data/render_workspace
        """
    )
    parser.add_argument("--host", default="0.0.0.0",
                        help="IP address to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT,
                        help=f"Port to listen on (default: {DEFAULT_SERVER_PORT})")
    parser.add_argument("--work-dir", default="./workspace",
                        help="Working directory for uploads & output (default: ./workspace)")

    args = parser.parse_args()

    daemon = WorkerDaemon(
        host=args.host,
        port=args.port,
        work_dir=args.work_dir
    )

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutdown signal received...")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        daemon.start()
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    main()
