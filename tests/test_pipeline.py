"""Offline regressions for failures that previously produced false success."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load('package_driver')
extractor = load('extract_archive')


def elf(align=16384, machine=183, soname='vulkan.freedreno.so', needed='libc.so'):
    # Independent minimal ELF64 fixture: two program headers, one string table.
    data = bytearray(1024)
    data[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH', data, 16, 3, machine, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0, 0, 0, len(data), len(data), align)
    struct.pack_into('<IIQQQQQQ', data, 120, 2, 4, 256, 256, 0, 80, 80, 8)
    strings = b'\0' + soname.encode() + b'\0' + needed.encode() + b'\0'
    data[512:512 + len(strings)] = strings
    for i, pair in enumerate([(5, 512), (10, len(strings)), (14, 1), (1, len(soname) + 2), (0, 0)]):
        struct.pack_into('<qQ', data, 256 + i * 16, *pair)
    return bytes(data)


class PipelineTests(unittest.TestCase):
    def test_valid_elf(self):
        self.assertEqual(pack.validate_elf(elf(), 'vulkan.freedreno.so'), ['libc.so'])

    def test_invalid_elf_variants(self):
        cases = [b'not ELF', elf(machine=62), elf(align=4096),
                 elf(soname='wrong.so'), elf(needed='libc++_shared.so'), elf()[:600]]
        for data in cases:
            with self.subTest(data=data[:24]), self.assertRaises(ValueError):
                pack.validate_elf(data, 'vulkan.freedreno.so')

    def test_dynamic_bounds(self):
        data = bytearray(elf())
        struct.pack_into('<Q', data, 256 + 2 * 16 + 8, 999999)
        with self.assertRaises(ValueError):
            pack.validate_elf(data, 'vulkan.freedreno.so')

    def test_package_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            library = root / 'vulkan.freedreno.so'
            library.write_bytes(elf())
            version = root / 'VERSION'
            version.write_text('26.3.0-devel\n')
            args = argparse.Namespace(library=library, version_file=version, output=root/'driver.zip',
                                      commit='a'*40, source_sha256='b'*64, ndk_sha256='c'*64, api=34)
            info = pack.create_package(args)
            self.assertFalse(info['runtimeTested'])
            with zipfile.ZipFile(args.output) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(json.loads(z.read('meta.json'))['driverVersion'], '26.3.0-devel')
                self.assertEqual(z.read(library.name), elf())
            old = args.output.read_bytes()
            with self.assertRaises(ValueError):
                pack.create_package(args)
            self.assertEqual(old, args.output.read_bytes())

    def test_failed_validation_creates_no_zip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lib = root / 'bad.so'; lib.write_bytes(b'old invalid library')
            args = argparse.Namespace(library=lib, output=root/'driver.zip')
            with self.assertRaises(ValueError):
                pack.create_package(args)
            self.assertFalse(args.output.exists())

    def bash(self, body, *args):
        return subprocess.run(['bash', '-c', 'source "$1"; ' + body, 'test', str(ROOT/'turnip_builder.sh'), *args],
                              text=True, capture_output=True)

    def test_failed_meson_stops_before_ninja(self):
        with tempfile.TemporaryDirectory() as td:
            p = self.bash('RUN_DIR="$2"; SOURCE="$2"; meson(){ return 23; }; ninja(){ echo WRONG_NINJA; }; build; echo WRONG_SUCCESS', td)
            self.assertEqual(p.returncode, 23)
            self.assertNotIn('WRONG_', p.stdout)
            self.assertIn('Build failed', p.stderr)

    def test_failed_ninja_is_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            p = self.bash('RUN_DIR="$2"; SOURCE="$2"; meson(){ :; }; ninja(){ return 24; }; build; echo WRONG_SUCCESS', td)
            self.assertEqual(p.returncode, 24)
            self.assertNotIn('WRONG_SUCCESS', p.stdout)

    def test_old_zip_cannot_hide_missing_library(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root/'turnip_a660_final_adrenotools.zip').write_bytes(b'old ZIP')
            p = self.bash('RUN_DIR="$2"; NDK="$2"; package; echo WRONG_SUCCESS', td)
            self.assertNotEqual(p.returncode, 0)
            self.assertNotIn('checks passed', p.stdout)
            self.assertNotIn('WRONG_SUCCESS', p.stdout)

    def test_download_failure_is_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            p = self.bash('curl(){ return 22; }; download https://example.invalid "$2/file" bad; echo WRONG_SUCCESS', td)
            self.assertEqual(p.returncode, 22)
            self.assertNotIn('WRONG_SUCCESS', p.stdout)
            self.assertFalse((Path(td)/'file').exists())

    def test_bad_checksum_is_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            p = self.bash('curl(){ printf wrong > "${@: -1}"; }; download ignored "$2/file" '+ '0'*64 + '; echo WRONG_SUCCESS', td)
            self.assertNotEqual(p.returncode, 0)
            self.assertNotIn('WRONG_SUCCESS', p.stdout)
            self.assertEqual((Path(td)/'file.part').read_text(), 'wrong')
            self.assertFalse((Path(td)/'file').exists())

    def test_extra_cli_argument_rejected(self):
        p = subprocess.run(['bash', str(ROOT/'turnip_builder.sh'), '--help', 'extra'], capture_output=True)
        self.assertNotEqual(p.returncode, 0)

    def test_extraction_modes_links_and_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); archive = root/'tools.zip'; dest=root/'out'
            with zipfile.ZipFile(archive, 'w') as z:
                info = zipfile.ZipInfo('tool'); info.external_attr=(stat.S_IFREG | 0o755) << 16
                z.writestr(info, b'#!/bin/sh\nexit 0\n')
                info = zipfile.ZipInfo('alias'); info.external_attr=(stat.S_IFLNK | 0o777) << 16
                z.writestr(info, 'tool')
            extractor.extract(archive, dest)
            self.assertTrue(os.access(dest/'tool', os.X_OK))
            self.assertTrue((dest/'alias').is_symlink())
            self.assertEqual((dest/'alias').read_bytes(), (dest/'tool').read_bytes())
            with zipfile.ZipFile(root/'bad.zip', 'w') as z:
                z.writestr('../escape', 'bad')
            with self.assertRaises(ValueError):
                extractor.extract(root/'bad.zip', root/'other')
            self.assertFalse((root/'escape').exists())


if __name__ == '__main__':
    unittest.main()
