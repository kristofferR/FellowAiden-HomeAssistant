"""Minimal Android FCM receiver used for Fellow cloud invalidations.

Fellow's mobile app registers a Firebase token with the Fellow API and receives
data messages over Google's Mobile Connection Server (MCS). This module
implements only that narrow Android transport: device check-in, app-token
registration, login, heartbeat handling, and stream acknowledgements.
"""

from __future__ import annotations

import asyncio
import inspect
import ssl
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs

import aiohttp

if TYPE_CHECKING:
    from asyncio import StreamReader, StreamWriter

CHECKIN_URL = "https://android.clients.google.com/checkin"
REGISTER_URL = "https://android.clients.google.com/c2dm/register3"
MCS_HOST = "mtalk.google.com"
MCS_PORT = 5228
MCS_VERSION = 41

FELLOW_PACKAGE = "com.fellowproducts.Fellow"
FELLOW_SENDER_ID = "235776765112"
FELLOW_APP_ID = "1:235776765112:android:36ec4d6d84197b8bb9584d"
FELLOW_CERT_SHA1 = "72af2c32c541ff241422dba026f3878723734664"
FELLOW_APP_VERSION_CODE = "52"
FELLOW_APP_VERSION_NAME = "1.4.5"

_MCS_HEARTBEAT_PING = 0
_MCS_HEARTBEAT_ACK = 1
_MCS_LOGIN_REQUEST = 2
_MCS_LOGIN_RESPONSE = 3
_MCS_CLOSE = 4
_MCS_IQ_STANZA = 7
_MCS_DATA_MESSAGE = 8
_MCS_STREAM_ERROR = 10

_HEARTBEAT_INTERVAL_SECONDS = 300
_HEARTBEAT_ACK_TIMEOUT_SECONDS = 90
_LOGIN_TIMEOUT_SECONDS = 30
_HTTP_TIMEOUT_SECONDS = 30
_MAX_FRAME_SIZE = 1024 * 1024
_MAX_PERSISTENT_IDS = 100


class FcmError(Exception):
    """Base exception for the FCM receiver."""


class FcmRegistrationError(FcmError):
    """Raised when Google rejects check-in or app registration."""


class FcmConnectionError(FcmError):
    """Raised when the long-lived MCS connection fails."""


class FcmProtocolError(FcmError):
    """Raised for malformed or unexpected MCS data."""


@dataclass(slots=True, repr=False)
class FcmCredentials:
    """Credentials needed to reconnect to Android cloud messaging."""

    android_id: int
    security_token: int
    fcm_token: str
    persistent_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: object) -> FcmCredentials | None:
        """Load validated credentials from Home Assistant storage."""
        if not isinstance(data, Mapping):
            return None
        android_id = data.get("android_id")
        security_token = data.get("security_token")
        fcm_token = data.get("fcm_token")
        persistent_ids = data.get("persistent_ids", [])
        if (
            isinstance(android_id, bool)
            or not isinstance(android_id, int)
            or android_id <= 0
            or isinstance(security_token, bool)
            or not isinstance(security_token, int)
            or security_token <= 0
            or not isinstance(fcm_token, str)
            or not fcm_token
            or not isinstance(persistent_ids, list)
            or not all(isinstance(value, str) for value in persistent_ids)
        ):
            return None
        return cls(
            android_id=android_id,
            security_token=security_token,
            fcm_token=fcm_token,
            persistent_ids=persistent_ids[-_MAX_PERSISTENT_IDS:],
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize credentials for private Home Assistant storage."""
        return {
            "android_id": self.android_id,
            "security_token": self.security_token,
            "fcm_token": self.fcm_token,
            "persistent_ids": self.persistent_ids[-_MAX_PERSISTENT_IDS:],
        }


@dataclass(frozen=True, slots=True)
class FcmMessage:
    """Useful, non-credential fields from an Android data message."""

    category: str | None
    data: dict[str, str]
    persistent_id: str | None


ConnectionCallback = Callable[[bool], Awaitable[None] | None]
MessageCallback = Callable[[FcmMessage], Awaitable[None] | None]


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("Varints must be non-negative")
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise FcmProtocolError("Truncated protobuf varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
    raise FcmProtocolError("Protobuf varint is too long")


def _field_varint(number: int, value: int) -> bytes:
    return _encode_varint(number << 3) + _encode_varint(value)


def _field_fixed64(number: int, value: int) -> bytes:
    return _encode_varint((number << 3) | 1) + value.to_bytes(8, "little")


def _field_bytes(number: int, value: str | bytes) -> bytes:
    raw = value.encode() if isinstance(value, str) else value
    return _encode_varint((number << 3) | 2) + _encode_varint(len(raw)) + raw


def _parse_fields(data: bytes) -> list[tuple[int, int, int | bytes]]:
    fields: list[tuple[int, int, int | bytes]] = []
    offset = 0
    while offset < len(data):
        key, offset = _decode_varint(data, offset)
        number = key >> 3
        wire_type = key & 7
        if number == 0:
            raise FcmProtocolError("Invalid protobuf field number")
        if wire_type == 0:
            value, offset = _decode_varint(data, offset)
        elif wire_type == 1:
            end = offset + 8
            if end > len(data):
                raise FcmProtocolError("Truncated fixed64 field")
            value = int.from_bytes(data[offset:end], "little")
            offset = end
        elif wire_type == 2:
            length, offset = _decode_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise FcmProtocolError("Truncated length-delimited field")
            value = data[offset:end]
            offset = end
        elif wire_type == 5:
            end = offset + 4
            if end > len(data):
                raise FcmProtocolError("Truncated fixed32 field")
            value = int.from_bytes(data[offset:end], "little")
            offset = end
        else:
            raise FcmProtocolError(f"Unsupported protobuf wire type: {wire_type}")
        fields.append((number, wire_type, value))
    return fields


def _first_int(fields: list[tuple[int, int, int | bytes]], number: int) -> int | None:
    for field_number, _wire_type, value in fields:
        if field_number == number and isinstance(value, int):
            return value
    return None


def _first_bytes(
    fields: list[tuple[int, int, int | bytes]], number: int
) -> bytes | None:
    for field_number, _wire_type, value in fields:
        if field_number == number and isinstance(value, bytes):
            return value
    return None


def _text(value: bytes | None) -> str | None:
    if value is None:
        return None
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as err:
        raise FcmProtocolError("Invalid UTF-8 in MCS message") from err


def _build_checkin_request(existing: FcmCredentials | None) -> bytes:
    chrome_build = b"".join(
        (
            _field_varint(1, 3),
            _field_bytes(2, "63.0.3234.0"),
            _field_varint(3, 1),
        )
    )
    checkin = _field_varint(12, 3) + _field_bytes(13, chrome_build)
    request = _field_varint(2, existing.android_id if existing else 0)
    request += _field_bytes(4, checkin)
    if existing:
        request += _field_fixed64(13, existing.security_token)
    request += _field_varint(14, 3)
    return request


def _parse_checkin_response(data: bytes) -> tuple[int, int]:
    fields = _parse_fields(data)
    android_id = _first_int(fields, 7)
    security_token = _first_int(fields, 8)
    if not android_id or not security_token:
        raise FcmRegistrationError("Google check-in response omitted credentials")
    return android_id, security_token


def _build_login_request(credentials: FcmCredentials) -> bytes:
    setting = _field_bytes(1, "new_vc") + _field_bytes(2, "1")
    payload = b"".join(
        (
            _field_bytes(1, "chrome-63.0.3234.0"),
            _field_bytes(2, "mcs.android.com"),
            _field_bytes(3, str(credentials.android_id)),
            _field_bytes(4, str(credentials.android_id)),
            _field_bytes(5, str(credentials.security_token)),
            _field_bytes(6, f"android-{credentials.android_id:x}"),
            _field_bytes(8, setting),
        )
    )
    for persistent_id in credentials.persistent_ids[-_MAX_PERSISTENT_IDS:]:
        payload += _field_bytes(10, persistent_id)
    payload += _field_varint(12, 0)
    payload += _field_varint(14, 1)
    payload += _field_varint(16, 2)
    payload += _field_varint(17, 1)
    return payload


def _frame(tag: int, payload: bytes, *, include_version: bool = False) -> bytes:
    prefix = bytes((MCS_VERSION,)) if include_version else b""
    return prefix + bytes((tag,)) + _encode_varint(len(payload)) + payload


def _build_heartbeat(last_stream_id: int | None) -> bytes:
    if last_stream_id is None:
        return b""
    return _field_varint(2, last_stream_id)


def _build_heartbeat_ack(payload: bytes, last_stream_id: int | None) -> bytes:
    fields = _parse_fields(payload)
    response = _build_heartbeat(last_stream_id)
    status = _first_int(fields, 3)
    if status is not None:
        response += _field_varint(3, status)
    return response


def _build_stream_ack(last_stream_id: int | None) -> bytes:
    extension = _field_varint(1, 13) + _field_bytes(2, b"")
    payload = _field_varint(2, 1)
    payload += _field_bytes(3, b"")
    payload += _field_bytes(7, extension)
    if last_stream_id is not None:
        payload += _field_varint(10, last_stream_id)
    payload += _field_varint(12, 0)
    return payload


def _parse_data_message(payload: bytes) -> FcmMessage:
    fields = _parse_fields(payload)
    data: dict[str, str] = {}
    for field_number, _wire_type, value in fields:
        if field_number != 7 or not isinstance(value, bytes):
            continue
        app_fields = _parse_fields(value)
        key = _text(_first_bytes(app_fields, 1))
        app_value = _text(_first_bytes(app_fields, 2))
        if key is not None and app_value is not None:
            data[key] = app_value
    return FcmMessage(
        category=_text(_first_bytes(fields, 5)),
        data=data,
        persistent_id=_text(_first_bytes(fields, 9)),
    )


async def _call(callback: Callable[[Any], Any], value: Any) -> None:
    result = callback(value)
    if inspect.isawaitable(result):
        await result


async def _read_length(reader: StreamReader) -> int:
    value = 0
    for shift in range(0, 35, 7):
        byte = (await reader.readexactly(1))[0]
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            if value > _MAX_FRAME_SIZE:
                raise FcmProtocolError("MCS frame exceeds the size limit")
            return value
    raise FcmProtocolError("MCS frame length is too long")


async def _read_frame(reader: StreamReader) -> tuple[int, bytes]:
    tag = (await reader.readexactly(1))[0]
    length = await _read_length(reader)
    return tag, await reader.readexactly(length)


class FcmClient:
    """Register and maintain a Fellow-compatible Android FCM connection."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_register(
        self, existing: FcmCredentials | None = None
    ) -> FcmCredentials:
        """Check in with Android services and obtain a Fellow app token."""
        try:
            async with asyncio.timeout(_HTTP_TIMEOUT_SECONDS):
                checkin_response = await self._session.request(
                    "post",
                    CHECKIN_URL,
                    data=_build_checkin_request(existing),
                    headers={"Content-Type": "application/x-protobuf"},
                )
                if not 200 <= checkin_response.status < 300:
                    checkin_response.release()
                    raise FcmRegistrationError(
                        f"Google check-in failed with HTTP {checkin_response.status}"
                    )
                android_id, security_token = _parse_checkin_response(
                    await checkin_response.read()
                )

                registration_response = await self._session.request(
                    "post",
                    REGISTER_URL,
                    data={
                        "X-subtype": FELLOW_SENDER_ID,
                        "sender": FELLOW_SENDER_ID,
                        "device": str(android_id),
                        "app": FELLOW_PACKAGE,
                        "cert": FELLOW_CERT_SHA1,
                        "app_ver": FELLOW_APP_VERSION_CODE,
                        "X-app_ver": FELLOW_APP_VERSION_CODE,
                        "X-app-ver-name": FELLOW_APP_VERSION_NAME,
                        "X-osv": "35",
                        "X-cliv": "fiid-21.1.1",
                        "X-gmsv": "250932000",
                        "X-scope": "*",
                        "X-gms_app_id": FELLOW_APP_ID,
                        "target_ver": "35",
                    },
                    headers={
                        "Authorization": (f"AidLogin {android_id}:{security_token}"),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                if not 200 <= registration_response.status < 300:
                    registration_response.release()
                    raise FcmRegistrationError(
                        "Google app registration failed with HTTP "
                        f"{registration_response.status}"
                    )
                parsed = parse_qs(
                    await registration_response.text(), keep_blank_values=True
                )
        except FcmError:
            raise
        except (aiohttp.ClientError, TimeoutError, OSError, ssl.SSLError) as err:
            raise FcmRegistrationError("Unable to register with Google FCM") from err

        token = parsed.get("token", [None])[0]
        if not token:
            error = parsed.get("Error", ["unknown error"])[0]
            raise FcmRegistrationError(f"Google rejected app registration: {error}")
        return FcmCredentials(
            android_id=android_id,
            security_token=security_token,
            fcm_token=token,
            persistent_ids=list(existing.persistent_ids) if existing else [],
        )

    async def async_listen(
        self,
        credentials: FcmCredentials,
        on_message: MessageCallback,
        on_connection: ConnectionCallback | None = None,
    ) -> None:
        """Listen until cancelled or the MCS connection fails."""
        writer: StreamWriter | None = None
        connected = False
        tasks: set[asyncio.Task[None]] = set()
        heartbeat_ack = asyncio.Event()
        incoming_stream_id = 1

        async def send(tag: int, payload: bytes = b"") -> None:
            if writer is None:
                raise FcmConnectionError("MCS connection is not open")
            writer.write(_frame(tag, payload))
            await writer.drain()

        async def read_loop(reader: StreamReader) -> None:
            nonlocal incoming_stream_id
            while True:
                tag, payload = await _read_frame(reader)
                incoming_stream_id += 1
                if tag == _MCS_HEARTBEAT_PING:
                    await send(
                        _MCS_HEARTBEAT_ACK,
                        _build_heartbeat_ack(payload, incoming_stream_id),
                    )
                elif tag == _MCS_HEARTBEAT_ACK:
                    heartbeat_ack.set()
                elif tag == _MCS_DATA_MESSAGE:
                    message = _parse_data_message(payload)
                    duplicate = (
                        message.persistent_id is not None
                        and message.persistent_id in credentials.persistent_ids
                    )
                    if message.persistent_id and not duplicate:
                        credentials.persistent_ids.append(message.persistent_id)
                        del credentials.persistent_ids[:-_MAX_PERSISTENT_IDS]
                    await send(
                        _MCS_IQ_STANZA,
                        _build_stream_ack(incoming_stream_id),
                    )
                    if not duplicate:
                        await _call(on_message, message)
                elif tag == _MCS_CLOSE:
                    raise FcmConnectionError("Google closed the MCS connection")
                elif tag == _MCS_STREAM_ERROR:
                    raise FcmProtocolError("Google reported an MCS stream error")

        async def heartbeat_loop() -> None:
            while True:
                await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
                heartbeat_ack.clear()
                await send(
                    _MCS_HEARTBEAT_PING,
                    _build_heartbeat(incoming_stream_id),
                )
                try:
                    async with asyncio.timeout(_HEARTBEAT_ACK_TIMEOUT_SECONDS):
                        await heartbeat_ack.wait()
                except TimeoutError as err:
                    raise FcmConnectionError(
                        "Google did not acknowledge the FCM heartbeat"
                    ) from err

        try:
            try:
                reader, writer = await asyncio.open_connection(
                    MCS_HOST,
                    MCS_PORT,
                    ssl=True,
                    server_hostname=MCS_HOST,
                )
                writer.write(
                    _frame(
                        _MCS_LOGIN_REQUEST,
                        _build_login_request(credentials),
                        include_version=True,
                    )
                )
                await writer.drain()

                async with asyncio.timeout(_LOGIN_TIMEOUT_SECONDS):
                    version = (await reader.readexactly(1))[0]
                    if version != MCS_VERSION:
                        raise FcmProtocolError(
                            f"Unsupported MCS protocol version: {version}"
                        )
                    tag, login_payload = await _read_frame(reader)
                if tag != _MCS_LOGIN_RESPONSE:
                    raise FcmProtocolError("MCS did not return a login response")
                if _first_bytes(_parse_fields(login_payload), 3) is not None:
                    raise FcmConnectionError("Google rejected the MCS login")
            except FcmError:
                raise
            except (
                asyncio.IncompleteReadError,
                OSError,
                TimeoutError,
                ssl.SSLError,
            ) as err:
                raise FcmConnectionError("Unable to connect to Google FCM") from err

            connected = True
            if on_connection:
                await _call(on_connection, True)

            tasks = {
                asyncio.create_task(read_loop(reader), name="fellow-fcm-reader"),
                asyncio.create_task(heartbeat_loop(), name="fellow-fcm-heartbeat"),
            }
            done, _pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_EXCEPTION
            )
            for task in done:
                error = task.exception()
                if error:
                    raise error
            raise FcmConnectionError("FCM connection ended unexpectedly")
        except (
            asyncio.IncompleteReadError,
            OSError,
            TimeoutError,
            ssl.SSLError,
        ) as err:
            raise FcmConnectionError("Google closed the FCM connection") from err
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if writer is not None:
                writer.close()
                try:
                    async with asyncio.timeout(5):
                        await writer.wait_closed()
                except (OSError, TimeoutError, ssl.SSLError):
                    pass
            if connected and on_connection:
                await _call(on_connection, False)
