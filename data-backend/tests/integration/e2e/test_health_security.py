from __future__ import annotations

import unittest

from .client import E2EApiClient
from .cleanup import cleanup_suite_state
from .config import load_config


class HealthAndSecurityE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()
        cls.client = E2EApiClient(cls.cfg.base_url, cls.cfg.timeout_seconds)
        login = cls.client.login(cls.cfg.email, cls.cfg.password)
        if login.status_code not in (200, 201):
            raise RuntimeError(f"Health suite login failed: {login.status_code} {login.body}")

        cleanup_stats = cleanup_suite_state(cls.client)
        print(
            f"[Suite B setup] cleaned entities={cleanup_stats['entities']} tags={cleanup_stats['tags']}"
        )

    def tearDown(self):
        outcome = getattr(self, "_outcome", None)
        result = getattr(outcome, "result", None) if outcome else None
        failed = False
        if result is not None:
            for test_obj, _tb in list(result.errors) + list(result.failures):
                if test_obj is self or getattr(test_obj, "test_case", None) is self:
                    failed = True
                    break

        self.client.finalize_test_outcome(self._testMethodName, failed)

    def test_01_health_endpoint(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIsInstance(payload, dict)

    def test_02_health_detailed_endpoint(self):
        response = self.client.get("/api/health/detailed/")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIsInstance(payload, dict)

    def test_03_protected_endpoint_requires_auth(self):
        unauth_client = E2EApiClient(self.cfg.base_url, self.cfg.timeout_seconds)
        response = unauth_client.get("/api/entities/")
        self.assertIn(response.status_code, (401, 403), response.text)

    def test_04_login_success(self):
        result = self.client.login(self.cfg.email, self.cfg.password)
        self.assertIn(result.status_code, (200, 201), str(result.body))

        # Accept either JWT or token-key auth mode.
        self.assertTrue(
            self.client.access_token is not None or bool(self.client.session.cookies),
            f"No token/cookie established. Body={result.body}",
        )

    def test_05_login_failure_wrong_password(self):
        bad_client = E2EApiClient(self.cfg.base_url, self.cfg.timeout_seconds)
        result = bad_client.login(self.cfg.email, self.cfg.password + "_wrong")
        self.assertIn(result.status_code, (400, 401), str(result.body))

    def test_06_authenticated_user_endpoint(self):
        # Ensure logged in
        result = self.client.login(self.cfg.email, self.cfg.password)
        self.assertIn(result.status_code, (200, 201), str(result.body))

        response = self.client.get("/api/auth/user/")
        self.assertEqual(response.status_code, 200, response.text)

        payload = response.json()
        self.assertIsInstance(payload, dict)

        # Different auth backends expose different keys.
        email = payload.get("email")
        username = payload.get("username")
        self.assertTrue(
            email == self.cfg.email or username == self.cfg.email or username,
            f"Unexpected user payload: {payload}",
        )

    def test_07_csrf_cookie_endpoint(self):
        response = self.client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200, response.text)

        set_cookie = response.headers.get("Set-Cookie", "")
        self.assertTrue("csrftoken" in set_cookie or "csrftoken" in self.client.session.cookies.get_dict())

    def test_08_token_refresh_when_available(self):
        result = self.client.login(self.cfg.email, self.cfg.password)
        self.assertIn(result.status_code, (200, 201), str(result.body))

        refresh_response = self.client.token_refresh()
        if refresh_response is None:
            self.skipTest("Refresh token not returned by auth backend")

        self.assertIn(refresh_response.status_code, (200, 201), refresh_response.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
