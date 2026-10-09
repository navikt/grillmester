"""Bounded, no-follow repository reads; never open special files or print data."""

import os
import stat
from contextlib import contextmanager
from pathlib import Path

LIMIT = 64 * 1024
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class Unavailable(ValueError):
    pass


@contextmanager
def parent(repo, name):
    parts = Path(name).parts
    if Path(name).is_absolute() or ".." in parts or not parts:
        raise Unavailable()
    fd = os.open(str(repo.resolve()), DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd, parts[-1]
    finally:
        os.close(fd)


def read(repo, name):
    fd = None
    try:
        with parent(repo, name) as (directory, leaf):
            info = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise Unavailable()
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
                raise Unavailable()
            with os.fdopen(os.dup(fd), "rb") as stream:
                data = stream.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise Unavailable()
            return data.decode("utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, RuntimeError):
        raise Unavailable() from None
    finally:
        if fd is not None:
            os.close(fd)


def regular(repo, name):
    try:
        with parent(repo, name) as (directory, leaf):
            return stat.S_ISREG(os.stat(leaf, dir_fd=directory, follow_symlinks=False).st_mode)
    except (OSError, RuntimeError, Unavailable):
        return False
