"""CLI entrypoint for every ingestion adapter.

Usage:
    python -m pipeline.run --source pluto
"""

import argparse
import sys

from pipeline.sources import pluto

ADAPTERS = {"pluto": pluto.main}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a pipeline ingestion adapter.")
    parser.add_argument("--source", required=True, choices=sorted(ADAPTERS))
    args = parser.parse_args()
    return ADAPTERS[args.source]()


if __name__ == "__main__":
    sys.exit(main())
