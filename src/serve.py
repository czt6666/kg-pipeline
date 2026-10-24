import sys
from pathlib import Path

# Run as `python src/serve.py` (how the server's systemd unit starts it), Python only
# puts src/ on sys.path; the packages live at the repo root, so add it explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.backend_server import main  # noqa: E402

if __name__ == '__main__':
    main()
