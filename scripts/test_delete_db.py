import sys
import os

# Add backend directory to path
backend_path = os.path.join(os.getcwd(), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

try:
    from src.utils.io.db import DatabaseManager
except ImportError:
    # If explicit src import fails, maybe structure is different
    # Try adding project root
    sys.path.insert(0, os.getcwd())
    from backend.src.utils.io.db import DatabaseManager
from sqlalchemy import create_engine, text

def test_delete():
    manager = DatabaseManager()
    db_name = "test_delete_db"
    
    print(f"Creating dummy database: {db_name}")
    try:
        manager.ensure_database(db_name)
    except Exception as e:
        print(f"Creation failed: {e}")
        
    print(f"Attempting to delete database: {db_name}")
    
    # Simulate an active connection to it
    from sqlalchemy.engine.url import make_url
    base_url = make_url(manager.db_url)
    target_url = base_url.set(database=db_name)
    print(f"Blocking connection to: {target_url}")
    
    # Create engine and connect. Keep connection open.
    blocking_engine = create_engine(target_url)
    blocking_conn = blocking_engine.connect()
    print("Maintained blocking connection.")
    
    # Try to delete
    try:
        success = manager.drop_database(db_name)
        if success:
            print("Delete SUCCESS (Blocking connection was killed!)")
        else:
            print("Delete FAILED (Blocking connection prevented drop)")
    finally:
        blocking_conn.close()
        blocking_engine.dispose()

if __name__ == "__main__":
    test_delete()
