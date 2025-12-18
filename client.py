# client.py
import argparse, socket, json, sys

def request(host: str, port: int, payload: dict) -> dict:
    """Send a single JSON-line request and return a single JSON-line response."""
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    with socket.create_connection((host, port), timeout=5) as s:
        s.sendall(data)
        buff = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            buff += chunk
            if b"\n" in buff:
                line, _, _ = buff.partition(b"\n")
                return json.loads(line.decode("utf-8"))
    return {"ok": False, "error": "No response"}

def main():
    # Parse basic command line arguments.
    parser = argparse.ArgumentParser(description="Interactive client for JSON TCP server")
    parser.add_argument("--host", default="127.0.0.1")

    # If --port is given, I will use it directly and won't ask anything.
    # If it's missing, I will ask the user if they want proxy or direct server.
    parser.add_argument("--port", type=int, default=None)

    # Default ports for direct server and proxy. Just here to avoid magic numbers.
    parser.add_argument("--server-port", dest="server_port", type=int, default=5555)
    parser.add_argument("--proxy-port", dest="proxy_port", type=int, default=5554)

    args = parser.parse_args()

    host = args.host

    # Decide which port to use.
    if args.port is not None:
        # User gave an explicit port in the command line, so I respect it.
        port = args.port
    else:
        # No explicit port, so I let the user choose between server and proxy.
        print("No port was given, choose where to connect:")
        print(f"1) Direct server on port {args.server_port}")
        print(f"2) Proxy on port {args.proxy_port}")
        choice = input("Choose option (1-2) [1]: ").strip()

        if choice == "2":
            port = args.proxy_port
        else:
            # Default choice is direct connection to the server.
            port = args.server_port

    # Open one persistent TCP connection to the chosen target (server or proxy).
    with socket.create_connection((host, port), timeout=5) as s:
        print(f"[client] connected to {host}:{port}")

        # Main loop: keep sending requests until the user chooses to exit.
        while True:
            print("\n=== Client menu ===")
            print("1) Calc expression")
            print("2) GPT prompt")
            print("3) Exit")
            choice = input("Choose option (1-3): ").strip()

            if choice == "3":
                print("[client] closing connection, bye.")
                break

            if choice == "1":
                # Calc mode: choose sample expression or enter your own.
                print("\nCalc mode:")
                print("1) Use sample expression")
                print("2) Enter custom expression")
                sub = input("Choose option (1-2): ").strip()

                if sub == "1":
                    samples = ["1+2", "2*3", "sqrt(2)", "10/2", "sqrt(9)"]
                    print("\nSample expressions:")
                    for i, expr in enumerate(samples, start=1):
                        print(f"{i}) {expr}")
                    idx = input("Choose sample (1-5): ").strip()
                    try:
                        expr = samples[int(idx) - 1]
                    except Exception:
                        print("Invalid choice, try again.")
                        continue
                else:
                    expr = input("Enter expression: ").strip()
                    if not expr:
                        print("Empty expression, try again.")
                        continue

                payload = {
                    "mode": "calc",
                    "data": {"expr": expr},
                    "options": {"cache": True},
                }

            elif choice == "2":
                # GPT mode: read prompt from user.
                print("\nGPT mode:")
                prompt = input("Enter prompt text: ").strip()
                if not prompt:
                    print("Empty prompt, try again.")
                    continue

                payload = {
                    "mode": "gpt",
                    "data": {"prompt": prompt},
                    "options": {"cache": True},
                }

            else:
                print("Unknown option, please choose 1/2/3.")
                continue

            # Serialize payload as JSON line (one request ends with '\n').
            line = json.dumps(payload, ensure_ascii=False) + "\n"
            s.sendall(line.encode("utf-8"))

            # Read exactly one JSON-line response from the server (or proxy target).
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    print("[client] server closed the connection.")
                    return
                buf += chunk

            resp_line, _, _ = buf.partition(b"\n")
            resp = json.loads(resp_line.decode("utf-8"))

            # Print a simple, human-friendly result.
            if resp.get("ok"):
                print("\n[server] OK")
                print("result:", resp.get("result"))
                meta = resp.get("meta") or {}
                print("meta:", meta)


            else:
                print("\n[server] ERROR")
                print("error:", resp.get("error"))


if __name__ == "__main__":
    main()




