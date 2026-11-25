import tempfile
import unittest
from pathlib import Path
from pathlib import Path
from threading import Event

from lanmessenger.transport import PinnedTlsTransport, PairingRequired, TransferRejected


class TransportIdentityTests(unittest.TestCase):
    def test_identity_is_persistent_and_fingerprint_is_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = PinnedTlsTransport("device-a", Path(directory), {}, lambda _msg: None, port=0)
            transport.start()
            first = transport.fingerprint
            transport.stop()
            again = PinnedTlsTransport("device-a", Path(directory), {}, lambda _msg: None, port=0)
            again.start()
            self.assertEqual(first, again.fingerprint)
            self.assertEqual(len(first), 64)
            again.stop()

    def test_trust_requires_matching_sha256_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = PinnedTlsTransport("device-a", Path(directory), {}, lambda _msg: None, port=0)
            transport.start()
            other = PinnedTlsTransport("device-b", Path(directory) / "other", {}, lambda _msg: None, port=0)
            other.start()
            with self.assertRaises(ValueError):
                transport.trust_peer("device-b", "00" * 32, other.certificate_pem)
            with self.assertRaises(ValueError):
                transport.trust_peer("wrong-device-id", other.fingerprint, other.certificate_pem)
            transport.trust_peer("device-b", other.fingerprint, other.certificate_pem)
            self.assertEqual(transport.trusted["device-b"], other.fingerprint)
            other.stop()
            transport.stop()

    def test_unpaired_send_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = PinnedTlsTransport("device-a", Path(directory), {}, lambda _msg: None, port=0)
            with self.assertRaises(PairingRequired):
                transport.send_message("127.0.0.1", 1, "device-b", "hello")

    def test_mutual_tls_message_delivery_and_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            received = Event()
            packets = []
            a = PinnedTlsTransport("device-a", Path(directory) / "a", {}, lambda _msg: None, port=0)
            b = PinnedTlsTransport("device-b", Path(directory) / "b", {}, lambda packet: (packets.append(packet), received.set()), port=0)
            a.start()
            b.start()
            a.trust_peer("device-b", b.fingerprint, b.certificate_pem)
            b.trust_peer("device-a", a.fingerprint, a.certificate_pem)
            message_id = a.send_message("127.0.0.1", b.port, "device-b", "hello over TLS")
            self.assertTrue(received.wait(2))
            self.assertEqual(packets[0]["body"], "hello over TLS")
            self.assertEqual(packets[0]["sender_id"], "device-a")
            self.assertEqual(packets[0]["message_id"], message_id)
            a.stop()
            b.stop()


    def test_paired_tls_file_transfer_requires_acceptance_and_verifies_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "payload.bin"
            payload = b"encrypted LAN file transfer" * 12000
            source.write_bytes(payload)
            received = root / "received"
            offered = Event()
            completed = []
            a = PinnedTlsTransport("device-a", root / "a", {}, lambda _msg: None, port=0)
            b = PinnedTlsTransport(
                "device-b", root / "b", {}, lambda _msg: None, port=0,
                on_file_offer=lambda _packet: received,
                on_file_received=lambda packet, path: (completed.append((packet, path)), offered.set()),
            )
            a.start()
            b.start()
            a.trust_peer("device-b", b.fingerprint, b.certificate_pem)
            b.trust_peer("device-a", a.fingerprint, a.certificate_pem)
            transfer_id = a.send_file("127.0.0.1", b.port, "device-b", source)
            self.assertTrue(offered.wait(3))
            self.assertEqual(completed[0][0]["transfer_id"], transfer_id)
            self.assertEqual(completed[0][1].read_bytes(), payload)
            a.stop()
            b.stop()

    def test_paired_tls_file_transfer_can_be_declined(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "declined.txt"
            source.write_text("do not save")
            a = PinnedTlsTransport("device-a", root / "a", {}, lambda _msg: None, port=0)
            b = PinnedTlsTransport(
                "device-b", root / "b", {}, lambda _msg: None, port=0,
                on_file_offer=lambda _packet: None,
            )
            a.start()
            b.start()
            a.trust_peer("device-b", b.fingerprint, b.certificate_pem)
            b.trust_peer("device-a", a.fingerprint, a.certificate_pem)
            with self.assertRaises(TransferRejected):
                a.send_file("127.0.0.1", b.port, "device-b", source)
            a.stop()
            b.stop()

    def test_paired_tls_folder_transfer_preserves_tree_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Project Docs"
            (source / "nested").mkdir(parents=True)
            (source / "one.txt").write_text("first")
            (source / "nested" / "two.txt").write_text("second file")
            receive_root = root / "received"
            completed = []
            final_received = Event()

            def on_file_received(packet, path):
                completed.append((packet, path))
                if packet.get("folder_index") == packet.get("folder_count"):
                    final_received.set()

            a = PinnedTlsTransport("device-a", root / "a", {}, lambda _msg: None, port=0)
            b = PinnedTlsTransport(
                "device-b", root / "b", {}, lambda _msg: None, port=0,
                on_file_offer=lambda packet: receive_root / packet["folder_name"],
                on_file_received=on_file_received,
            )
            a.start()
            b.start()
            a.trust_peer("device-b", b.fingerprint, b.certificate_pem)
            b.trust_peer("device-a", a.fingerprint, a.certificate_pem)
            folder_id, count, total_bytes = a.send_folder("127.0.0.1", b.port, "device-b", source)
            self.assertTrue(final_received.wait(5))
            self.assertEqual(count, 2)
            self.assertEqual(total_bytes, len(b"first") + len(b"second file"))
            self.assertEqual((receive_root / "Project Docs" / "one.txt").read_text(), "first")
            self.assertEqual((receive_root / "Project Docs" / "nested" / "two.txt").read_text(), "second file")
            self.assertEqual(completed[-1][0]["folder_id"], folder_id)
            a.stop()
            b.stop()

if __name__ == "__main__":
    unittest.main()
