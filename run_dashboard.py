#!/usr/bin/env python
"""Launch the local paper-trading dashboard.

    python run_dashboard.py [--port 5000] [--debug]

Runs a Flask development server bound to 127.0.0.1 only -- this is a
local, read-only tool and is not meant to be exposed on a network.
"""

from __future__ import annotations

import argparse

from app.config.settings import Settings, get_settings
from app.dashboard.app import create_app
from app.utils.logging_config import configure_logging


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    settings = settings or get_settings()
    configure_logging(settings.logs_dir)

    app = create_app(settings)
    print(f"Dashboard running at http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
