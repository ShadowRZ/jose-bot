import re
from typing import Optional, Tuple

import xxhash
from nio import Event, MatrixRoom

REACTIONS = ["🎉", "🤣", "😃", "😋", "🥳", "🤔", "😅"]


def hash_user_id(user_id: str):
    hash = xxhash.xxh64_intdigest(user_id)
    return REACTIONS[hash % len(REACTIONS)]


def get_bot_event_type(event: Event) -> Optional[str]:
    if is_bot_event(event):
        content = event.source.get("content")
        type = content.get("io.github.shadowrz.jose_bot", {}).get("type")
        return type
    else:
        return None


def is_bot_event(event: Event) -> bool:
    content = event.source.get("content")
    return "io.github.shadowrz.jose_bot" in content


def user_name(room: MatrixRoom, user_id: str) -> Optional[str]:
    """Get display name for a user."""
    if user_id not in room.users:
        return None
    user = room.users[user_id]
    return user.name


# A structure for a Matrix UID. It also supports legacy UID formats.
# First part: [\!-9\;-\~]+
# Matches legacy UIDs too.
# Second part:
# // IPv4 Address: [0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}
# // IPv6 Address: \[[0-9A-Fa-f:.]{2,45}\]
# // DNS name: [-.0-9A-Za-z]{1,255}
# // Port: [0-9]{1,5}
# // Hostname: [0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}|\[[0-9A-Fa-f:.]{2,45}\]|[-.0-9A-Za-z]{1,255}(?::[0-9]{1,5})?
MATRIX_UID_RE = r"@([\!-9\;-\~]+):([0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}|\[[0-9A-Fa-f:.]{2,45}\]|[-.0-9A-Za-z]{1,255}(?::[0-9]{1,5})?)"


def get_user_id_parts(user_id: str) -> Tuple[str, str]:
    uid, domain = re.match(MATRIX_UID_RE, user_id).groups()
    return (uid, domain)
