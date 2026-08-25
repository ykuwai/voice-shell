import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

from voice_daemon import route_shape


class RouteNumberTest(unittest.TestCase):
    """Every language routes on Arabic digits, and all but Korean also read out
    their own native number words. Korean's native readings were added later
    (its 이번, "number two", is also the everyday word for "this time"), so
    it gets its own case spelling out why that is safe."""

    def test_digits_work_everywhere(self):
        self.assertEqual(route_shape("2番"), 2)
        self.assertEqual(route_shape("session 2"), 2)
        self.assertEqual(route_shape("sesión 2"), 2)
        self.assertEqual(route_shape("2번"), 2)

    def test_native_readings(self):
        self.assertEqual(route_shape("2番目"), 2)
        self.assertEqual(route_shape("number two"), 2)
        self.assertEqual(route_shape("sesión dos"), 2)
        self.assertEqual(route_shape("session deux"), 2)
        self.assertEqual(route_shape("Sitzung zwei"), 2)
        self.assertEqual(route_shape("会话二"), 2)

    def test_korean_native_reading(self):
        # 이번 alone is exactly 이 (2) + 번 (the counter), the same shape every
        # other language's counter pattern already matches on.
        self.assertEqual(route_shape("이번"), 2)
        self.assertEqual(route_shape("일번"), 1)
        self.assertEqual(route_shape("삼번으로 보내"), 3)

    def test_korean_native_reading_inside_a_sentence_does_not_fire(self):
        # 이번 is also the everyday word for "this time". The guard every
        # routing phrase already has, the whole utterance must be only this,
        # is what keeps ordinary talk from being read as a command.
        self.assertIsNone(route_shape("이번에는 다른 얘기를 좀 해볼까 합니다"))


if __name__ == "__main__":
    unittest.main()
