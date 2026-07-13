import unittest

from e2e.test_health_security import HealthAndSecurityE2ETest


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HealthAndSecurityE2ETest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
