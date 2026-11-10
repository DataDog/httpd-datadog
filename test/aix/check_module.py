#!/usr/bin/env python3
"""Check the linked AIX module against native Apache and APR loader exports."""

from pathlib import Path
import struct
import sys


def read_loader(path):
    data = path.read_bytes()
    magic, sections, _, _, optional, _, _ = struct.unpack_from('>HHIQHHI', data)
    assert magic == 0x1f7, 'Expected 64-bit big-endian AIX XCOFF'
    for index in range(sections):
        section = struct.unpack_from('>8sQQQqqqIII4x', data, 24 + optional + 72 * index)
        if section[0].rstrip(b'\0') == b'.loader':
            raw = section[4]
            break
    else:
        raise AssertionError('No XCOFF loader section')
    header = struct.unpack_from('>6I4q', data, raw)
    (_, symbol_count, _, _, import_count, _, import_offset,
     strings_offset, symbols_offset, _) = header
    cursor = raw + import_offset
    imports = []
    for index in range(import_count):
        fields = []
        for _ in range(3):
            end = data.index(b'\0', cursor)
            fields.append(data[cursor:end].decode())
            cursor = end + 1
        imports.append(dict(zip(('path', 'base', 'member'), fields)))
    exports = []
    imported_symbols = []
    for index in range(symbol_count):
        _, offset, _, kind, _, file_id, _ = struct.unpack_from(
            '>QIHBBII', data, raw + symbols_offset + index * 24
        )
        start = raw + strings_offset + offset
        end = data.index(b'\0', start)
        name = data[start:end].decode()
        if kind & 0x10:
            exports.append(name)
        if kind & 0x40:
            imported_symbols.append({'name': name, 'file_id': file_id})
    return {"imports": imports, "exports": set(exports), "symbols": imported_symbols}


def main():
    module_path, sdk = map(Path, sys.argv[1:])
    module = read_loader(module_path)
    required = {"datadog_module", "mod_datadog_version", "mod_datadog_version_string"}
    assert required <= module["exports"], "Missing Apache module exports"
    assert all(symbol["file_id"] for symbol in module["symbols"]), "Unbound loader import"
    allowed = {"/opt/datadog-httpd/lib", "/opt/freeware/lib64", "/usr/lib", "/lib", ""}
    for entry in module["imports"]:
        assert set(entry["path"].split(":")) <= allowed, "Unexpected loader path"
    providers = {
        ".": sdk / "bin/httpd_64",
        "libapr-1.so.0": sdk / "lib/libapr-1.so.0",
        "libaprutil-1.so.0": sdk / "lib/libaprutil-1.so.0",
    }
    for name, path in providers.items():
        needed = {
            symbol["name"] for symbol in module["symbols"]
            if module["imports"][symbol["file_id"]]["base"] == name
        }
        assert needed, f"No imports from {name}"
        missing = needed - read_loader(path)["exports"]
        assert not missing, f"{name}: missing exports {sorted(missing)}"
        print(f"{name}: {len(needed)} imports verified")


if __name__ == "__main__":
    main()
