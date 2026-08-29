from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from module_loader import load_fcm_module


class FakeResponse:
    def __init__(self, status: int, payload: bytes | str) -> None:
        self.status = status
        self.payload = payload
        self.released = False

    async def read(self) -> bytes:
        return self.payload.encode() if isinstance(self.payload, str) else self.payload

    async def text(self) -> str:
        return (
            self.payload.decode() if isinstance(self.payload, bytes) else self.payload
        )

    def release(self) -> None:
        self.released = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    async def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError(f"Unexpected request: {method} {url}")
        return self.responses.pop(0)


class FakeReader:
    def __init__(self, data: bytes) -> None:
        self.data = bytearray(data)

    async def readexactly(self, length: int) -> bytes:
        await asyncio.sleep(0)
        if len(self.data) < length:
            partial = bytes(self.data)
            self.data.clear()
            raise asyncio.IncompleteReadError(partial, length)
        value = bytes(self.data[:length])
        del self.data[:length]
        return value


class FakeWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        await asyncio.sleep(0)


class FcmProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.module, cleanup = load_fcm_module()
        self.addCleanup(cleanup)

    def test_credentials_reject_malformed_private_storage(self) -> None:
        self.assertIsNone(self.module.FcmCredentials.from_dict(None))
        self.assertIsNone(
            self.module.FcmCredentials.from_dict(
                {
                    "android_id": True,
                    "security_token": 2,
                    "fcm_token": "token",
                }
            )
        )
        credentials = self.module.FcmCredentials.from_dict(
            {
                "android_id": 1,
                "security_token": 2,
                "fcm_token": "token",
                "persistent_ids": [str(index) for index in range(110)],
            }
        )
        self.assertEqual(len(credentials.persistent_ids), 100)
        self.assertEqual(credentials.persistent_ids[0], "10")

    async def test_registers_as_the_signed_fellow_android_app(self) -> None:
        android_id = 123456
        security_token = 789012
        checkin = self.module._field_fixed64(7, android_id)
        checkin += self.module._field_fixed64(8, security_token)
        session = FakeSession(
            [
                FakeResponse(200, checkin),
                FakeResponse(200, "token=fellow-fcm-token"),
            ]
        )
        client = self.module.FcmClient(session)

        credentials = await client.async_register()

        self.assertEqual(credentials.android_id, android_id)
        self.assertEqual(credentials.security_token, security_token)
        self.assertEqual(credentials.fcm_token, "fellow-fcm-token")
        self.assertNotIn("fellow-fcm-token", repr(credentials))
        registration = session.requests[1][2]
        self.assertEqual(
            registration["headers"]["Authorization"],
            f"AidLogin {android_id}:{security_token}",
        )
        self.assertEqual(registration["data"]["app"], self.module.FELLOW_PACKAGE)
        self.assertEqual(registration["data"]["cert"], self.module.FELLOW_CERT_SHA1)
        self.assertNotIn("fellow-fcm-token", str(session.requests[0]))

    async def test_registration_transport_failure_is_a_connection_error(self) -> None:
        module = self.module

        class FailingSession:
            async def request(self, *_args: object, **_kwargs: object) -> object:
                raise module.aiohttp.ClientError("network failure")

        with self.assertRaises(module.FcmConnectionError):
            await module.FcmClient(FailingSession()).async_register(
                module.FcmCredentials(1, 2, "existing-token", ["persistent-id"])
            )

    async def test_explicit_registration_rejection_is_distinct(self) -> None:
        android_id = 123456
        security_token = 789012
        checkin = self.module._field_fixed64(7, android_id)
        checkin += self.module._field_fixed64(8, security_token)
        client = self.module.FcmClient(
            FakeSession(
                [
                    FakeResponse(200, checkin),
                    FakeResponse(200, "Error=AUTHENTICATION_FAILED"),
                ]
            )
        )

        with self.assertRaises(self.module.FcmRegistrationRejectedError):
            await client.async_register()

    def test_login_replays_only_recent_persistent_ids(self) -> None:
        credentials = self.module.FcmCredentials(
            android_id=1,
            security_token=2,
            fcm_token="token",
            persistent_ids=[str(index) for index in range(110)],
        )

        payload = self.module._build_login_request(credentials)
        fields = self.module._parse_fields(payload)
        persistent_ids = [
            value.decode() for number, _wire_type, value in fields if number == 10
        ]

        self.assertEqual(len(persistent_ids), 100)
        self.assertEqual(persistent_ids[0], "10")
        self.assertEqual(
            self.module._text(self.module._first_bytes(fields, 2)), "mcs.android.com"
        )

    def test_parses_data_message_and_builds_stream_ack(self) -> None:
        app_data = self.module._field_bytes(1, "notificationType")
        app_data += self.module._field_bytes(2, "brew-complete")
        payload = self.module._field_bytes(5, self.module.FELLOW_PACKAGE)
        payload += self.module._field_bytes(7, app_data)
        payload += self.module._field_bytes(9, "persistent-1")
        payload += self.module._field_varint(10, 42)

        message = self.module._parse_data_message(payload)
        ack = self.module._parse_fields(self.module._build_stream_ack(42))

        self.assertEqual(message.category, self.module.FELLOW_PACKAGE)
        self.assertEqual(message.data, {"notificationType": "brew-complete"})
        self.assertEqual(message.persistent_id, "persistent-1")
        self.assertEqual(self.module._first_int(ack, 10), 42)
        extension = self.module._parse_fields(self.module._first_bytes(ack, 7))
        self.assertEqual(self.module._first_int(extension, 1), 13)

    async def test_listener_logs_in_delivers_and_acknowledges(self) -> None:
        app_data = self.module._field_bytes(1, "type")
        app_data += self.module._field_bytes(2, "device-update")
        message_payload = self.module._field_bytes(5, self.module.FELLOW_PACKAGE)
        message_payload += self.module._field_bytes(7, app_data)
        message_payload += self.module._field_bytes(9, "persistent-1")
        message_payload += self.module._field_varint(10, 7)
        server_data = bytes((self.module.MCS_VERSION,))
        server_data += self.module._frame(self.module._MCS_LOGIN_RESPONSE, b"")
        server_data += self.module._frame(
            self.module._MCS_DATA_MESSAGE, message_payload
        )
        server_data += self.module._frame(
            self.module._MCS_DATA_MESSAGE, message_payload
        )
        server_data += self.module._frame(
            self.module._MCS_HEARTBEAT_PING,
            self.module._field_varint(1, 8),
        )
        server_data += self.module._frame(self.module._MCS_CLOSE, b"")
        reader = FakeReader(server_data)
        writer = FakeWriter()
        credentials = self.module.FcmCredentials(1, 2, "token")
        messages = []
        connections = []
        ssl_context = object()

        with (
            patch.object(
                self.module.asyncio,
                "to_thread",
                return_value=ssl_context,
            ) as to_thread,
            patch.object(
                self.module.asyncio,
                "open_connection",
                return_value=(reader, writer),
            ) as open_connection,
            self.assertRaises(self.module.FcmConnectionError),
        ):
            await self.module.FcmClient(FakeSession([])).async_listen(
                credentials,
                messages.append,
                connections.append,
            )

        self.assertEqual(messages[0].data, {"type": "device-update"})
        self.assertEqual(len(messages), 1)
        self.assertEqual(credentials.persistent_ids, ["persistent-1"])
        self.assertEqual(connections, [True, False])
        self.assertTrue(writer.closed)
        to_thread.assert_awaited_once_with(self.module.ssl.create_default_context)
        open_connection.assert_awaited_once_with(
            self.module.MCS_HOST,
            self.module.MCS_PORT,
            ssl=ssl_context,
            server_hostname=self.module.MCS_HOST,
        )
        self.assertEqual(writer.writes[0][:2], bytes((self.module.MCS_VERSION, 2)))
        iq_frame = next(
            frame
            for frame in writer.writes[1:]
            if frame[0] == self.module._MCS_IQ_STANZA
        )
        iq_length, iq_payload_offset = self.module._decode_varint(iq_frame, 1)
        iq_fields = self.module._parse_fields(
            iq_frame[iq_payload_offset : iq_payload_offset + iq_length]
        )
        self.assertEqual(self.module._first_int(iq_fields, 10), 2)
        self.assertEqual(
            sum(frame[0] == self.module._MCS_IQ_STANZA for frame in writer.writes[1:]),
            2,
        )

        heartbeat_frame = next(
            frame
            for frame in writer.writes[1:]
            if frame[0] == self.module._MCS_HEARTBEAT_ACK
        )
        heartbeat_length, heartbeat_payload_offset = self.module._decode_varint(
            heartbeat_frame, 1
        )
        heartbeat_fields = self.module._parse_fields(
            heartbeat_frame[
                heartbeat_payload_offset : heartbeat_payload_offset + heartbeat_length
            ]
        )
        self.assertEqual(self.module._first_int(heartbeat_fields, 2), 4)

    async def test_listener_does_not_record_message_when_ack_fails(self) -> None:
        module = self.module

        class FailingAckWriter(FakeWriter):
            def __init__(self) -> None:
                super().__init__()
                self.drain_count = 0

            async def drain(self) -> None:
                self.drain_count += 1
                if self.drain_count == 2:
                    raise ConnectionResetError("ack failed")
                await super().drain()

        app_data = module._field_bytes(1, "type")
        app_data += module._field_bytes(2, "device-update")
        message_payload = module._field_bytes(5, module.FELLOW_PACKAGE)
        message_payload += module._field_bytes(7, app_data)
        message_payload += module._field_bytes(9, "persistent-1")
        server_data = bytes((module.MCS_VERSION,))
        server_data += module._frame(module._MCS_LOGIN_RESPONSE, b"")
        server_data += module._frame(module._MCS_DATA_MESSAGE, message_payload)
        reader = FakeReader(server_data)
        writer = FailingAckWriter()
        credentials = module.FcmCredentials(1, 2, "token")
        messages = []

        with (
            patch.object(module.asyncio, "to_thread", return_value=object()),
            patch.object(
                module.asyncio,
                "open_connection",
                return_value=(reader, writer),
            ),
            self.assertRaises(module.FcmConnectionError),
        ):
            await module.FcmClient(FakeSession([])).async_listen(
                credentials,
                messages.append,
            )

        self.assertEqual(messages, [])
        self.assertEqual(credentials.persistent_ids, [])
        self.assertTrue(writer.closed)

    async def test_listener_distinguishes_rejected_android_credentials(self) -> None:
        login_error = self.module._field_bytes(3, "rejected")
        server_data = bytes((self.module.MCS_VERSION,))
        server_data += self.module._frame(self.module._MCS_LOGIN_RESPONSE, login_error)
        reader = FakeReader(server_data)
        writer = FakeWriter()

        with (
            patch.object(
                self.module.asyncio,
                "to_thread",
                return_value=object(),
            ),
            patch.object(
                self.module.asyncio,
                "open_connection",
                return_value=(reader, writer),
            ),
            self.assertRaises(self.module.FcmAuthenticationError),
        ):
            await self.module.FcmClient(FakeSession([])).async_listen(
                self.module.FcmCredentials(1, 2, "token"),
                lambda _message: None,
            )

    async def test_rejects_oversized_frames_before_reading_payload(self) -> None:
        length = self.module._encode_varint(self.module._MAX_FRAME_SIZE + 1)
        reader = FakeReader(bytes((8,)) + length)

        with self.assertRaises(self.module.FcmProtocolError):
            await self.module._read_frame(reader)
