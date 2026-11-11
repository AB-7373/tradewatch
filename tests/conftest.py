"""Shared test setup: lets tests `import signals`, `import trades`, etc. from the project root."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
