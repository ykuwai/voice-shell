import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

from port_config import DEFAULT_PORT, configured_port, parse_port


class PortConfigTest(unittest.TestCase):
    def test_uses_default_when_unset(self):
        self.assertEqual(DEFAULT_PORT, 47865)
        self.assertEqual(configured_port({}), 47865)

    def test_uses_voice_shell_port(self):
        self.assertEqual(configured_port({"VOICE_SHELL_PORT": "8090"}), 8090)

    def test_rejects_invalid_ports(self):
        for value in ("", "no", "0", "65536", "1.5"):
            with self.assertRaises(ValueError):
                parse_port(value, "VOICE_SHELL_PORT")

    def test_script_reports_invalid_environment_port(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "port_config.py")],
            text=True,
            capture_output=True,
            env=os.environ | {"VOICE_SHELL_PORT": "70000"},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("VOICE_SHELL_PORT must be an integer from 1 to 65535", result.stderr)


if __name__ == "__main__":
    unittest.main()
