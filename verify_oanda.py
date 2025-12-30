import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path.cwd()))

from src.core.logger import setup_logging, logging
from src.modules.market.providers.oanda import OANDAProvider
from src.core.config import config

def verify_oanda():
    setup_logging()
    logger = logging.getLogger("verify_oanda")
    logger.info("Starting OANDA Verification...")
    
    # 1. Check Config
    logger.info(f"Source: {config.data.get('source')}")
    logger.info(f"Env: {config.data.get('oanda', {}).get('environment')}")
    
    # 2. Init Provider
    try:
        provider = OANDAProvider()
        logger.info("Provider Initialized.")
    except Exception as e:
        logger.critical(f"Failed to init provider: {e}")
        return
        
    # 3. Fetch Spread
    try:
        spread = provider.fetch_spread("EUR/USD")
        logger.info(f"Current Spread: {spread:.5f}")
    except Exception as e:
        logger.error(f"Spread Fetch Failed: {e}")
        
    # 4. Fetch Candles
    try:
        candles = provider.fetch_candles("EUR/USD", "H4", 5)
        logger.info(f"Fetched {len(candles)} candles.")
        if candles:
            logger.info(f"Last Candle: {candles[-1]}")
    except Exception as e:
        logger.error(f"Candle Fetch Failed: {e}")
        
    logger.info("Verification Done.")

if __name__ == "__main__":
    verify_oanda()
