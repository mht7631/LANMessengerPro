import tempfile
import unittest
from pathlib import Path
from threading import Event

from lanmessenger.transport import PinnedTlsTransport, PairingRequired


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


if __name__ == "__main__":
    unittest.main()
