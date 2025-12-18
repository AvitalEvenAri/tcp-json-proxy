# server.py
'''
Enabling real GPT calls (optional):
1. Install deps: pip install -r requirements.txt.
2. Create a .env file with OPENAI_API_KEY=... .
3. Replace call_gpt() in server.py with the real implementation shown in the comments, or keep the stub.
'''
import argparse, socket, json, time, threading, math, os, ast, operator, collections
from typing import Any, Dict
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from .env (OPENAI_API_KEY)
load_dotenv()

GEMINI_API_KEY = os.getenv("OPENAI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("[server] WARNING: OPENAI_API_KEY is not set. GPT mode will not work.")

# ---------------- LRU Cache (simple) ----------------
class LRUCache:
    """Minimal LRU cache based on OrderedDict."""
    def __init__(self, capacity: int = 128):
        self.capacity = capacity
        self._d = collections.OrderedDict()

    def get(self, key):
        if key not in self._d:
            return None
        self._d.move_to_end(key)
        return self._d[key]

    def set(self, key, value):
        self._d[key] = value
        self._d.move_to_end(key)
        if len(self._d) > self.capacity:
            self._d.popitem(last=False)

# ---------------- Safe Math Eval (no eval) ----------------
_ALLOWED_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "sqrt": math.sqrt,
    "log": math.log, "exp": math.exp, "max": max, "min": min, "abs": abs,
}
_ALLOWED_CONSTS = {"pi": math.pi, "e": math.e}
_ALLOWED_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.UAdd: operator.pos, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
}

def _eval_node(node):
    """Evaluate a restricted AST node safely."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("illegal constant type")
    if hasattr(ast, "Num") and isinstance(node, ast.Num):  # legacy fallback
        return node.n
    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTS:
            return _ALLOWED_CONSTS[node.id]
        raise ValueError(f"unknown symbol {node.id}")
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise ValueError("illegal function call")
        args = [_eval_node(a) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise ValueError("illegal expression")

def safe_eval_expr(expr: str) -> float:
    """Parse and evaluate the expression safely using ast (no eval)."""
    tree = ast.parse(expr, mode="eval")
    return float(_eval_node(tree.body))

def call_gpt(prompt: str) -> str:
    """
    Sends a text prompt to Google's Gemini model and returns the answer as plain text.
    This replaces the old stub we used earlier.
    """

    try:
        # I create a model object using the free Gemini model..
        model = genai.GenerativeModel("gemini-2.5-flash")
        # Send the prompt to Google and get the generated result.
        response = model.generate_content(prompt)

        # Sometimes the API returns an object without .text,
        # so I check it carefully before trying to use it.
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        else:
            return "[GPT] Empty response (model returned no text)."

    except Exception as e:
        # If anything goes wrong (network, wrong key, wrong model, etc.),
        # I return a readable error so the client won't crash.
        return f"[GPT-ERROR] {e}"



# ---------------- Server core ----------------
def handle_request(msg: Dict[str, Any], cache: LRUCache) -> Dict[str, Any]:
    mode = msg.get("mode")
    data = msg.get("data") or {}
    options = msg.get("options") or {}
    use_cache = bool(options.get("cache", True))

    started = time.time()
    cache_key = json.dumps(msg, sort_keys=True)

    if use_cache:
        hit = cache.get(cache_key)
        if hit is not None:
            took = int((time.time() - started) * 1000)
            # Server cache HIT: both from_cache and any_cache are True
            return {
                "ok": True,
                "result": hit,
                "meta": {
                    "from_cache": True,   # server's LRU cache
                    "any_cache": True,    # at least one cache was used (here: server)
                    "took_ms": took,
                },
            }


    try:
        if mode == "calc":
            expr = data.get("expr")
            if not expr or not isinstance(expr, str):
                return {"ok": False, "error": "Bad request: 'expr' is required (string)"}
            res = safe_eval_expr(expr)
        elif mode == "gpt":
            prompt = data.get("prompt")
            if not prompt or not isinstance(prompt, str):
                return {"ok": False, "error": "Bad request: 'prompt' is required (string)"}
            res = call_gpt(prompt)
        else:
            return {"ok": False, "error": "Bad request: unknown mode"}

        took = int((time.time() - started) * 1000)
        if use_cache:
            cache.set(cache_key, res)

        # Server cache MISS: from_cache=False, any_cache=False (no proxy involved yet)
        return {
            "ok": True,
            "result": res,
            "meta": {
                "from_cache": False,  # server did NOT take from its cache
                "any_cache": False,  # no cache used at this stage
                "took_ms": took,
            },
        }

    except Exception as e:
        return {"ok": False, "error": f"Server error: {e}"}

def serve(host: str, port: int, cache_size: int):
    cache = LRUCache(cache_size)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(16)
        print(f"[server] listening on {host}:{port} (cache={cache_size})")
        while True:
            conn, addr = s.accept()
            print(f"[server] new connection from {addr}")
            threading.Thread(target=handle_client, args=(conn, addr, cache), daemon=True).start()

def handle_client(conn: socket.socket, addr, cache: LRUCache):
    # This function handles one client connection.
    # The connection stays open and may contain multiple requests.
    with conn:
        print(f"[server] start handling client {addr}")
        try:
            buffer = b""  # stores data received from the socket

            while True:
                chunk = conn.recv(4096)
                # If recv() returns empty bytes, the client closed the connection
                if not chunk:
                    break

                buffer += chunk

                # Process every full line (each request ends with '\n')
                while b"\n" in buffer:
                    line, _, rest = buffer.partition(b"\n")
                    buffer = rest  # keep remaining bytes for next request
                    print(f"[server] got request from {addr}")

                    # Convert bytes -> string -> JSON object
                    msg = json.loads(line.decode("utf-8"))

                    # Handle the logical request (calc / gpt / cache)
                    resp = handle_request(msg, cache)

                    # Convert response to JSON + newline (required by protocol)
                    reply = (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")

                    # Send reply back to the client
                    conn.sendall(reply)

        except Exception as e:
            # If something goes wrong (e.g. malformed JSON), try to send an error message
            try:
                err = {"ok": False, "error": f"Malformed: {e}"}
                conn.sendall((json.dumps(err) + "\n").encode("utf-8"))
            except:
                # If even this fails, just ignore (connection likely dead)
                pass


def main():
    ap = argparse.ArgumentParser(description="JSON TCP server (calc/gpt) — student skeleton")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--cache-size", type=int, default=128)
    args = ap.parse_args()
    serve(args.host, args.port, args.cache_size)

if __name__ == "__main__":
    main()
