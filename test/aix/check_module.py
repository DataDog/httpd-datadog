#!/usr/bin/env python3
"""Check the linked AIX module against native Apache and APR loader exports."""

from pathlib import Path
import struct
import sys


def read_loader(path):
    data = path.read_bytes()
    magic, sections, _, _, optional, _, _ = struct.unpack_from('>HHIQHHI', data)
    assert magic == 0x1f7, 'Expected 64-bit big-endian AIX XCOFF'
    section_names = set()
    raw = None
    for index in range(sections):
        section = struct.unpack_from('>8sQQQqqqIII4x', data, 24 + optional + 72 * index)
        name = section[0].rstrip(b'\0').decode()
        section_names.add(name)
        if name == '.loader':
            raw = section[4]
    assert raw is not None, 'No XCOFF loader section'
    header = struct.unpack_from('>6I4q', data, raw)
    (_, symbol_count, relocation_count, _, import_count, _, import_offset,
     strings_offset, symbols_offset, relocations_offset) = header
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
    storage_classes = []
    for index in range(symbol_count):
        _, offset, _, kind, storage, file_id, _ = struct.unpack_from(
            '>QIHBBII', data, raw + symbols_offset + index * 24
        )
        storage_classes.append(storage)
        start = raw + strings_offset + offset
        end = data.index(b'\0', start)
        name = data[start:end].decode()
        if kind & 0x10:
            exports.append(name)
        if kind & 0x40:
            imported_symbols.append({'name': name, 'file_id': file_id})
    relocations = [
        struct.unpack_from('>QHHi', data, raw + relocations_offset + index * 16)
        for index in range(relocation_count)
    ]
    return {"imports": imports, "exports": set(exports), "symbols": imported_symbols,
            "sections": section_names, "storage_classes": storage_classes,
            "relocations": relocations}


def check_tls(module):
    for address, kind, _, symbol in module["relocations"]:
        if not 0x20 <= kind & 0xff <= 0x25:
            continue
        message = f"Invalid TLS loader relocation at {address:#x}"
        if symbol in (-1, -2):
            section = ".tdata" if symbol == -1 else ".tbss"
            assert section in module["sections"], message
        else:
            assert 3 <= symbol < len(module["storage_classes"]) + 3, message
            assert module["storage_classes"][symbol - 3] in (20, 21), message


def main():
    module_path, sdk = map(Path, sys.argv[1:])
    module = read_loader(module_path)
    check_tls(module)
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
