"""ADMIN_PASSWORD for seed: getenv-only, stripped; SESSION_SECRET must never substitute."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from app.seed import validate_admin_password_env_at_startup
from app.services.password_hashing import hash_password


class TestSeedAdminPassword(unittest.TestCase):
    def test_short_admin_password_works_production(self):
        with mock.patch.dict(
            os.environ,
            {"ENVIRONMENT": "production", "ADMIN_PASSWORD": "  ninechars  "},
            clear=False,
        ):
            validate_admin_password_env_at_startup()
            admin_pwd = os.getenv("ADMIN_PASSWORD", "").strip()
            self.assertEqual(admin_pwd, "ninechars")
            self.assertLessEqual(len(admin_pwd.encode("utf-8")), 72)

    def test_missing_admin_password_production_fails_clearly(self):
        with mock.patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            os.environ.pop("ADMIN_PASSWORD", None)
            with self.assertRaisesRegex(
                RuntimeError,
                "ADMIN_PASSWORD is required in production",
            ):
                validate_admin_password_env_at_startup()

    def test_session_secret_never_used_as_admin_password(self):
        long_secret = "x" * 120
        with mock.patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "ADMIN_PASSWORD": "mypassword",
                "SESSION_SECRET": long_secret,
            },
            clear=False,
        ):
            admin_pwd = os.getenv("ADMIN_PASSWORD", "").strip()
            self.assertEqual(admin_pwd, "mypassword")
            self.assertNotEqual(admin_pwd, long_secret)


class TestPasswordHashingGuard(unittest.TestCase):
    def test_hash_password_over_72_utf8_bytes_raises(self):
        plain = "ä" * 40
        self.assertGreater(len(plain.encode("utf-8")), 72)
        with self.assertRaisesRegex(
            ValueError,
            "Password is too long for bcrypt; use <=72 bytes",
        ):
            hash_password(plain)


if __name__ == "__main__":
    unittest.main()
