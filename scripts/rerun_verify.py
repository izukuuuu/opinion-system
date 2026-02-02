import sys
import os
try:
    from scripts.verify_db_query import *
except ImportError:
    # Re-run the existing script logic if import fails
    os.system("uv run python scripts/verify_db_query.py")
