from dotenv import load_dotenv
import os
from pathlib import Path

path = Path(".env")
print(f"Checking .env at: {path.absolute()}")
print(f"Exists: {path.exists()}")

if path.exists():
    print("Loading...")
    load_dotenv(path) # Override=True by default? No. Let's try override=True
    # load_dotenv(path, override=True)

    token = os.getenv("OANDA_API_TOKEN")
    account = os.getenv("OANDA_ACCOUNT_ID")
    env = os.getenv("OANDA_ENV")

    print(f"OANDA_API_TOKEN Found: {token is not None}")
    if token:
        print(f"Token Length: {len(token)}")
        print(f"Token Start: {token[:4]}***")

    print(f"OANDA_ACCOUNT_ID Found: {account is not None}")
    print(f"OANDA_ENV Found: {env is not None}")
    print(f"OANDA_ENV content: {env}")
else:
    print("File missing.")
