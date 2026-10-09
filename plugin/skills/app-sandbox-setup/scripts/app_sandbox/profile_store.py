"""No-follow file snapshots, private backups and atomic compare-before-write."""

import hashlib
import os
import stat
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .paths import SetupError

LIMIT = 1024 * 1024
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@contextmanager
def directory(path, create=False):
    """Anchor every ancestor with dir_fd; never follow a parent symlink."""
    if not path.is_absolute() or ".." in path.parts:
        raise SetupError(1, "File location must be absolute without parent traversal.")
    descriptor = os.open("/", FLAGS)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            next_fd = os.open(part, FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_fd
        yield descriptor
    finally:
        os.close(descriptor)


def _read(parent, name):
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return {"exists": False, "mode": 0o600, "text": ""}
    if not stat.S_ISREG(info.st_mode):
        raise SetupError(1, "Profile/properties file is symlinked or not regular; refused, target untouched.")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
            raise SetupError(1, "File changed while reading; rerun plan.")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise SetupError(1, "File exceeds the safe size limit; use manual instructions.")
        return {"exists": True, "mode": stat.S_IMODE(opened.st_mode),
                "text": data.decode("utf-8")}
    finally:
        os.close(fd)


def snapshot(path):
    try:
        with directory(path.parent) as parent:
            return _read(parent, path.name)
    except FileNotFoundError:
        return {"exists": False, "mode": 0o600, "text": ""}
    except OSError:
        raise SetupError(1, "File or parent is inaccessible/symlinked; refused, nothing written.") from None


def fingerprint(state):
    return hashlib.sha256(repr((state["exists"], state["mode"], state["text"])).encode()).hexdigest()


def write(path, before, text, home):
    if before["text"] == text:
        return None
    backup = None
    try:
        with directory(path.parent, create=True) as parent:
            if _read(parent, path.name) != before:
                raise SetupError(4, "File changed since plan; rerun plan and confirm.")
            if before["exists"]:
                destination = home / ".copilot/app-sandbox-setup-backups"
                with directory(destination, create=True) as backup_fd:
                    os.fchmod(backup_fd, 0o700)
                    name = path.name + "." + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
                    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=backup_fd)
                    with os.fdopen(fd, "wb") as stream:
                        os.fchmod(stream.fileno(), 0o600)
                        stream.write(before["text"].encode("utf-8"))
                        stream.flush()
                        os.fsync(stream.fileno())
                    backup = str(destination / name)
            temporary = ".app-sandbox-setup-" + uuid.uuid4().hex
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    os.fchmod(stream.fileno(), before["mode"])
                    stream.write(text.encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
                if _read(parent, path.name) != before:
                    raise SetupError(4, "File changed during apply; target untouched, rerun plan.")
                os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
    except OSError:
        raise SetupError(1, "Atomic file update failed; inspect a fresh plan. Backup retained if created.") from None
    return backup
