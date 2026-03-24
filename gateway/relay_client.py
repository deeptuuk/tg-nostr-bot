"""Re-export shared relay_client."""
import sys
from pathlib import Path
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))
from shared.relay_client import RelayClient, NostrEvent
