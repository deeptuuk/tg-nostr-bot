"""Re-export shared key_manager."""
import sys
from pathlib import Path
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))
from shared.key_manager import (
    generate_keys, get_keys, get_public_key, get_private_key,
    npub_to_hex, nsec_to_hex, hex_to_npub,
    nip44_encrypt, nip44_decrypt,
    nip17_wrap_message, nip17_unwrap,
    KIND_NIP17_GIFT_WRAP, KIND_NIP17_SEAL, KIND_NIP17_TEXT_MSG,
    sign_event,
)
