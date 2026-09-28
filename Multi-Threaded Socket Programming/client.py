"""
TCP Client
Connects to the server and exchanges messages continuously until 'exit'.
"""

import socket

# Server address (localhost)
HOST = "127.0.0.1"
PORT = 5000


def start_client():
    """Connects to the server and handles user input."""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((HOST, PORT))

    # Receive and print welcome message from server
    welcome = client.recv(1024).decode()
    print(welcome)

    try:
        while True:
            # Take input from user
            message = input("You: ").strip()

            # Ignore empty inputs
            if not message:
                continue

            # Send message to server
            client.send(message.encode())

            # Receive response from server
            response = client.recv(1024).decode()
            print(f"Server: {response}")

            # Stop loop if user typed exit
            if message.lower() == "exit":
                break

    except (ConnectionResetError, BrokenPipeError):
        print("[ERROR] Connection to server lost.")
    finally:
        client.close()


if __name__ == "__main__":
    start_client()
