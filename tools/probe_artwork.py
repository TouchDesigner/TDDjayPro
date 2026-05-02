"""
Test djay v3 artwork-via-HTTP-POST flow.

1. Spin up a threaded HTTP server on a free port that logs any inbound POST.
2. Send /djay/request/turntable/artwork <our_url> via OSC to djay (port 10001).
3. Wait a few seconds, report what arrived.

We try a few path variants since the binary stores `/request/turntable/artwork`
(no per-turntable index) but per-deck addressing might still be supported.
"""
import http.server
import socket, struct, sys, threading, time


received = []
lock = threading.Lock()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length > 0 else b''
        with lock:
            received.append({
                'path': self.path,
                'method': 'POST',
                'content_type': self.headers.get('Content-Type', '?'),
                'length': length,
                'first_bytes': body[:16].hex(),
            })
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

    def do_GET(self):
        with lock:
            received.append({'path': self.path, 'method': 'GET'})
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_):
        pass  # suppress default stderr logging


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def pad(b: bytes) -> bytes:
    b = b + b'\x00'
    return b + b'\x00' * ((4 - len(b) % 4) % 4)


def osc_msg(addr: str, args=()) -> bytes:
    body = pad(addr.encode())
    typetag = ','
    payload = b''
    for a in args:
        if isinstance(a, str):
            typetag += 's'; payload += pad(a.encode())
        elif isinstance(a, int):
            typetag += 'i'; payload += struct.pack('>i', a)
        elif isinstance(a, float):
            typetag += 'f'; payload += struct.pack('>f', a)
    return body + pad(typetag.encode()) + payload


def main():
    port = free_port()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    base = f'http://127.0.0.1:{port}'
    print(f'HTTP server listening on {base}')

    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    variants = [
        ('/djay/request/turntable/artwork',  [f'{base}/art-no-index']),
        ('/djay/request/turntable1/artwork', [f'{base}/art-tt1']),
        ('/djay/request/turntable/artwork',  [1, f'{base}/art-int-arg']),
    ]

    for addr, args in variants:
        pkt = osc_msg(addr, args)
        tx.sendto(pkt, ('127.0.0.1', 10001))
        print(f'  sent {addr}  args={args}  ({len(pkt)}B)')

    print('waiting 5s for POSTs…')
    time.sleep(5)

    server.shutdown()
    print(f'\n--- received {len(received)} request(s)')
    for r in received:
        print(f'  {r}')


if __name__ == '__main__':
    main()
