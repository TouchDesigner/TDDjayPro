"""
Tiny OSC sniffer for djay Pro v3.
Binds 10000, captures bundles for `seconds` (default 6s), prints unique
addresses with hit counts and a sample arg value.

Usage: python3 tools/sniff_djay.py [seconds]
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


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 10000))
    s.setblocking(False)
    print(f"listening on 10000 for {seconds}s…")

    end = time.time() + seconds
    seen = {}
    total_pkts = total_msgs = 0
    STREAM_PREFIXES = ('/djay/turntable1/playback/', '/djay/turntable2/playback/',
                       '/djay/turntable3/playback/', '/djay/turntable4/playback/',
                       '/djay/mixer/turntable1/meter', '/djay/mixer/turntable2/meter',
                       '/djay/mixer/turntable3/meter', '/djay/mixer/turntable4/meter')
    while time.time() < end:
        r, _, _ = select.select([s], [], [], 0.2)
        for sock in r:
            data, _ = sock.recvfrom(65535)
            total_pkts += 1
            msgs = []
            try:
                walk(data, msgs)
            except Exception as e:
                continue
            for a, args in msgs:
                total_msgs += 1
                seen.setdefault(a, []).append(args)

    # Filter out 60Hz streams to highlight what changed during the window
    interesting = {a: v for a, v in seen.items() if not a.startswith(STREAM_PREFIXES)}
    print(f"\n--- {total_pkts} pkts, {total_msgs} msgs, {len(seen)} unique addresses")
    print(f"--- {len(interesting)} non-stream addresses:")
    for a, samples in sorted(interesting.items()):
        last = samples[-1]
        print(f"  {len(samples):4d}  {a}  -> {last}")


if __name__ == '__main__':
    main()
