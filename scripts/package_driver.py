#!/usr/bin/env python3
"""Validate the final Android ELF and create a fresh Adreno Tools package."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import time
import zipfile

SYSTEM_LIBS = {'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libandroid.so',
               'libz.so', 'libnativewindow.so', 'libsync.so', 'libhardware.so'}


def validate_elf(data, library_name):
    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('Expected little-endian ELF64')
    header = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    if header[:3] != (3, 183, 1):
        raise ValueError('Expected an AArch64 shared library')
    phoff, phsize, phcount = header[4], header[8], header[9]
    if phsize != 56 or not phcount or phoff + phsize * phcount > len(data):
        raise ValueError('Invalid ELF program headers')
    loads, dynamic = [], None
    for index in range(phcount):
        kind, flags, offset, address, _, size, memsize, align = struct.unpack_from(
            '<IIQQQQQQ', data, phoff + index * phsize)
        if offset + size > len(data):
            raise ValueError('Truncated ELF segment')
        if kind == 1:
            if size > memsize or align < 16384 or align & (align - 1) or (address - offset) % align:
                raise ValueError('LOAD segment is not compatible with 16 KiB pages')
            if flags & 3 == 3:
                raise ValueError('Writable executable LOAD segment')
            loads.append((offset, address, size))
        elif kind == 2:
            if dynamic is not None:
                raise ValueError('Duplicate dynamic table')
            dynamic = (offset, size)
    if not loads or dynamic is None or dynamic[1] % 16:
        raise ValueError('Missing or invalid load/dynamic table')
    tags, terminated = {}, False
    for offset in range(dynamic[0], sum(dynamic), 16):
        tag, value = struct.unpack_from('<qQ', data, offset)
        if tag == 0:
            terminated = True
            break
        tags.setdefault(tag, []).append(value)
    if not terminated or any(len(tags.get(tag, [])) != 1 for tag in (5, 10, 14)):
        raise ValueError('Missing dynamic string table, size or SONAME')
    if 22 in tags or any(value & 4 for value in tags.get(30, [])):
        raise ValueError('Text relocations are unsupported')
    address, size = tags[5][0], tags[10][0]
    table = None
    for offset, vaddr, filesz in loads:
        if vaddr <= address and address + size <= vaddr + filesz:
            start = offset + address - vaddr
            table = data[start:start + size]
            break
    if table is None:
        raise ValueError('Dynamic string table is not file-backed')

    def string_at(index):
        if index >= len(table) or table.find(b'\0', index) < 0:
            raise ValueError('Invalid dynamic string offset or terminator')
        return table[index:table.find(b'\0', index)].decode('ascii')

    if string_at(tags[14][0]) != library_name:
        raise ValueError('SONAME does not match libraryName')
    needed = sorted({string_at(index) for index in tags.get(1, [])})
    if set(needed) - SYSTEM_LIBS:
        raise ValueError('Unbundled dependencies: ' + ', '.join(sorted(set(needed) - SYSTEM_LIBS)))
    return needed


def create_package(args):
    if args.output.exists():
        raise ValueError('Existing output: use a fresh run directory')
    data = args.library.read_bytes()
    needed = validate_elf(data, args.library.name)
    version = args.version_file.read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.+-]+)?', version):
        raise ValueError('Invalid Mesa version')
    for value, length in [(args.commit, 40), (args.source_sha256, 64), (args.ndk_sha256, 64)]:
        if not re.fullmatch('[0-9a-f]{' + str(length) + '}', value):
            raise ValueError('Invalid source identity')
    if args.api != 34:
        raise ValueError('This configuration is reviewed for API 34 only')
    code = str(time.time_ns() // 1_000_000)
    build_id = os.environ.get('GITHUB_RUN_ID', 'local') + '-' + os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    package_version = code + '-' + args.commit[:12] + '-' + build_id
    metadata = dict(schemaVersion=1, name='Mesa Turnip ' + version,
                    description='ARM64 / KGSL; release build, no LTO. Device compatibility requires testing.',
                    author='freedreno_turnip-CI contributors', packageVersion=package_version,
                    vendor='Mesa', driverVersion=version, minApi=args.api, libraryName=args.library.name)
    versions = {}
    for package in ('meson', 'ninja', 'Mako', 'MarkupSafe', 'packaging', 'PyYAML'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = 'not installed in packaging interpreter'
    info = dict(mesaCommit=args.commit, mesaArchiveSha256=args.source_sha256,
                ndkVersion='r29', ndkArchiveSha256=args.ndk_sha256, pythonPackages=versions,
                librarySha256=hashlib.sha256(data).hexdigest(), needed=needed,
                api=args.api, lto=False, pageSize=16384, version=version,
                packageVersion=package_version, versionCode=code, runtimeTested=False,
                sourceUrl='https://gitlab.freedesktop.org/mesa/mesa/-/commit/' + args.commit)

    def payload(obj):
        return (json.dumps(obj, indent=2, sort_keys=True) + '\n').encode()

    descriptor, name = tempfile.mkstemp(dir=args.output.parent, suffix='.zip.part')
    os.close(descriptor)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.writestr(args.library.name, data)
            archive.writestr('meta.json', payload(metadata))
            archive.writestr('build-info.json', payload(info))
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None or set(archive.namelist()) != {args.library.name, 'meta.json', 'build-info.json'}:
                raise ValueError('Invalid final ZIP')
            if json.loads(archive.read('meta.json')) != metadata or archive.read(args.library.name) != data:
                raise ValueError('ZIP content mismatch')
        (args.output.parent / 'build-info.json').write_bytes(payload(info))
        args.output.with_suffix('.zip.sha256').write_text(
            hashlib.sha256(temporary.read_bytes()).hexdigest() + '  ' + args.output.name + '\n', encoding='ascii')
        # Hard-link is atomic and refuses to overwrite a concurrently created output.
        os.link(temporary, args.output)
    finally:
        temporary.unlink(missing_ok=True)
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('library', 'version-file', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('commit', 'source-sha256', 'ndk-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--api', type=int, required=True)
    try:
        create_package(parser.parse_args())
    except (OSError, ValueError, struct.error, zipfile.BadZipFile) as error:
        parser.exit(1, f'Packaging failed: {error}\n')


if __name__ == '__main__':
    main()
