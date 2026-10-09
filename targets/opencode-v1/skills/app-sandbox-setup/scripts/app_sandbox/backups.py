"""Observe and move loose DB copies without reading their contents."""

import os
import re
import stat
from pathlib import Path

from . import rules
from .paths import display


OWNED_NAME = re.compile(r"data\.db\.\d{8}T\d{6}\.\d{6}Z\Z")


def identity(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_mode]


def observe(home, moving=False):
    directory = home / rules.BACKUP_DIRECTORY
    warnings, moves = [], []
    unsafe_parent = directory.is_symlink() or directory.parent.is_symlink()
    if moving and unsafe_parent:
        warnings.append("Backup moves refused: backup directory or parent is a symlink.")
    reserved = set()
    for source in sorted((home / ".copilot").glob("data.db*")):
        if source.name == "data.db" or source.name.endswith(rules.APP_OWNED_DB_SUFFIXES):
            continue
        try:
            info = source.lstat()
        except OSError:
            warnings.append("Backup copy unavailable; left untouched.")
            continue
        if not stat.S_ISREG(info.st_mode):
            warnings.append("Backup move refused (symlink or non-regular file): " + display(str(source)))
            continue
        if not moving:
            warnings.append(f"Backup copy {display(str(source))} is not covered by the deny list; "
                            "suggest moving it (do not delete it) with --move-backups into "
                            "~/.copilot/app-sandbox-setup-backups, which is denied.")
            continue
        if unsafe_parent:
            continue
        destination = directory / source.name
        suffix = 0
        # The generated-backup namespace is reserved for retention; moved copies
        # must never become eligible for pruning on a later apply.
        while destination.exists() or destination.is_symlink() or str(destination) in reserved or OWNED_NAME.fullmatch(destination.name):
            suffix += 1
            destination = directory / (source.name + "." + str(suffix))
        reserved.add(str(destination))
        moves.append({"source": str(source), "destination": str(destination), "identity": identity(info)})
    return warnings, moves


def move(plan, home):
    moved = 0
    for entry in plan.get("backup_moves", []):
        parent_fd = destination_fd = reservation_fd = None
        reserved = None
        destination = Path(entry["destination"])
        source = Path(entry["source"])
        try:
            directory = home / rules.BACKUP_DIRECTORY
            if directory.is_symlink() or directory.parent.is_symlink():
                raise OSError("unsafe parent")
            directory.mkdir(mode=0o700, exist_ok=True)
            directory.chmod(0o700)
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            parent_fd = os.open(str(directory.parent), flags)
            destination_fd = os.open(directory.name, flags, dir_fd=parent_fd)
            info = os.stat(source.name, dir_fd=parent_fd, follow_symlinks=False)
            if identity(info) != entry["identity"] or not stat.S_ISREG(info.st_mode):
                raise OSError("source changed")
            # O_EXCL refuses every existing destination, including broken links.
            # rename replaces only this operation's own empty reservation.
            reservation_fd = os.open(destination.name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                                     0o600, dir_fd=destination_fd)
            reserved = os.fstat(reservation_fd)
            current = os.stat(destination.name, dir_fd=destination_fd, follow_symlinks=False)
            if identity(current) != identity(reserved):
                raise OSError("destination changed")
            info = os.stat(source.name, dir_fd=parent_fd, follow_symlinks=False)
            if identity(info) != entry["identity"] or not stat.S_ISREG(info.st_mode):
                raise OSError("source changed")
            os.rename(source.name, destination.name, src_dir_fd=parent_fd, dst_dir_fd=destination_fd)
            reserved = None
            moved += 1
        except (OSError, ValueError, NotImplementedError):
            plan["warnings"].append("DB commit succeeded but backup move failed; copy left untouched where possible: "
                                    + display(str(source)) + "; inspect a fresh plan.")
        finally:
            if reserved is not None:
                try:
                    current = os.stat(destination.name, dir_fd=destination_fd, follow_symlinks=False)
                    if identity(current) == identity(reserved):
                        os.unlink(destination.name, dir_fd=destination_fd)
                except OSError:
                    pass
            for descriptor in (reservation_fd, destination_fd, parent_fd):
                if descriptor is not None:
                    os.close(descriptor)
    return moved
