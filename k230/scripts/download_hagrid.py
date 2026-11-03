"""Resumable, parallel-range downloader for the HaGRID 30k sample.

The international link is throttled to roughly 0.3 MiB/s in total, so this uses a
chunked ranged download with resume: every finished chunk is kept, interrupted
runs continue where they stopped, and the final file is concatenated in order.
"""
import os
import re
import sys
import threading
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
SRC = "https://huggingface.co/datasets/cj-mills/hagrid-sample-30k-384p/resolve/main/hagrid-sample-30k-384p.zip"
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_downloads")
OUT = os.path.join(ROOT, "hagrid-sample-30k-384p.zip")
CHUNK = 32 << 20  # 32 MiB per chunk
WORKERS = 6


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.newurl = newurl
        return None


def resolve(url, timeout=30):
    """Follow the hub redirect manually so we can hit the CDN directly."""
    op = urllib.request.build_opener(NoRedirect)
    try:
        op.open(urllib.request.Request(url, headers=UA), timeout=timeout)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location")
        if loc:
            return loc
        raise
    raise RuntimeError("no redirect returned")


def content_length(url, timeout=30):
    headers = dict(UA)
    headers["Range"] = "bytes=0-0"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        cr = r.headers.get("Content-Range") or ""
        m = re.search(r"/(\d+)$", cr)
        if m:
            return int(m.group(1))
        total = r.headers.get("Content-Length")
        if total:
            return int(total)
    raise RuntimeError("cannot determine size")


def fetch_chunk(url, idx, start, end, path, log):
    """Download [start, end] into path, resuming from the existing partial size."""
    need = end - start + 1
    have = os.path.getsize(path) if os.path.exists(path) else 0
    if have >= need:
        return have
    headers = dict(UA)
    headers["Range"] = f"bytes={start + have}-{end}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as r:
            mode = "ab" if have else "wb"
            with open(path, mode) as f:
                while have < need:
                    c = r.read(256 * 1024)
                    if not c:
                        break
                    f.write(c)
                    have += len(c)
    except Exception as e:
        log(f"chunk {idx}: {type(e).__name__} {str(e)[:70]} (at {have / 2**20:.0f}MiB)")
    return have


def main():
    os.makedirs(ROOT, exist_ok=True)
    if os.path.exists(OUT) and os.path.getsize(OUT) > 0:
        print(f"already downloaded: {OUT} ({os.path.getsize(OUT) / 2**20:.1f}MiB)")
        return 0

    url = resolve(SRC)
    total = content_length(url)
    print(f"total size: {total / 2**20:.1f}MiB, chunk={CHUNK / 2**20:.0f}MiB, workers={WORKERS}", flush=True)

    parts_dir = os.path.join(ROOT, ".parts_30k")
    os.makedirs(parts_dir, exist_ok=True)
    jobs = []
    for i, start in enumerate(range(0, total, CHUNK)):
        jobs.append((i, start, min(start + CHUNK - 1, total - 1)))
    print(f"chunks: {len(jobs)}", flush=True)

    lock = threading.Lock()
    state = {"done": 0}

    def log(msg):
        with lock:
            print("   ", msg, flush=True)

    def worker():
        while True:
            with lock:
                if not jobs:
                    return
                idx, start, end = jobs.pop(0)
            path = os.path.join(parts_dir, f"{idx:04d}.part")
            fetch_chunk(url, idx, start, end, path, log)
            size = os.path.getsize(path) if os.path.exists(path) else 0
            if size == end - start + 1:
                with lock:
                    state["done"] += 1
                    print(f"    chunk {idx} ok ({state['done']}/{len(range(0, total, CHUNK))}) "
                          f"{state['done'] * CHUNK / 2**20:.0f}MiB", flush=True)
            else:
                with lock:
                    jobs.append((idx, start, end))

    t0 = time.time()
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    got = sum(os.path.getsize(os.path.join(parts_dir, f)) for f in os.listdir(parts_dir))
    print(f"downloaded {got / 2**20:.1f}/{total / 2**20:.1f}MiB in {(time.time() - t0) / 60:.1f} min", flush=True)
    if got != total:
        print("INCOMPLETE — rerun to resume")
        return 1

    with open(OUT, "wb") as out:
        for i in range(len(range(0, total, CHUNK))):
            with open(os.path.join(parts_dir, f"{i:04d}.part"), "rb") as f:
                while True:
                    b = f.read(4 << 20)
                    if not b:
                        break
                    out.write(b)
    print(f"assembled -> {OUT} ({os.path.getsize(OUT) / 2**20:.1f}MiB)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
