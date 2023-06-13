#!/usr/bin/env python3
import logging
import sys
from time import sleep

from aiohttp import ClientConnectionError, ServerDisconnectedError
from nio import (
    AsyncClient,
    AsyncClientConfig,
    InviteMemberEvent,
    LocalProtocolError,
    LoginError,
    RoomMemberEvent,
    SyncError,
    UnknownEvent,
)

from jose_bot.callbacks import Callbacks
from jose_bot.config import Config

logger = logging.getLogger(__name__)


async def main():
    """The first function that is run when starting the bot"""

    # Read user-configured options from a config file.
    # A different config file path can be specified as the first command line argument
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.yaml"

    # Read the parsed config file and create a Config object
    config = Config(config_path)

    # Configuration options for the AsyncClient
    client_config = AsyncClientConfig(
        max_limit_exceeded=0,
        max_timeouts=0,
        store_sync_tokens=True,
        encryption_enabled=False,
    )

    # Initialize the matrix client
    client = AsyncClient(
        config.homeserver_url,
        config.user_id,
        device_id=config.device_id,
        config=client_config,
    )

    if config.user_token:
        client.access_token = config.user_token
        client.user_id = config.user_id

    # Keep trying to reconnect on failure (with some time in-between)
    while True:
        try:
            if config.user_token:
                # Sync encryption keys with the server
                if client.should_upload_keys:
                    await client.keys_upload()
            else:
                # Try to login with the configured username/password
                try:
                    login_response = await client.login(
                        password=config.user_password,
                        device_name=config.device_name,
                    )

                    # Check if login failed
                    if type(login_response) == LoginError:
                        logger.error("Failed to login: %s", login_response.message)
                        return False
                except LocalProtocolError as e:
                    # There's an edge case here where the user hasn't installed the correct C
                    # dependencies. In that case, a LocalProtocolError is raised on login.
                    logger.fatal(
                        "Failed to login. Have you installed the correct dependencies? "
                        "https://github.com/poljar/matrix-nio#installation "
                        "Error: %s",
                        e,
                    )
                    return False

                # Login succeeded!

            logger.info(f"Logged in as {config.user_id}")

            # Do a initial sync
            resp = await client.sync(timeout=30000, full_state=True)
            while isinstance(resp, SyncError):
                logger.warning("Initial sync failed, retrying in 30s...")
                sleep(30)
                resp = await client.sync(timeout=30000, full_state=True)
            logger.info("Initial sync completed.")
            sync_token = resp.next_batch

            # Set up event callbacks
            callbacks = Callbacks(client, config)
            client.add_event_callback(
                callbacks.invite_event_filtered_callback, (InviteMemberEvent,)
            )
            client.add_event_callback(callbacks.membership, (RoomMemberEvent,))
            client.add_event_callback(callbacks.unknown, (UnknownEvent,))

            await client.sync_forever(timeout=30000, full_state=True, since=sync_token)

        except (ClientConnectionError, ServerDisconnectedError, TimeoutError):
            logger.warning("Unable to connect to homeserver, retrying in 15s...")

            # Sleep so we don't bombard the server with login requests
            sleep(15)
        except Exception:
            logger.exception("An exception was raised.")
            # Sleep so we don't bombard the server with login requests
            sleep(15)
        finally:
            # Make sure to close the client connection on disconnect
            await client.close()
