#!/usr/bin/env python3
"""Extract a verified ZIP into a fresh tree, preserving Unix file modes and links."""
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import zipfile


def extract(archive_path, destination):
    root = Path(destination).resolve()
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip():
            raise ValueError('ZIP CRC validation failed')
        members = archive.infolist()
        seen = set()
        for info in members:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename:
                raise ValueError('Unsafe archive member')
            normalized = str(path)
            if normalized in seen or normalized in ('', '.'):
                raise ValueError('Duplicate or empty archive member')
            seen.add(normalized)
            target = root / path
            if not target.resolve().is_relative_to(root) or target.exists() or target.is_symlink():
                raise ValueError('Archive would overwrite an existing path')
        # Files first, links last: writing a member never follows an archive link.
        for info in members:
            target = root / info.filename
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod((mode & 0o777) or 0o644)
        for info in members:
            if not stat.S_ISLNK(info.external_attr >> 16):
                continue
            target = root / info.filename
            link = archive.read(info).decode('utf-8')
            if Path(link).is_absolute() or not (target.parent / link).resolve().is_relative_to(root):
                raise ValueError('Unsafe archive link')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(link)
    print('Archive CRC, paths and extraction checked:', archive_path)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Usage: extract_archive.py ARCHIVE DESTINATION')
        extract(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        sys.exit(f'Extraction failed: {error}')
