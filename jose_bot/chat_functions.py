import logging
from typing import Any, Dict, Optional, Union

from nio import AsyncClient, ErrorResponse, RoomSendResponse, SendRetryError

logger = logging.getLogger(__name__)


async def send_text_to_room(
    client: AsyncClient,
    room_id: str,
    message: str,
    notice: bool = True,
    reply_to_event_id: Optional[str] = None,
    extended_data: Optional[Dict[Any, Any]] = None,
) -> Union[RoomSendResponse, ErrorResponse]:
    """Send text to a matrix room.

    Args:
        client: The client to communicate to matrix with.

        room_id: The ID of the room to send the message to.

        message: The message content.

        notice: Whether the message should be sent with an "m.notice" message type
            (will not ping users).

        markdown_convert: Whether to convert the message content to markdown.
            Defaults to true.

        reply_to_event_id: Whether this message is a reply to another event. The event
            ID this is message is a reply to.

    Returns:
        A RoomSendResponse if the request was successful, else an ErrorResponse.
    """
    # Determine whether to ping room members or not
    msgtype = "m.notice" if notice else "m.text"

    content = {
        "msgtype": msgtype,
        "body": message,
    }

    if reply_to_event_id:
        content["m.relates_to"] = {"m.in_reply_to": {"event_id": reply_to_event_id}}

    # Add custom data for tracking bot message.
    content["io.github.shadowrz.jose_bot"] = extended_data or {}
    content["io.github.shadowrz.jose_bot"]["in_reply_to"] = reply_to_event_id
    if not content["io.github.shadowrz.jose_bot"].get("type"):
        content["io.github.shadowrz.jose_bot"]["type"] = "text"

    try:
        return await client.room_send(
            room_id,
            "m.room.message",
            content,
            ignore_unverified_devices=True,
        )
    except SendRetryError:
        logger.exception(f"Unable to send message response to {room_id}")
