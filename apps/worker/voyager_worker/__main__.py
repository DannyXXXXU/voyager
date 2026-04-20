"""Worker CLI entrypoint: `python -m voyager_worker`."""
import asyncio

from voyager_worker.main import run

if __name__ == "__main__":
    asyncio.run(run())
