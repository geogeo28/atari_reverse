"""Put the package root on sys.path so `from stepix... import` works without installation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
