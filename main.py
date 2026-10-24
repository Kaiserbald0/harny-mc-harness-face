from dotenv import load_dotenv
from harness.loop import run_loop
import logging
import os


def main():
    load_dotenv()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    run_loop()

if __name__ == "__main__":
    main()
