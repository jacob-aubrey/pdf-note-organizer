"""Audit only: reuse extracted plugin dependencies after the real stdlib/site-packages."""
from pathlib import Path
import sys

repository = Path(__file__).resolve().parents[4]
dependencies = repository / '.test-tmp' / 'scheduled-repair-20261024' / 'runtime-dependencies'
if dependencies.is_dir():
    sys.path.append(str(dependencies))
