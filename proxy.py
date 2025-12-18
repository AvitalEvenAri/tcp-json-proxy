# proxy.py
import argparse
import socket
import threading
import json

# Simple in-memory cache for the proxy.
# Key: request JSON string, Value: response JSON string.
PROXY_CACHE = {}


def forward_request_to_server(req_json_str: str, server_host: str, server_port: int) -> str:
    """
    Send a single JSON request to the real server and read a single JSON reply.
    I open a short TCP connection for each request, to keep the code simple.
    The proxy still keeps a persistent connection only with the client.
    """
    # Connect to the real server
    with socket.create_connection((server_host, server_port), timeout=5) as s:
        # Send the request as one JSON line
        s.sendall((req_json_str + "\n").encode("utf-8"))

        # Read until we get one full line (one reply)
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                # Server closed the connection unexpectedly
                break
            buf += chunk

        line, _, _ = buf.partition(b"\n")
        if not line:
            raise RuntimeError("Empty response from server")

        # Return the reply as a UTF-8 string (without the newline)
        return line.decode("utf-8").strip()


def handle(client_sock: socket.socket, addr, server_host: str, server_port: int):
    """
    Handle one client connection to the proxy.
    The client can send multiple JSON requests on the same TCP connection.
    For each request, I first check the proxy cache.
    If it is not in the cache, I forward it to the real server.
    I also decorate the server's JSON with extra meta fields:
    - proxy_from_cache: did the proxy serve from its own cache?
    - any_cache: did any cache (server or proxy) handle this response?
    """
    print(f"[proxy] start handling client {addr}")

    with client_sock:
        buffer = b""

        try:
            while True:
                # Read raw bytes from the client
                chunk = client_sock.recv(4096)
                if not chunk:
                    # Client closed the connection
                    break

                buffer += chunk

                # Process all complete lines (each request ends with '\n')
                while b"\n" in buffer:
                    line, _, rest = buffer.partition(b"\n")
                    buffer = rest

                    # Decode the request line to a string
                    req_str = line.decode("utf-8").strip()
                    if not req_str:
                        # Ignore empty lines
                        continue

                    print(f"[proxy] got request from {addr}: {req_str}")

                    # We will first get the "base" reply from cache or server,
                    # and remember if it came from the proxy cache.
                    served_from_proxy_cache = False

                    if req_str in PROXY_CACHE:
                        print("[proxy] cache HIT")
                        reply_base = PROXY_CACHE[req_str]
                        served_from_proxy_cache = True
                    else:
                        print("[proxy] cache MISS, contacting server")
                        # Ask the real server for a reply (one JSON line as string)
                        reply_base = forward_request_to_server(req_str, server_host, server_port)
                        # Store the *server* reply in the proxy cache (without proxy meta)
                        PROXY_CACHE[req_str] = reply_base
                        served_from_proxy_cache = False

                    # Now try to parse the JSON so we can extend the "meta" section.
                    try:
                        resp_obj = json.loads(reply_base)
                    except json.JSONDecodeError:
                        # If it's not valid JSON, just forward as-is.
                        client_sock.sendall((reply_base + "\n").encode("utf-8"))
                        continue

                    meta = resp_obj.get("meta") or {}
                    if not isinstance(meta, dict):
                        meta = {}

                    # meta.from_cache refers to the SERVER's internal cache.
                    server_from_cache = bool(meta.get("from_cache"))

                    # New flag: did the PROXY serve from its own cache?
                    meta["proxy_from_cache"] = served_from_proxy_cache

                    # New flag: did ANY cache handle this? (server OR proxy)
                    any_cache = bool(server_from_cache or served_from_proxy_cache)
                    meta["any_cache"] = any_cache

                    resp_obj["meta"] = meta

                    # Serialize back to JSON string for the client
                    reply_str = json.dumps(resp_obj, ensure_ascii=False)

                    # Send the reply back to the client as one JSON line
                    client_sock.sendall((reply_str + "\n").encode("utf-8"))

        except Exception as e:
            # If something goes wrong in the proxy, try to send an error JSON
            print(f"[proxy] error while handling client {addr}: {e}")
            try:
                err = {"ok": False, "error": f"Proxy error: {e}"}
                client_sock.sendall((json.dumps(err) + "\n").encode("utf-8"))
            except Exception:
                # If we cannot even send the error, just give up
                pass

    print(f"[proxy] connection closed {addr}")



def main():
    parser = argparse.ArgumentParser(description="Application-level JSON proxy")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=5554)
    parser.add_argument("--server-host", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=5555)
    args = parser.parse_args()

    # Create a listening TCP socket for incoming clients
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((args.listen_host, args.listen_port))
        listener.listen(16)

        print(f"[proxy] listening on {args.listen_host}:{args.listen_port}, "
              f"forwarding to {args.server_host}:{args.server_port}")

        while True:
            # Accept a new client and handle it in a separate thread
            client_conn, addr = listener.accept()
            threading.Thread(
                target=handle,
                args=(client_conn, addr, args.server_host, args.server_port),
                daemon=True
            ).start()


if __name__ == "__main__":
    main()
