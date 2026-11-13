#!/usr/bin/env python3
"""Create APR import files from the native AIX SDK's exported symbols."""

from pathlib import Path
import subprocess
import sys

sdk, compiler = map(Path, sys.argv[1:3])
triple = sys.argv[3] if len(sys.argv) > 3 else "powerpc-ibm-aix7.3.0.0"
nm = compiler / f"compiler/bin/{triple}-nm"
for library, output in (("libapr-1.so.0", "apr.exp"), ("libaprutil-1.so.0", "aprutil.exp")):
    text = subprocess.check_output(
        [str(nm), "--dynamic", "--extern-only", "--defined-only", str(sdk / "lib" / library)],
        text=True,
    )
    symbols = {line.split()[-1] for line in text.splitlines() if line and not line.endswith(":")}
    names = {name for name in symbols if name.startswith("apr_")}
    if not names:
        raise SystemExit(f"No APR exports in {library}")
    entries = names | {"." + name for name in names}
    content = f"#! {library}\n" + "\n".join(sorted(entries)) + "\n"
    path = sdk / output
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
