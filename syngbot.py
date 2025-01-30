from maubot import Plugin, MessageEvent
from maubot.handlers import command
import socketio


class MiniClient:
    def __init__(self, url: str, room: str, msg_callback) -> None:
        self.url = url
        self.room = room
        self.queue = []
        self.old_queue = []
        self.msg_callback = msg_callback

    def register_handlers(self) -> None:
        self.client.on("state", self.on_state)
        self.client.on("connect", self.on_connect)

    async def on_connect(self, data: dict) -> None:
        await self.client.emit("register-web", {"room": self.room})
        await self.msg_callback("Connected to a good room")

    async def on_state(self, data: dict) -> None:
        self.queue = data["queue"]
        if self.old_queue != self.queue:
            self.old_queue = self.queue
            self.msg_callback(self.queue)

    async def connect(self) -> None:
        self.client = socketio.AsyncClient()
        self.register_handlers()
        await self.client.connect(self.url)


class SyngBot(Plugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients = {}

    @command.new(name="queue")
    async def queue(self, evt: MessageEvent) -> None:
        user_id = evt.sender
        if user_id not in self.clients:
            await evt.respond("Not connected to a room")
        else:
            await evt.respond("Queue command not implemented yet")

    @command.new(name="connect")
    @command.argument("url", required=True)
    @command.argument("room", required=True)
    async def connect(self, evt: MessageEvent, url: str, room: str) -> None:
        user_id = evt.sender
        await evt.respond(f"Connecting to {url} in room {room}")

        if user_id in self.clients:
            await evt.respond("Already connected to a room, use disconnect")
        else:
            client = MiniClient(url, room, evt.respond)
            client.connect()
            self.clients[user_id] = client
            await evt.respond("Connected to a room")

    @command.new(name="disconnect")
    async def disconnect(self, evt: MessageEvent) -> None:
        user_id = evt.sender
        if user_id not in self.clients:
            await evt.respond("Not connected to a room")
        else:
            del self.clients[user_id]
            await evt.respond("Disconnected from a room")
