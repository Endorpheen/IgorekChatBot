import hashlib
import unittest

from image_generation import FINGERPRINT_ITERATIONS, FINGERPRINT_SALT, ImageGenerationManager


class FingerprintTests(unittest.TestCase):
    def test_consistent_with_pbkdf2_parameters(self) -> None:
        value = "super-secret-api-key"
        expected = hashlib.pbkdf2_hmac(
            "sha256",
            value.encode("utf-8"),
            FINGERPRINT_SALT,
            FINGERPRINT_ITERATIONS,
        ).hex()

        result = ImageGenerationManager._fingerprint(value)

        self.assertEqual(result, expected)
        self.assertEqual(len(result), 64)

    def test_distinguishes_different_values(self) -> None:
        first = ImageGenerationManager._fingerprint("first-key")
        second = ImageGenerationManager._fingerprint("second-key")

        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertEqual(len(second), 64)

    def test_same_value_produces_same_hash(self) -> None:
        value = "repeatable"
        first = ImageGenerationManager._fingerprint(value)
        second = ImageGenerationManager._fingerprint(value)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
