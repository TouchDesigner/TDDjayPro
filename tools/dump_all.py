"""
Probe djay Pro v3 with /djay/request/dumpAll and capture the full state burst.

Listens on 10000 (where djay sends), then sends the dumpAll request to
127.0.0.1:10001 (where djay listens), then keeps listening for a few seconds
to capture the response flood. Prints unique addresses with hit counts and
sample arg values, grouped by category.
"""
import socket, select, struct, sys, time


def read_str(buf, off):
    end = buf.index(b'\x00', off)
    s = buf[off:end].decode('utf-8', 'replace')
    off = end + 1
    off += (4 - off % 4) % 4
    return s, off


def parse_msg(data):
    addr, off = read_str(data, 0)
    if off >= len(data):
        return addr, []
    types, off = read_str(data, off)
    args = []
    for t in types.lstrip(','):
        if t == 'f':
            args.append(struct.unpack('>f', data[off:off+4])[0]); off += 4
        elif t == 'i':
            args.append(struct.unpack('>i', data[off:off+4])[0]); off += 4
        elif t == 's':
            s, off = read_str(data, off); args.append(s)
        elif t in 'TF':
            args.append(t == 'T')
        else:
            args.append(f'<{t}>')
    return addr, args


def walk(data, out):
    if data.startswith(b'#bundle\x00'):
        off = 16
        while off < len(data):
            size = struct.unpack('>i', data[off:off+4])[0]
            off += 4
            walk(data[off:off+size], out)
            off += size
    elif data.startswith(b'/'):
        out.append(parse_msg(data))


def build_osc_message(addr: str, args=()) -> bytes:
    def pad(s: bytes) -> bytes:
        s = s + b'\x00'
        s += b'\x00' * ((4 - len(s) % 4) % 4)
        return s
    body = pad(addr.encode())
    typetag = ','
    payload = b''
    for a in args:
        if isinstance(a, int):
            typetag += 'i'; payload += struct.pack('>i', a)
        elif isinstance(a, float):
            typetag += 'f'; payload += struct.pack('>f', a)
        elif isinstance(a, str):
            typetag += 's'; payload += pad(a.encode())
        else:
            raise TypeError(f"unsupported OSC arg type: {type(a)}")
    body += pad(typetag.encode())
    return body + payload


STREAM_PREFIXES = (
    '/djay/turntable1/playback/', '/djay/turntable2/playback/',
    '/djay/turntable3/playback/', '/djay/turntable4/playback/',
    '/djay/mixer/turntable1/meter', '/djay/mixer/turntable2/meter',
    '/djay/mixer/turntable3/meter', '/djay/mixer/turntable4/meter',
    '/djay/turntable1/neuralmix/', '/djay/turntable2/neuralmix/',
    '/djay/turntable3/neuralmix/', '/djay/turntable4/neuralmix/',
)


def main():
    capture = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(('0.0.0.0', 10000))
    rx.setblocking(False)

    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    pkt = build_osc_message('/djay/request/dumpAll')
    print(f"sending /djay/request/dumpAll to 127.0.0.1:10001 ({len(pkt)}B)")
    tx.sendto(pkt, ('127.0.0.1', 10001))

    print(f"listening on 10000 for {capture}s…")
    end = time.time() + capture
    seen = {}
    total_pkts = total_msgs = 0
    while time.time() < end:
        r, _, _ = select.select([rx], [], [], 0.2)
        for sock in r:
            data, _ = sock.recvfrom(65535)
            total_pkts += 1
            msgs = []
            try:
                walk(data, msgs)
            except Exception:
                continue
            for a, args in msgs:
                total_msgs += 1
                seen.setdefault(a, []).append(args)

    print(f"\n--- {total_pkts} pkts, {total_msgs} msgs, {len(seen)} unique addresses\n")

    # Group by family. Print all addresses including streams since dumpAll is one-shot.
    families = {}
    for a, samples in seen.items():
        # /djay/turntable1/foo/bar -> family 'turntable1/foo'  (or 'mixer/...')
        parts = a.split('/')
        if len(parts) >= 4:
            fam = '/'.join(parts[2:4])
        else:
            fam = '/'.join(parts[2:])
        families.setdefault(fam, []).append((a, samples))

    for fam in sorted(families):
        print(f"=== {fam}")
        for a, samples in sorted(families[fam]):
            last = samples[-1]
            tag = ' [stream]' if a.startswith(STREAM_PREFIXES) else ''
            print(f"  {len(samples):4d}  {a}{tag}  -> {last}")
        print()


if __name__ == '__main__':
    main()
