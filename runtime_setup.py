"""Process-local discovery of the active environment's bundled Arrow runtime."""
import os
from pathlib import Path
import sys

_DLL_HANDLES = []


def configure_runtime():
    """Keep bundled DLLs discoverable on Windows; change no environment files."""
    if os.name != 'nt' or _DLL_HANDLES:
        return
    prefix = Path(sys.prefix)
    # BLAS delay-loads native libraries through PATH even after Python's DLL
    # directories are registered. Keep this scoped to the current process.
    native = prefix / 'Library' / 'bin'
    if native.is_dir():
        os.environ['PATH'] = str(native) + os.pathsep + os.environ.get('PATH', '')
    for folder in (prefix / 'Library' / 'bin', prefix / 'Lib' / 'site-packages' / 'pyarrow.libs'):
        if folder.is_dir():
            _DLL_HANDLES.append(os.add_dll_directory(str(folder)))
