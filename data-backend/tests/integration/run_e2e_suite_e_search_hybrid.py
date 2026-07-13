import unittest

from e2e.test_suite_e_search_hybrid import SuiteESearchHybridE2ETest


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SuiteESearchHybridE2ETest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
