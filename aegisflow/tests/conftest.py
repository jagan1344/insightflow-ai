"""Make the `aegisflow` package importable when running pytest from aegisflow/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
