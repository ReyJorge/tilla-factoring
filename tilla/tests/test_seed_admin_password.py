"""ADMIN_PASSWORD via get_admin_password only; SESSION_SECRET must never substitute."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from app.seed import get_admin_password
from app.services.password_hashing import hash_password


class TestGetAdminPassword(unittest.TestCase):
    def test_short_admin_password_works_production(self):
        with mock.patch.dict(
            os.environ,
            {"ENVIRONMENT": "production", "ADMIN_PASSWORD": "  ninechars  "},
            clear=False,
        ):
            self.assertEqual(get_admin_password(), "ninechars")

    def test_missing_admin_password_production_raises(self):
        with mock.patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            os.environ.pop("ADMIN_PASSWORD", None)
            with self.assertRaisesRegex(
                RuntimeError,
                "ADMIN_PASSWORD is required in production/staging",
            ):
                get_admin_password()

    def test_missing_admin_password_staging_raises(self):
        with mock.patch.dict(os.environ, {"ENVIRONMENT": "staging"}, clear=False):
            os.environ.pop("ADMIN_PASSWORD", None)
            with self.assertRaisesRegex(
                RuntimeError,
                "ADMIN_PASSWORD is required in production/staging",
            ):
                get_admin_password()

    def test_long_admin_password_raises_before_passlib(self):
        long_pw = "x" * 73
        with mock.patch.dict(
            os.environ,
            {"ENVIRONMENT": "production", "ADMIN_PASSWORD": long_pw},
            clear=False,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "ADMIN_PASSWORD is too long for bcrypt",
            ):
                get_admin_password()

    def test_development_fallback_admin123_when_unset(self):
        with mock.patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            os.environ.pop("ADMIN_PASSWORD", None)
            self.assertEqual(get_admin_password(), "admin123")

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
            self.assertEqual(get_admin_password(), "mypassword")


class TestPasswordHashingGuard(unittest.TestCase):
    def test_hash_password_none_raises(self):
        with self.assertRaisesRegex(ValueError, "Password cannot be None"):
            hash_password(None)  # type: ignore[arg-type]

    def test_hash_password_empty_raises(self):
        with self.assertRaisesRegex(ValueError, "Password cannot be empty"):
            hash_password("   ")

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
