"""Reuse the current prepared PDF while its sources and library are unchanged."""
from pathlib import Path


def file_version(path):
    try:
        info = Path(path).stat()
    except OSError:
        return None
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


class ReaderSource:
    def __init__(self, key, path, versions, location=None):
        self.key, self.path = key, Path(path)
        # Source/library versions were captured before preparation. A source
        # changed during that work must invalidate reuse on the next request.
        self.versions = dict(versions)
        self.versions.setdefault(self.path, file_version(self.path))
        self.location = dict(location or {})

    def reusable(self, key):
        return (self.key == key and self.versions[self.path] is not None and
                all(file_version(path) == version for path, version in self.versions.items()))
