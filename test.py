"""Run isolated regressions without unrelated global pytest plugins."""
import os
from pathlib import Path
import sys

from runtime_setup import configure_runtime

if __name__ == '__main__':
    configure_runtime()
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    os.environ['LLM_ENABLED'] = 'no'
    os.chdir(Path(__file__).resolve().parent)
    try:
        import pytest
    except ImportError:
        print('pytest is missing. Review README.md; nothing was installed.')
        raise SystemExit(2)
    raise SystemExit(pytest.main(['tests', '-q', '-p', 'no:cacheprovider', *sys.argv[1:]]))
