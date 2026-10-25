"""Isolated native crash probe; synthetic bytes and localhost fixture only.

Run as a child process. No real Zotero, cloud, vault or device is accessed.
The churn case adapts the official CPython issue 158200 reproducer.
"""
import argparse
import ctypes
from contextlib import ExitStack
import faulthandler
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time
import types


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['churn', 'httpx', 'dpapi'])
    parser.add_argument('--watchdog', action='store_true')
    parser.add_argument('--safe', action='store_true')
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--interval', type=float, default=.0001)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32')
        kernel.SetErrorMode.argtypes = [ctypes.c_uint]
        kernel.SetErrorMode.restype = ctypes.c_uint
        kernel.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    # Matches the helper's live, blocked pipe reader, without sending commands.
    reader = threading.Thread(target=lambda: sys.stdin.buffer.read(), daemon=True)
    reader.start()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    counter = 0
    started = time.monotonic()
    stop_at = started + args.seconds
    with ExitStack() as contexts:
        if args.safe:
            sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
            from note_organizer.zotero_worker import _periodic_stack_diagnostics
            contexts.enter_context(_periodic_stack_diagnostics(args.output, interval=args.interval))
        else:
            output = contexts.enter_context(args.output.open('wb'))
        if args.watchdog:
            faulthandler.dump_traceback_later(args.interval, repeat=True, file=output)
        try:
            if args.mode == 'churn':
                def template():
                    return 1
                while time.monotonic() < stop_at:
                    code = template.__code__.replace()
                    function = types.FunctionType(code, {})
                    function()
                    function = None
                    code = None
                    counter += 1
            elif args.mode == 'dpapi':
                from note_organizer.remarkable_cloud import _dpapi
                value = b'isolated disposable credential, never persisted'
                while time.monotonic() < stop_at:
                    protected = _dpapi(value)
                    assert _dpapi(protected, decrypt=True) == value
                    counter += 1
            else:
                import httpx2
                class Handler(BaseHTTPRequestHandler):
                    protocol_version = 'HTTP/1.1'
                    def do_GET(self):
                        data = b'{"data":{"key":"TESTKEY2","title":"Disposable"}}'
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Content-Length', str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                    def log_message(self, *args):
                        pass
                server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                with httpx2.Client(trust_env=False, timeout=5) as client:
                    while time.monotonic() < stop_at:
                        reply = client.get('http://127.0.0.1:' + str(server.server_port) + '/users/0/items/TESTKEY2')
                        assert reply.json()['data']['key'] == 'TESTKEY2'
                        counter += 1
                server.shutdown()
                server.server_close()
        finally:
            if args.watchdog:
                faulthandler.cancel_dump_traceback_later()
    print(json.dumps({'mode': args.mode, 'watchdog': args.watchdog, 'safe': args.safe, 'count': counter,
                      'seconds': round(time.monotonic() - started, 3), 'python': sys.version}), flush=True)
    # The driver closes stdin after receiving the flushed completion record.
    # Let the blocked reader exit before CPython finalization; the first probe
    # harness omitted this and hit an unrelated buffered-stdin shutdown error.
    reader.join(timeout=5)


if __name__ == '__main__':
    main()
