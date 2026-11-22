"""Local-only entrypoint; no broker execution functionality."""
from hyperpass.server import main
import sys

if __name__ == '__main__':
    sys.exit(main())
