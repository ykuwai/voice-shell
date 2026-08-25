import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))
if "aiohttp" not in sys.modules:
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = types.SimpleNamespace()
    aiohttp.WSCloseCode = object()
    sys.modules["aiohttp"] = aiohttp

import viewer
from viewer import _allowed_hostports, _secure_dir


class AllowedHostportsTest(unittest.TestCase):
    """The set both the Host and the Origin checks in make_origin_guard draw on."""

    def test_loopback_names_always_included(self):
        allowed = _allowed_hostports("127.0.0.1", 47865)
        for host in ("127.0.0.1", "localhost", "::1", "[::1]"):
            self.assertIn(f"{host}:47865", allowed)

    def test_bind_address_zero_is_not_a_reachable_name(self):
        # "0.0.0.0" is what --host can be set to, never something a browser's
        # Host or Origin header actually says, so it must not end up allowed.
        allowed = _allowed_hostports("0.0.0.0", 47865)
        self.assertNotIn("0.0.0.0:47865", allowed)

    def test_explicit_host_is_added(self):
        allowed = _allowed_hostports("192.168.1.5", 47865)
        self.assertIn("192.168.1.5:47865", allowed)


class SecureDirTest(unittest.TestCase):
    """Guards STATE_DIR/CONFIG_DIR against another local account having gotten
    there first, whether as a real pre-existing directory or a planted symlink."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_creates_and_locks_down_a_fresh_directory(self):
        target = self.base / "state"
        _secure_dir(target)
        self.assertTrue(target.is_dir())
        self.assertEqual(target.stat().st_mode & 0o777, 0o700)

    def test_refuses_a_symlink_planted_at_the_target(self):
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        target = self.base / "state"
        target.symlink_to(elsewhere)
        with self.assertRaises(SystemExit):
            _secure_dir(target)

    def test_refuses_a_directory_owned_by_someone_else(self):
        target = self.base / "state"
        target.mkdir()
        with mock.patch.object(viewer.os, "getuid", return_value=target.stat().st_uid + 1):
            with self.assertRaises(SystemExit):
                _secure_dir(target)

    def test_leaves_an_already_private_directory_alone(self):
        target = self.base / "state"
        _secure_dir(target)
        (target / "marker").write_text("x", encoding="utf-8")
        _secure_dir(target)   # called again, the way both daemons do on every start
        self.assertTrue((target / "marker").exists())


if __name__ == "__main__":
    unittest.main()
