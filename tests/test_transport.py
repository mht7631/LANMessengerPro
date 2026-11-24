import tempfile
import unittest
from pathlib import Path

from lanmessenger.transport import PinnedTlsTransport, PairingRequired


class TransportIdentityTests(unittest.TestCase):
    def test_identity_is_persistent_and_fingerprint_is_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = PinnedTlsTransport("device-a", Path(directory), {}, lambda _msg: None)
            transport.start()
            first = transport.fingerprint
            transport.stop()
            again = PinnedTlsTransport("device-a", Path(directory), {}, lambda _msg: None)
            again.start()
            self.assertEqual(first, again.fingerprint)
            self.assertEqual(len(first), 64)
            again.stop()

    def test_trust_requires_sha256_hex(self):
        transport = PinnedTlsTransport("device-a", Path(tempfile.gettempdir()) / "unused-lmp", {}, lambda _msg: None)
        with self.assertRaises(ValueError):
            transport.trust_peer("device-b", "not-a-fingerprint")
        transport.trust_peer("device-b", "AA" * 32)
        self.assertEqual(transport.trusted["device-b"], "aa" * 32)

    def test_unpaired_send_is_rejected_before_network(self):
        transport = PinnedTlsTransport("device-a", Path(tempfile.gettempdir()) / "unused-lmp", {}, lambda _msg: None)
        with self.assertRaises(PairingRequired):
            transport.send_message("127.0.0.1", 1, "device-b", "hello")


if __name__ == "__main__":
    unittest.main()
