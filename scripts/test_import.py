
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

print(f"Project root: {PROJECT_ROOT}")

try:
    from backend.src.fluid import fluid_analysis
    print("Import OK")
except Exception as e:
    print(f"Import Failed: {e}")
    import traceback
    traceback.print_exc()
