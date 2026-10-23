import asyncio
import base64
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "client"))

import db
from crypto import CryptoManager
from network import MAX_FILE_BYTES, NetworkEngine, _close_writer, _save_attachment
from server.server import MessengerServer

with patch("logging.FileHandler", return_value=logging.NullHandler()):
    from ui import SuperChat


class AttachmentStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.downloads = self.root / "downloads"

    def save(self, name, data=b"attachment"):
        return _save_attachment(self.downloads, name, base64.b64encode(data).decode("ascii"))

    def test_portable_filenames_and_empty_files(self):
        for name in ["notes.txt", "файл.jpg", ".hidden", "empty"]:
            with self.subTest(name=name):
                saved = self.save(name, b"")
                self.assertEqual(saved.parent, self.downloads)
                self.assertEqual(saved.name, name)
                self.assertEqual(saved.read_bytes(), b"")

    def test_rejects_paths_and_unsafe_names_before_creating_downloads(self):
        for name in ["../outside", "/absolute", "nested/file", r"..\outside", r"C:\outside", "C:outside",
                     "", ".", "..", "nul.txt", "CON .txt", "file.", "file ", "x\x00y", "a\nb", None, 1]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.save(name)
        self.assertFalse(self.downloads.exists())

    def test_duplicate_files_are_renamed_and_never_overwritten(self):
        first = self.save("notes.txt", b"first")
        second = self.save("notes.txt", b"second")
        third = self.save("notes.txt", b"third")
        self.assertEqual(first.read_bytes(), b"first")
        self.assertEqual(second.name, "notes (1).txt")
        self.assertEqual(third.name, "notes (2).txt")
        self.assertEqual(third.read_bytes(), b"third")

    def test_existing_symlink_cannot_redirect_a_download(self):
        self.downloads.mkdir()
        outside = self.root / "outside.txt"
        outside.write_bytes(b"preserve")
        (self.downloads / "notes.txt").symlink_to(outside)
        result = self.save("notes.txt", b"received")
        self.assertEqual(outside.read_bytes(), b"preserve")
        self.assertEqual(result.name, "notes (1).txt")

    def test_duplicate_maximum_length_names_still_fit_filesystem_limit(self):
        for name in ["я" * 120 + ".txt", "a." + "x" * 253]:
            with self.subTest(name=name):
                first = self.save(name)
                second = self.save(name, b"second")
                self.assertLessEqual(len(second.name.encode("utf-8")), 255)
                self.assertNotEqual(first, second)
                self.assertEqual(second.read_bytes(), b"second")

    def test_invalid_base64_and_oversized_data_leave_no_file(self):
        for encoded in ["!bad!", "é", "YQ", None, "A" * (4 * ((MAX_FILE_BYTES + 2) // 3) + 1)]:
            with self.subTest(encoded_type=type(encoded).__name__), self.assertRaises((ValueError, TypeError)):
                _save_attachment(self.downloads, "bad.bin", encoded)
        self.assertFalse(self.downloads.exists())

    def test_limit_is_inclusive_and_checks_decoded_length(self):
        with patch("network.MAX_FILE_BYTES", 3):
            self.assertEqual(self.save("limit.bin", b"123").read_bytes(), b"123")
            with self.assertRaises(ValueError):
                self.save("too-large.bin", b"1234")
        self.assertFalse((self.downloads / "too-large.bin").exists())


class AttachmentMessageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_patch = patch.object(db, "DB_PATH", str(self.root / "history.db"))
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        db.init_db()
        self.crypto = Mock()
        self.engine = NetworkEngine("bob", "127.0.0.1", 1, crypto_manager=self.crypto,
                                    downloads_dir=self.root / "downloads")
        self.engine.on_message_callback = Mock()

    async def test_incoming_file_envelope_is_not_dependent_on_json_key_order(self):
        self.crypto.decrypt.return_value = json.dumps({"data_b64": "YQ==", "file": "safe.txt"}, indent=2)
        await self.engine.handle_incoming_message("alice", "ciphertext")
        self.assertEqual((self.root / "downloads" / "safe.txt").read_bytes(), b"a")
        self.assertEqual(len(db.get_messages("alice")), 1)
        self.engine.on_message_callback.assert_called_once()

    async def test_regular_json_text_remains_a_message(self):
        text = '{"file": "an ordinary text message"}'
        self.crypto.decrypt.return_value = text
        await self.engine.handle_incoming_message("alice", "ciphertext")
        self.assertEqual(db.get_messages("alice")[0]["text"], text)
        self.assertFalse((self.root / "downloads").exists())

    async def test_rejected_incoming_file_creates_neither_file_nor_history(self):
        self.crypto.decrypt.return_value = json.dumps({"file": "../outside.txt", "data_b64": "YQ=="})
        with self.assertLogs(level=logging.ERROR):
            await self.engine.handle_incoming_message("alice", "ciphertext")
        self.assertFalse((self.root / "outside.txt").exists())
        self.assertEqual(db.get_messages("alice"), [])
        self.engine.on_message_callback.assert_not_called()

    async def test_outgoing_oversize_and_missing_paths_are_not_recorded_as_sent(self):
        db.save_contact("alice", "public key")
        oversized = self.root / "big.bin"
        with oversized.open("wb") as stream:
            stream.truncate(MAX_FILE_BYTES + 1)
        for path in [oversized, self.root / "missing", self.root]:
            with self.subTest(path=path), self.assertLogs(level=logging.ERROR):
                self.assertFalse(await self.engine.send_message("alice", "", is_file=True, file_path=path))
        self.assertFalse(await self.engine.send_message("alice", "", is_file=True))
        self.assertEqual(db.get_messages("alice"), [])
        self.crypto.encrypt_for.assert_not_called()
        self.engine.on_message_callback.assert_not_called()

    async def test_disconnected_send_is_not_recorded_as_sent(self):
        db.save_contact("alice", "public key")
        self.crypto.encrypt_for.return_value = "ciphertext"
        with self.assertLogs(level=logging.ERROR):
            self.assertFalse(await self.engine.send_message("alice", "unsent"))
        self.assertEqual(db.get_messages("alice"), [])
        self.engine.on_message_callback.assert_not_called()

    async def test_stalled_p2p_write_and_close_abort_then_fall_back_to_relay(self):
        async def never_returns():
            await asyncio.Future()

        db.save_contact("alice", "public key", "127.0.0.1", 12345)
        self.crypto.encrypt_for.return_value = "ciphertext"
        closed = asyncio.get_running_loop().create_future()
        async def wait_closed():
            await closed

        stalled = Mock(drain=AsyncMock(side_effect=never_returns), wait_closed=AsyncMock(side_effect=wait_closed))
        stalled.transport.abort.side_effect = lambda: closed.set_result(None)
        relay = Mock(drain=AsyncMock())
        self.engine.server_writer = relay
        with patch("network.asyncio.open_connection", new=AsyncMock(return_value=(Mock(), stalled))), \
             patch("network.SEND_TIMEOUT", 0.01), patch("network.WRITER_CLOSE_TIMEOUT", 0.01), \
             self.assertLogs(level=logging.WARNING):
            self.assertTrue(await asyncio.wait_for(self.engine.send_message("alice", "retry"), 1))
        stalled.close.assert_called_once()
        stalled.transport.abort.assert_called_once()
        relay.write.assert_called_once()
        self.assertEqual(len(db.get_messages("alice")), 1)

    async def test_stalled_relay_returns_failure_without_sent_history(self):
        async def never_returns():
            await asyncio.Future()

        db.save_contact("alice", "public key")
        self.crypto.encrypt_for.return_value = "ciphertext"
        closed = asyncio.get_running_loop().create_future()
        async def wait_closed():
            await closed

        writer = Mock(drain=AsyncMock(side_effect=never_returns), wait_closed=AsyncMock(side_effect=wait_closed))
        writer.transport.abort.side_effect = lambda: closed.set_result(None)
        self.engine.server_writer = writer
        with patch("network.SEND_TIMEOUT", 0.01), patch("network.WRITER_CLOSE_TIMEOUT", 0.01), \
             self.assertLogs(level=logging.ERROR):
            self.assertFalse(await asyncio.wait_for(self.engine.send_message("alice", "unsent"), 1))
        self.assertIsNone(self.engine.server_writer)
        writer.transport.abort.assert_called_once()
        self.assertEqual(db.get_messages("alice"), [])
        self.engine.on_message_callback.assert_not_called()

    async def test_repeated_close_does_not_cancel_shared_protocol_waiter(self):
        shared = asyncio.get_running_loop().create_future()
        async def wait_closed():
            await shared

        writer = Mock(wait_closed=AsyncMock(side_effect=wait_closed))
        with patch("network.WRITER_CLOSE_TIMEOUT", 0.01):
            await _close_writer(writer)
        self.assertFalse(shared.cancelled())
        writer.transport.abort.assert_called_once()
        shared.set_result(None)
        await asyncio.wait_for(_close_writer(writer), 1)
        self.assertFalse(shared.cancelled())

    async def test_cancelling_cleanup_aborts_transport_but_preserves_shared_waiter(self):
        shared = asyncio.get_running_loop().create_future()
        async def wait_closed():
            await shared

        writer = Mock(wait_closed=AsyncMock(side_effect=wait_closed))
        task = asyncio.create_task(_close_writer(writer))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        writer.transport.abort.assert_called_once()
        self.assertFalse(shared.cancelled())
        shared.set_result(None)
        await asyncio.sleep(0)

    async def test_ui_reports_failed_file_and_text_sends(self):
        app = SuperChat("bob")
        app.contact = "alice"
        app.network = Mock(send_message=AsyncMock(return_value=False))
        app.add_err = Mock()
        app.add_panel = Mock()
        source = self.root / "file.txt"
        source.write_bytes(b"attachment")
        await app._dispatch(f"/send {source}")
        self.assertIn("file was not sent", app.add_err.call_args.args[0])
        app.add_err.reset_mock()
        await app._dispatch("hello")
        self.assertIn("message was not sent", app.add_err.call_args.args[0])

    async def test_ui_status_distinguishes_connected_connecting_and_disconnected(self):
        app = SuperChat("bob")
        for status, expected in [("🟢 Connected", "h_ok"), ("🟡 Connecting...", "h_yw"),
                                 ("🔴 Disconnected (Retrying...)", "h_off")]:
            with self.subTest(status=status):
                app._set_header_status(status)
                text, attributes = app._h_text.get_text()
                self.assertIn(status.split(" ", 1)[1].lower(), text)
                self.assertIn(expected, [name for name, length in attributes])

    async def test_clean_relay_eof_clears_writer_and_backs_off(self):
        accepts = []
        disconnected = asyncio.Event()

        async def close_after_registration(reader, writer):
            accepts.append(writer)
            await reader.readline()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(close_after_registration, "127.0.0.1", 0)
        self.engine.server_port = server.sockets[0].getsockname()[1]
        self.crypto.get_public_key_pem.return_value = "test-key"
        self.engine.on_status_change_callback = lambda status: disconnected.set() if "Disconnected" in status else None
        task = asyncio.create_task(self.engine.connect_to_server())
        try:
            await asyncio.wait_for(disconnected.wait(), timeout=2)
            await asyncio.sleep(0.05)
            self.assertIsNone(self.engine.server_writer)
            self.assertEqual(len(accepts), 1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            server.close()
            await server.wait_closed()


class LoopbackTransferTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_patch = patch.object(db, "DB_PATH", str(self.root / "history.db"))
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        db.init_db()
        self.tasks = []
        self.server = MessengerServer(host="127.0.0.1", port=0)
        self.tasks.append(asyncio.create_task(self.server.start()))
        await self.wait_until(lambda: self.server.port != 0)
        self.alice = self.client("alice")
        self.bob = self.client("bob")
        self.received = asyncio.Queue()
        self.bob.on_message_callback = lambda sender, text: self.received.put_nowait((sender, text))
        self.tasks.extend([asyncio.create_task(self.alice.start()), asyncio.create_task(self.bob.start())])
        await self.wait_until(lambda: db.get_contact("alice") and db.get_contact("bob"))

    async def asyncTearDown(self):
        for task in self.tasks[1:]:
            task.cancel()
        await asyncio.gather(*self.tasks[1:], return_exceptions=True)
        await self.wait_until(lambda: not self.server.clients)
        self.tasks[0].cancel()
        await asyncio.gather(self.tasks[0], return_exceptions=True)

    async def wait_until(self, condition):
        async with asyncio.timeout(5):
            while not condition():
                await asyncio.sleep(0.01)

    def client(self, username):
        key = CryptoManager(str(self.root / f"{username}.pem"))
        return NetworkEngine(username, "127.0.0.1", self.server.port, crypto_manager=key,
                             downloads_dir=self.root / f"{username}-downloads", p2p_host="127.0.0.1")

    async def transfer(self, relay, data=None):
        # Encrypted wire data greatly exceeds asyncio's default 64 KiB line cap.
        if data is None:
            data = bytes(range(256)) * 1024
        source = self.root / "attachment.bin"
        source.write_bytes(data)
        if relay:
            contact = db.get_contact("bob")
            db.save_contact("bob", contact["public_key"], None, None)
        self.assertTrue(await self.alice.send_message("bob", "", is_file=True, file_path=source))
        sender, display = await asyncio.wait_for(self.received.get(), timeout=15)
        self.assertEqual(sender, "alice")
        self.assertIn("attachment.bin", display)
        self.assertEqual((self.bob.downloads_dir / "attachment.bin").read_bytes(), data)
        self.assertEqual(len(list(self.bob.downloads_dir.iterdir())), 1)

    async def test_p2p_file_above_64_kib_round_trips_with_real_encryption(self):
        await self.transfer(relay=False)

    async def test_relay_file_above_64_kib_round_trips_with_real_encryption(self):
        await self.transfer(relay=True)

    async def test_maximum_10_mib_file_round_trips_through_relay(self):
        await self.transfer(relay=True, data=b"\0" * MAX_FILE_BYTES)


if __name__ == "__main__":
    unittest.main()
