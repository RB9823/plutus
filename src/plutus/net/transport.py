"""Envelope wire format, Transport ABC, and WebSocketTransport."""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable

import anyio
import websockets
import websockets.asyncio.client
import websockets.asyncio.server
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from plutus._util.serialization import pack, unpack

logger = logging.getLogger(__name__)


class MessageType(IntEnum):
    CRDT_UPDATE = 1
    HEARTBEAT = 2
    JOIN = 3
    LEAVE = 4
    SNAPSHOT_REQUEST = 5
    SNAPSHOT_RESPONSE = 6


@dataclass
class Envelope:
    """Wire format wrapping CRDT bytes with routing metadata."""

    msg_type: MessageType
    sender: int
    target: int | None  # None = broadcast
    payload: bytes
    version: int = 1

    def encode(self) -> bytes:
        return pack({
            "v": self.version,
            "t": int(self.msg_type),
            "s": self.sender,
            "r": self.target,
            "p": self.payload,
        })

    @classmethod
    def decode(cls, data: bytes) -> Envelope:
        try:
            d = unpack(data)
        except Exception as exc:
            raise ValueError("invalid envelope encoding") from exc
        if not isinstance(d, dict):
            raise ValueError("invalid envelope payload shape")
        if not {"t", "s", "r", "p"}.issubset(d.keys()):
            raise ValueError("envelope missing required fields")
        if not isinstance(d["s"], int):
            raise ValueError("envelope sender must be an int")
        if d["r"] is not None and not isinstance(d["r"], int):
            raise ValueError("envelope target must be None or int")
        if not isinstance(d["p"], (bytes, bytearray)):
            raise ValueError("envelope payload must be bytes")
        version = d.get("v", 1)
        if not isinstance(version, int) or version < 1:
            raise ValueError("envelope version must be a positive int")

        try:
            msg_type = MessageType(d["t"])
        except Exception as exc:
            raise ValueError("invalid message type in envelope") from exc

        return cls(
            version=version,
            msg_type=msg_type,
            sender=d["s"],
            target=d["r"],
            payload=bytes(d["p"]),
        )


class Transport(abc.ABC):
    """Abstract base class for network transports."""

    @abc.abstractmethod
    async def send(self, envelope: Envelope) -> None: ...

    @abc.abstractmethod
    async def receive(self) -> Envelope: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    @property
    @abc.abstractmethod
    def is_connected(self) -> bool: ...


class WebSocketTransport(Transport):
    """WebSocket-based transport for client connections."""

    def __init__(
        self,
        ws: Any,
        uri: str,
        *,
        connect_kwargs: dict[str, Any] | None = None,
        retries: int = 3,
        backoff_base: float = 0.2,
        backoff_max: float = 5.0,
    ) -> None:
        self._ws = ws
        self._uri = uri
        self._connect_kwargs = connect_kwargs or {}
        self._retries = retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._closed = False

    @staticmethod
    async def _connect_with_retry(
        uri: str,
        *,
        connect_kwargs: dict[str, Any],
        retries: int,
        backoff_base: float,
        backoff_max: float,
    ) -> Any:
        attempt = 0
        while True:
            try:
                return await websockets.asyncio.client.connect(uri, **connect_kwargs)
            except Exception:
                if attempt >= retries:
                    raise
                delay = min(backoff_base * (2**attempt), backoff_max)
                logger.warning(
                    "websocket connect failed (attempt=%s/%s); retrying in %.2fs",
                    attempt + 1,
                    retries + 1,
                    delay,
                )
                await anyio.sleep(delay)
                attempt += 1

    @classmethod
    async def connect(
        cls,
        uri: str,
        *,
        retries: int = 3,
        backoff_base: float = 0.2,
        backoff_max: float = 5.0,
        token: str | None = None,
        peer_id: int | None = None,
        max_size: int | None = 10 * 1024 * 1024,
    ) -> WebSocketTransport:
        headers: dict[str, str] = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        if peer_id is not None:
            headers["X-Plutus-Peer-Id"] = str(peer_id)
        connect_kwargs: dict[str, Any] = {
            "max_size": max_size,
        }
        if headers:
            connect_kwargs["additional_headers"] = headers
        ws = await cls._connect_with_retry(
            uri,
            connect_kwargs=connect_kwargs,
            retries=retries,
            backoff_base=backoff_base,
            backoff_max=backoff_max,
        )
        return cls(
            ws,
            uri=uri,
            connect_kwargs=connect_kwargs,
            retries=retries,
            backoff_base=backoff_base,
            backoff_max=backoff_max,
        )

    async def reconnect(self) -> None:
        """Reconnect this transport using the original connection settings."""
        try:
            await self.close()
        except Exception:
            pass
        self._ws = await self._connect_with_retry(
            self._uri,
            connect_kwargs=self._connect_kwargs,
            retries=self._retries,
            backoff_base=self._backoff_base,
            backoff_max=self._backoff_max,
        )
        self._closed = False

    @property
    def is_connected(self) -> bool:
        if self._closed:
            return False
        if hasattr(self._ws, "closed"):
            return not bool(self._ws.closed)
        return True

    async def send(self, envelope: Envelope) -> None:
        if self._closed:
            raise RuntimeError("cannot send on closed websocket transport")
        try:
            await self._ws.send(envelope.encode())
        except websockets.exceptions.ConnectionClosed as exc:
            self._closed = True
            raise ConnectionError("websocket send failed; connection closed") from exc

    async def receive(self) -> Envelope:
        if self._closed:
            raise RuntimeError("cannot receive on closed websocket transport")
        try:
            data = await self._ws.recv()
        except websockets.exceptions.ConnectionClosed as exc:
            self._closed = True
            raise ConnectionError("websocket receive failed; connection closed") from exc
        return Envelope.decode(bytes(data))

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._ws.close()


class WebSocketServer:
    """WebSocket server that accepts connections and broadcasts envelopes."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        *,
        auth_token: str | None = None,
        max_size: int | None = 10 * 1024 * 1024,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.max_size = max_size
        self._clients: dict[int, Any] = {}  # peer_id -> websocket
        self._clients_lock = anyio.Lock()
        self._on_message: Callable[[Envelope], Any] | None = None
        self._server: Any = None

    def on_message(self, callback: Callable[[Envelope], Any]) -> None:
        self._on_message = callback

    async def _process_request(self, connection: Any, request: Request) -> Response | None:
        if self.auth_token is None:
            return None

        expected_auth = f"Bearer {self.auth_token}"
        provided_auth = request.headers.get("Authorization")
        if provided_auth != expected_auth:
            return Response(
                401,
                "Unauthorized",
                Headers(),
                b"missing or invalid authorization token",
            )

        peer_header = request.headers.get("X-Plutus-Peer-Id")
        try:
            peer_id = int(peer_header) if peer_header is not None else None
        except ValueError:
            return Response(
                400,
                "Bad Request",
                Headers(),
                b"X-Plutus-Peer-Id must be an integer",
            )
        if peer_id is None:
            return Response(
                400,
                "Bad Request",
                Headers(),
                b"X-Plutus-Peer-Id is required when auth is enabled",
            )
        setattr(connection, "_plutus_authenticated_peer_id", peer_id)
        return None

    async def _handler(self, websocket: Any) -> None:
        peer_id: int | None = None
        authenticated_peer_id: int | None = getattr(websocket, "_plutus_authenticated_peer_id", None)
        try:
            async for message in websocket:
                try:
                    envelope = Envelope.decode(bytes(message))
                except ValueError:
                    logger.warning("dropping malformed envelope from client")
                    continue
                if authenticated_peer_id is not None and envelope.sender != authenticated_peer_id:
                    logger.warning(
                        "dropping envelope with sender=%s for authenticated peer=%s",
                        envelope.sender,
                        authenticated_peer_id,
                    )
                    continue
                if envelope.msg_type == MessageType.JOIN:
                    peer_id = envelope.sender
                    async with self._clients_lock:
                        self._clients[peer_id] = websocket
                if self._on_message:
                    self._on_message(envelope)
                # Broadcast to other clients
                async with self._clients_lock:
                    recipients = [(cid, ws) for cid, ws in self._clients.items() if cid != envelope.sender]
                stale_clients: list[int] = []
                for cid, ws in recipients:
                    if cid != envelope.sender:
                        try:
                            await ws.send(bytes(message))
                        except Exception:
                            stale_clients.append(cid)
                if stale_clients:
                    async with self._clients_lock:
                        for cid in stale_clients:
                            self._clients.pop(cid, None)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if peer_id is not None:
                async with self._clients_lock:
                    self._clients.pop(peer_id, None)

    async def start(self) -> None:
        self._server = await websockets.asyncio.server.serve(
            self._handler,
            self.host,
            self.port,
            process_request=self._process_request,
            max_size=self.max_size,
        )

    async def stop(self) -> None:
        async with self._clients_lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for ws in clients:
            try:
                await ws.close()
            except Exception:
                logger.debug("error while closing websocket client", exc_info=True)
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    @property
    def client_count(self) -> int:
        return len(self._clients)
