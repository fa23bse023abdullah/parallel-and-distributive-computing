"""
Multi-Threaded TCP Server
Handles multiple client connections simultaneously using Python threading.
"""

import socket
import threading

# Server configuration
HOST = "0.0.0.0"
PORT = 5000

# Thread lock to synchronize console output and prevent race conditions
lock = threading.Lock()


def handle_client(conn, addr):
    """Handles communication with a single connected client."""
    client_ip = addr[0]
    client_port = addr[1]
    thread_name = threading.current_thread().name

    # Lock before printing to keep console output clean
    lock.acquire()
    print(f"[NEW CONNECTION] Thread: {thread_name} | Client IP: {client_ip} | Port: {client_port}")
    lock.release()

    # Send welcome message to client
    conn.send("Welcome! Type 'exit' to disconnect.".encode())

    try:
        while True:
            # Receive message from client
            data = conn.recv(1024)
            if not data:
                break

            message = data.decode().strip()

            # Synchronize console print using lock
            lock.acquire()
            print(f"[{thread_name}] {client_ip}:{client_port} -> {message}")
            lock.release()

            # If client sends exit
            if message.lower() == "exit":
                conn.send("Goodbye!".encode())
                break

            # Send response back to client
            reply = f"Server received: {message}"
            conn.send(reply.encode())

    except ConnectionResetError:
        pass
    finally:
        # Client disconnect log
        lock.acquire()
        print(f"[DISCONNECTED] Thread: {thread_name} | Client: {client_ip}:{client_port}")
        lock.release()
        conn.close()


def start_server():
    """Starts the TCP server and listens for incoming connections."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()

    print(f"[STARTING] Server is listening on {HOST}:{PORT}")

    while True:
        # Accept new client connection
        conn, addr = server.accept()

        # Start a new thread for each client
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()


if __name__ == "__main__":
    start_server()
