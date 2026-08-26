from __future__ import annotations

import unittest
from unittest.mock import patch

from takhrij.security import AuthenticationError, verify_pubsub_oidc


class SecurityTests(unittest.TestCase):
    def test_missing_token_fails_closed(self):
        with self.assertRaises(AuthenticationError):
            verify_pubsub_oidc(
                None,
                audience="https://example.run.app/worker",
                expected_service_account="push@example.iam.gserviceaccount.com",
            )

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_signature_and_identity_claims_are_required(self, verify):
        audience = "https://example.run.app/worker"
        email = "push@example.iam.gserviceaccount.com"
        verify.return_value = {"aud": audience, "email": email, "email_verified": True}
        claims = verify_pubsub_oidc(
            "Bearer signed-token",
            audience=audience,
            expected_service_account=email,
        )
        self.assertEqual(claims["email"], email)
        verify.assert_called_once()

        verify.return_value = {
            "aud": audience,
            "email": "attacker@example.iam.gserviceaccount.com",
            "email_verified": True,
        }
        with self.assertRaisesRegex(AuthenticationError, "unexpected service account"):
            verify_pubsub_oidc(
                "Bearer signed-token",
                audience=audience,
                expected_service_account=email,
            )

    @patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("bad token"))
    def test_invalid_signature_is_rejected(self, _verify):
        with self.assertRaisesRegex(AuthenticationError, "invalid signed identity token"):
            verify_pubsub_oidc(
                "Bearer forged",
                audience="https://example.run.app/worker",
                expected_service_account="push@example.iam.gserviceaccount.com",
            )


if __name__ == "__main__":
    unittest.main()
