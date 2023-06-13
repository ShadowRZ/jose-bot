from typing import Optional

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
