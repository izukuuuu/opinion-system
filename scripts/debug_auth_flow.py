from sqlalchemy.engine.url import make_url
import sys

# The URL from config
TEST_URL = "postgresql+psycopg2://postgres:w13135365248@101.43.204.229:5432/remote"

def test_url_transform():
    with open('debug_auth_output.txt', 'w') as f:
        f.write(f"Original: {TEST_URL}\n")
        u = make_url(TEST_URL)
        f.write(f"Parsed Password: {u.password}\n")
        
        # Simulate the logic in data_query.py
        db_name = "remote" 
        
        new_u = u.set(database=db_name)
        new_url_str = str(new_u)
        
        f.write(f"Transformed: {new_url_str}\n")
        
        # Check if password is preserved
        u2 = make_url(new_url_str)
        f.write(f"Reparsed Password: {u2.password}\n")
        
        if u2.password != u.password:
            f.write("FAIL: Password lost during transformation!\n")
        else:
            f.write("SUCCESS: Password preserved.\n")

        # Test actual connection with transformed URL
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(new_url_str)
            with engine.connect() as conn:
                f.write("Connection Successful!\n")
        except Exception as e:
            f.write(f"Connection Failed: {e}\n")

if __name__ == "__main__":
    test_url_transform()
