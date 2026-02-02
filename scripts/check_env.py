import os
import sys

# Add backend to path to use settings logic if needed, but os.environ is global
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

print("--- Environment Variables Check ---")
for key, value in os.environ.items():
    if "DB_URL" in key or "OPINION_" in key:
        print(f"{key}: {value}")

try:
    from src.utils.setting.settings import settings
    print(f"Settings env.DB_URL: {settings.get('env.DB_URL')}")
except Exception as e:
    print(f"Could not load settings: {e}")

print("--- End Check ---")
