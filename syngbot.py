import asyncio
import re
import operator
from typing import Literal, Optional
from maubot import Plugin, MessageEvent
from maubot.handlers import command

from mautrix.types import ReactionEvent, EventType, TextMessageEventContent
import socketio


class MiniClient:
    def __init__(
        self,
        url: str,
        room: str,
        msg_callback,
        logger,
        maubot_client,
        room_id,
        # performer,
    ) -> None:
        self.url = url
        self.room = room
        self.queue = []
        self.msg_callback = msg_callback
        self.logger = logger
        self.sio = socketio.AsyncClient()
        self.maubot_client = maubot_client
        self.room_id = room_id
        # self.performer = performer
        self.searches = {}
        self.search_events = {}
        self.notifications = {}
        self.last_notofication = None
        self.alertmode: Literal["personal", "room"] = "room"

    #     self.client = socketio.AsyncClient(logger=logger, engineio_logger=logger)
    #     self.register_handlers()
    #
    # def register_handlers(self) -> None:
    #     self.logger.debug("Registering handlers")
    #     self.client.on("state", self.on_state)
    #     self.client.on("connect", self.on_connect)
    #     self.client.on("connect_error", self.on_connect_error)
    #
    # async def on_connect_error(self, data: dict) -> None:
    #     self.logger.debug("on_connect_error")
    #     await self.msg_callback(f"Failed to connect to the server {data} (internal)")
    #
    # async def on_connect(self, data: dict) -> None:
    #     self.logger.debug("on_connect")
    #     await self.client.emit("register-web", {"room": self.room})
    #     await self.msg_callback("Connected to a good room")
    #
    # async def on_state(self, data: dict) -> None:
    #     self.logger.debug("on_state")
    #     self.queue = data["queue"]
    #     if self.old_queue != self.queue:
    #         self.old_queue = self.queue
    #         self.msg_callback(self.queue)

    async def search(self, query: str, evt) -> Optional[str]:
        search_id = await self.sio.call("search", {"query": query})
        self.searches[search_id] = {"query": evt, "results": []}
        return search_id

    async def add_to_queue(
        self, ident: str, source: str, performer: str
    ) -> Optional[str]:
        entry = {"performer": performer, "source": source, "ident": ident}
        entry_id = await self.sio.call("append", entry)
        self.logger.debug(f"Added {entry} to the queue with id {entry_id}")
        return entry_id

    async def connect(self) -> None:
        self.logger.debug("connect")
        await self.msg_callback(f"Connecting to the server {self.url} (internal)")
        # await self.client.connect(self.url)

        @self.sio.event
        async def connect():
            self.logger.debug("Connected to the server")
            await self.msg_callback("Connected to the server!")
            await self.sio.emit("register-web", {"room": self.room})

        @self.sio.event
        async def disconnect():
            self.logger.debug("Disconnected from the server")
            await self.msg_callback("Disconnected from the server")

        @self.sio.on("state")
        async def on_state(data):
            self.logger.debug("on_state")
            self.queue = data["queue"]

            relevant_entries = self.queue[:2]
            relevant_uuids = map(operator.itemgetter("uuid"), relevant_entries)
            mentions = [
                self.notifications[uuid]
                for uuid in relevant_uuids
                if uuid in self.notifications
            ]
            if mentions:
                next_up_str = f"Next up: {relevant_entries[0]['artist']} - {relevant_entries[0]['title']} ({relevant_entries[0]['performer']})"
                if len(relevant_entries) > 1:
                    next_up_str += f"\nAfter that: {relevant_entries[1]['artist']} - {relevant_entries[1]['title']} ({relevant_entries[1]['performer']})"
                event_content = TextMessageEventContent.deserialize(
                    {
                        "body": next_up_str,
                        "m.mentions": {"user_ids": mentions},
                        "msgtype": "m.text",
                    }
                )
                await self.maubot_client.send_message(self.room_id, event_content)

        @self.sio.on("search-results")
        async def on_search_results(data):
            self.logger.debug("on_search_results")
            if "results" not in data:
                await self.msg_callback("No results in response")
                return

            search_id = data["search_id"]
            search_event = self.searches[search_id]["query"]
            self.searches[search_id]["results"] = data["results"]

            text_message = ""

            for i, result in enumerate(data["results"][:5]):
                text_message += f"{EMOJI_NUMBERS[i]}: {result['ident']} ({result['title']}) [{result['source']}]\n\n"

            msg = await search_event.respond(text_message, in_thread=True)
            self.search_events[msg] = search_id
            await asyncio.sleep(0.2)
            await self.maubot_client.react(self.room_id, msg, "1️⃣")
            await asyncio.sleep(0.2)
            await self.maubot_client.react(self.room_id, msg, "2️⃣")
            await asyncio.sleep(0.2)
            await self.maubot_client.react(self.room_id, msg, "3️⃣")
            await asyncio.sleep(0.2)
            await self.maubot_client.react(self.room_id, msg, "4️⃣")
            await asyncio.sleep(0.2)
            await self.maubot_client.react(self.room_id, msg, "5️⃣")

            # msg = await search_event.respond(
            #     f"{result["source"]}: {result["ident"]} ({result["title"]})",
            #     in_thread=True,
            # )
            #
            # await self.maubot_client.react(self.room_id, msg, "➕")
            # self.searches[search_id]["results"].append(result)
            # self.threads[search_event.event_id].append(msg)
            # await asyncio.sleep(0.5)

            # del self.searches[search_id]

        await self.sio.connect(self.url)


EMOJI_REGEX = r"^[\U00000031-\U00000039]\U0000FE0F\U000020E3"
EMOJI_NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


def emoji_to_number(emoji: str) -> int:
    """Helper function to convert the emojis to their index"""
    return EMOJI_NUMBERS.index(emoji)


class SyngBot(Plugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients = {}

    @command.new(name="queue")
    async def queue(self, evt: MessageEvent) -> None:
        room_id = evt.room_id
        if room_id not in self.clients:
            await evt.respond("Not connected to a room")
        else:
            client = self.clients[room_id]
            msg = ""
            for i, entry in enumerate(client.queue):
                msg += (
                    f"{i+1}: {entry['performer']} - {entry['title']} {entry['uuid']}\n"
                )

            await evt.respond(msg)

    @command.passive(
        regex=EMOJI_REGEX,
        field=lambda evt: evt.content.relates_to.key,
        event_type=EventType.REACTION,
        msgtypes=None,
    )
    async def add_to_queue(self, evt: ReactionEvent, _: tuple[str]) -> None:
        client = self.clients[evt.room_id]
        parent_event_id = evt.content.relates_to.event_id
        display_name = await self.client.get_displayname(evt.sender)
        if parent_event_id not in client.search_events:
            self.log.info("Search event not found")
            return

        search_id = client.search_events[parent_event_id]
        parent_event = await self.client.get_event(evt.room_id, parent_event_id)

        selected_result_index = emoji_to_number(evt.content.relates_to.key)
        selected_result = client.searches[search_id]["results"][selected_result_index]
        ident = selected_result["ident"]
        source = selected_result["source"]
        query_event = client.searches[search_id]["query"]
        await query_event.reply(f"Adding {ident} [{source}] to the queue")

        entry_id = await client.add_to_queue(ident, source, display_name)
        client.notifications[entry_id] = evt.sender
        await self.client.redact(parent_event.room_id, parent_event.event_id)
        del client.search_events[parent_event_id]
        del client.searches[search_id]

    @command.new(name="connect")
    @command.argument("url", required=True)
    @command.argument("room", required=True)
    async def connect(self, evt: MessageEvent, url: str, room: str) -> None:
        # user_id = evt.sender
        room_id = evt.room_id
        await evt.respond(f"Connecting to {url} in room {room}")

        if room_id in self.clients:
            await evt.respond("Already connected to a room")
            return
        client = MiniClient(
            url,
            room,
            evt.respond,
            self.log,
            self.client,
            evt.room_id,
            # display_name,
        )
        await client.connect()
        self.clients[room_id] = client

    @command.new(name="search")
    @command.argument("query", pass_raw=True, required=True)
    async def search(self, evt: MessageEvent, query: str) -> None:
        room_id = evt.room_id
        if room_id not in self.clients:
            await evt.respond("Not connected to a room")
            return
        client = self.clients[room_id]
        await client.search(query, evt)

    @command.new(name="disconnect")
    async def disconnect(self, evt: MessageEvent) -> None:
        room_id = evt.room_id
        if room_id not in self.clients:
            await evt.respond("Not connected to a room")
        else:
            del self.clients[room_id]
            await evt.respond("Disconnected from a room")

    @command.new(name="list")
    async def list(self, evt: MessageEvent) -> None:
        await evt.respond("Connected rooms: " + ", ".join(self.clients.keys()))

    async def stop(self):
        for client in self.clients.values():
            await client.sio.disconnect()

    @command.new(name="alertmode")
    @command.argument("mode", required=True)
    async def alertmode(self, evt: MessageEvent, mode: str) -> None:
        room_id = evt.room_id
        if room_id not in self.clients:
            await evt.respond("Not connected to a room")
            return
        client = self.clients[room_id]
        if mode not in ["personal", "room"]:
            await evt.respond("Invalid mode")
            return
        client.alertmode = mode
        await evt.respond(f"Alert mode set to {mode}")
