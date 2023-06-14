import logging

from nio import (
    AsyncClient,
    InviteMemberEvent,
    JoinError,
    MatrixRoom,
    PowerLevels,
    RoomGetEventError,
    RoomGetStateEventError,
    RoomMemberEvent,
    RoomPutStateError,
    UnknownEvent,
)

from jose_bot.chat_functions import send_text_to_room
from jose_bot.config import Config
from jose_bot.utils import (
    get_bot_event_type,
    get_user_id_parts,
    hash_user_id,
    is_bot_event,
    user_name,
)

logger = logging.getLogger(__name__)


class Callbacks:
    def __init__(self, client: AsyncClient, config: Config):
        """
        Args:
            client: nio client used to interact with matrix.

            store: Bot storage.

            config: Bot configuration parameters.
        """
        self.client = client
        self.config = config

    async def invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        """Callback for when an invite is received. Join the room specified in the invite.

        Args:
            room: The room that we are invited to.

            event: The invite event.
        """
        logger.debug(f"Got invite to {room.room_id} from {event.sender}.")

        # Attempt to join 3 times before giving up
        for attempt in range(3):
            result = await self.client.join(room.room_id)
            if type(result) == JoinError:
                logger.error(
                    f"Error joining room {room.room_id} (attempt %d): %s",
                    attempt,
                    result.message,
                )
            else:
                break
        else:
            logger.error("Unable to join room: %s", room.room_id)

        # Successfully joined room
        logger.info(f"Joined {room.room_id}")

    async def invite_event_filtered_callback(
        self, room: MatrixRoom, event: InviteMemberEvent
    ) -> None:
        """
        Since the InviteMemberEvent is fired for every m.room.member state received
        in a sync response's `rooms.invite` section, we will receive some that are
        not actually our own invite event (such as the inviter's membership).
        This makes sure we only call `callbacks.invite` with our own invite events.
        """
        if event.state_key == self.client.user_id:
            # This is our own membership (invite) event
            await self.invite(room, event)

    async def _reaction(
        self, room: MatrixRoom, event: UnknownEvent, reacted_to_id: str
    ) -> None:
        """A reaction was sent to one of our messages. Let's send a reply acknowledging it.

        Args:
            room: The room the reaction was sent in.

            event: The reaction event.

            reacted_to_id: The event ID that the reaction points to.
        """
        logger.debug(f"Got reaction to {room.room_id} from {event.sender}.")

        # Get the original event that was reacted to
        event_response = await self.client.room_get_event(room.room_id, reacted_to_id)
        if isinstance(event_response, RoomGetEventError):
            logger.warning(
                "Error getting event that was reacted to (%s)", reacted_to_id
            )
            return
        reacted_to_event = event_response.event
        if (
            is_bot_event(reacted_to_event)
            and get_bot_event_type(reacted_to_event) == "join_confirm"
        ):
            content = reacted_to_event.source.get("content")
            state_key = content.get("io.github.shadowrz.jose_bot", {}).get("state_key")
            required_reaction = hash_user_id(state_key)

            reaction_content = (
                event.source.get("content", {}).get("m.relates_to", {}).get("key")
            )

            if reaction_content == required_reaction:
                state_resp = await self.client.room_get_state_event(
                    room.room_id, "m.room.power_levels"
                )
                if isinstance(state_resp, RoomGetStateEventError):
                    logger.debug(
                        f"Failed to get power level data in room {room.display_name} ({room.room_id}). Stop processing."
                    )
                    return
                content = state_resp.content
                events = content.get("events")
                users = content.get("users")
                del users[state_key]
                await self.client.room_put_state(
                    room.room_id,
                    "m.room.power_levels",
                    {"events": events, "users": users},
                )

    async def unknown(self, room: MatrixRoom, event: UnknownEvent) -> None:
        """Callback for when an event with a type that is unknown to matrix-nio is received.
        Currently this is used for reaction events, which are not yet part of a released
        matrix spec (and are thus unknown to nio).

        Args:
            room: The room the reaction was sent in.

            event: The event itself.
        """
        if event.type == "m.reaction":
            # Get the ID of the event this was a reaction to
            relation_dict = event.source.get("content", {}).get("m.relates_to", {})

            reacted_to = relation_dict.get("event_id")
            if reacted_to and relation_dict.get("rel_type") == "m.annotation":
                await self._reaction(room, event, reacted_to)
                return

        logger.debug(
            f"Got unknown event with type to {event.type} from {event.sender} in {room.room_id}."
        )

    async def membership(self, room: MatrixRoom, event: RoomMemberEvent) -> None:
        if event.membership == "join" and event.prev_membership in (
            None,
            "invite",
            "leave",
        ):
            content = event.content or {}
            name = content.get("displayname")
            logger.info(
                f"New user joined in {room.display_name}: {name} ({event.state_key})"
            )
            _, domain = get_user_id_parts(event.state_key)
            if domain in self.config.allowed_servers:
                logger.info(
                    f"{name} ({event.state_key}) is in allowed servers. Stop processing."
                )
                return
            if self.config.dry_run:
                return
            state_resp = await self.client.room_get_state_event(
                room.room_id, "m.room.power_levels"
            )
            if isinstance(state_resp, RoomGetStateEventError):
                logger.warn(
                    f"Failed to get power level data in room {room.display_name} ({room.room_id}). Stop processing."
                )
                return
            content = state_resp.content
            events = content.get("events")
            events["m.reaction"] = -1
            users = content.get("users")
            powers = PowerLevels(events=events, users=users)
            if not powers.can_user_send_state(self.client.user, "m.room.power_levels"):
                logger.warn(
                    f"Bot is unable to update power levels in {room.display_name} ({room.room_id}). Stop processing."
                )
                return
            users[event.state_key] = -1
            put_state_resp = await self.client.room_put_state(
                room.room_id, "m.room.power_levels", {"events": events, "users": users}
            )
            if isinstance(put_state_resp, RoomPutStateError):
                logger.warn(
                    f"Failed to reconfigure power level: {put_state_resp.message}"
                )
                return
            await send_text_to_room(
                self.client,
                room.room_id,
                f"新加群的用户 {user_name(room, event.state_key)} ({event.state_key}) 请用 Reaction {hash_user_id(event.state_key)} 回复本条消息",
                notice=True,
                extended_data={"type": "join_confirm", "state_key": event.state_key},
            )
