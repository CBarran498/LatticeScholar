from __future__ import annotations

import argparse
import multiprocessing
import threading
import webbrowser

import uvicorn

from .config import settings


def main() -> None:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Run the LatticeScholar local research workspace")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically")
    args = parser.parse_args()
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
    from .main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

