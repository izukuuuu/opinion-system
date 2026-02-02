import sys
import os
import logging
import json

# Setup path to run from root context
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

# Mock settings if needed, or rely on actual
try:
    from src.utils.setting.settings import settings
except ImportError:
    pass

from src.utils.logging.logging import setup_logger
from src.query.data_query import query_database_info, run_query

# PATCH settings
from src.utils.setting.settings import settings
original_get = settings.get
def mock_get(key, default=None):
    if key == 'databases':
        return {"db_url": "postgresql+psycopg2://postgres:w13135365248@101.43.204.229:5432/remote"}
    return original_get(key, default)
settings.get = mock_get

logger = setup_logger("Test", "info")

print("--- Starting Verification of Data Query ---")

try:
    # This will use the config from settings/databases.yaml or similar
    result = query_database_info(logger, include_counts=True) # True to verify table queries
    
    if result:
        print("SUCCESS: Query returned result")
        print(json.dumps(result['summary'], indent=2))
        if result['databases']:
             print(f"Found {len(result['databases'])} databases:")
             for db in result['databases']:
                 print(f" - {db['name']}")
    else:
        print("WARNING: Query returned None (maybe no DB configured or connection failed)")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("--- Verification Complete ---")
