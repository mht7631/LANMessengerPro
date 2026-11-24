import tempfile
import unittest
from pathlib import Path

from lanmessenger.storage import Store


class OutboxTests(unittest.TestCase):
    def test_outgoing_messages_are_queued_until_acknowledged(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.db")
            store.add_message("peer-1", "outgoing", "queued text")
            rows = store.pending_messages("peer-1")
            self.assertEqual(len(rows), 1)
            message_id = rows[0]["message_id"]
            self.assertEqual(rows[0]["delivery_status"], "queued")
            store.set_delivery_status(message_id, "sending")
            self.assertEqual(store.pending_messages("peer-1"), [])
            store.set_delivery_status(message_id, "failed")
            self.assertEqual(len(store.pending_messages("peer-1")), 1)
            store.set_delivery_status(message_id, "delivered")
            self.assertEqual(store.pending_messages("peer-1"), [])

    def test_incoming_message_defaults_to_delivered(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.db")
            store.add_message("peer-1", "incoming", "received")
            self.assertEqual(store.messages("peer-1")[0]["delivery_status"], "delivered")


if __name__ == "__main__":
    unittest.main()
