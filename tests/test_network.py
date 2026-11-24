import json
import unittest

from lanmessenger.network import LanDiscovery, PROTOCOL_VERSION


class DiscoveryTests(unittest.TestCase):
    def test_accepts_valid_peer_presence(self):
        found = []
        service = LanDiscovery("local-device", "Local", found.append)
        payload = {
            "app": "LANMessengerPro",
            "version": PROTOCOL_VERSION,
            "type": "presence",
            "peer_id": "remote-device",
            "display_name": "Office PC",
            "tcp_port": 0,
            "sent_at": 1,
        }
        service._consume(json.dumps(payload).encode(), "192.168.1.22")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0].peer_id, "remote-device")
        self.assertEqual(found[0][0].display_name, "Office PC")
        self.assertEqual(found[0][0].host, "192.168.1.22")

    def test_ignores_own_presence(self):
        found = []
        service = LanDiscovery("local-device", "Local", found.append)
        payload = {
            "app": "LANMessengerPro",
            "version": PROTOCOL_VERSION,
            "type": "presence",
            "peer_id": "local-device",
            "display_name": "Local",
            "tcp_port": 0,
            "sent_at": 1,
        }
        service._consume(json.dumps(payload).encode(), "127.0.0.1")
        self.assertEqual(found, [])

    def test_ignores_wrong_application(self):
        found = []
        service = LanDiscovery("local-device", "Local", found.append)
        service._consume(b'{"app":"other","type":"presence"}', "127.0.0.1")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()