import unittest

from voice_telephony import validate_outbound_number


class VoiceTelephonyTests(unittest.TestCase):
    def test_requires_e164_number_in_allowlist(self):
        self.assertEqual(
            validate_outbound_number("+996555123456", ["+996555123456"]),
            "+996555123456",
        )

    def test_rejects_number_not_in_allowlist(self):
        with self.assertRaises(ValueError):
            validate_outbound_number("+996555123456", ["+996700000000"])

    def test_rejects_invalid_number_format(self):
        for value in ("0555123456", "+996 555 123456", "+00012345678", "+123"):
            with self.assertRaises(ValueError):
                validate_outbound_number(value, [value])


if __name__ == "__main__":
    unittest.main()
