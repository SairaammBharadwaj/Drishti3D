"""Read selected members out of a remote ZIP without downloading it.

AGZ.zip is 29.8 GB; the flight segment we need is a few hundred images. The
server honours Range requests, so zipfile can drive random access through this
file-like shim and pull just the central directory plus the wanted members.
"""
import io, urllib.request

class HTTPFile(io.RawIOBase):
    def __init__(self, url, block=1 << 20):
        self.url, self.block, self.pos, self.cache = url, block, 0, {}
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as r:
            self.size = int(r.headers["Content-Length"])
    def _fetch(self, idx):
        if idx in self.cache: return self.cache[idx]
        a = idx * self.block; b = min(a + self.block, self.size) - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={a}-{b}"})
        for _ in range(3):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = r.read(); break
            except Exception: d = None
        if d is None: raise IOError(f"range {a}-{b} failed")
        if len(self.cache) > 512: self.cache.clear()
        self.cache[idx] = d
        return d
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos
    def read(self, n=-1):
        if n < 0: n = self.size - self.pos
        n = min(n, self.size - self.pos)
        out = bytearray()
        while n > 0:
            i = self.pos // self.block; o = self.pos % self.block
            chunk = self._fetch(i)[o:o + n]
            if not chunk: break
            out += chunk; self.pos += len(chunk); n -= len(chunk)
        return bytes(out)
