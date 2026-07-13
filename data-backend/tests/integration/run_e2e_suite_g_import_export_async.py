import unittest

from e2e.test_suite_g_import_export_async import SuiteGImportExportAsyncE2ETest


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SuiteGImportExportAsyncE2ETest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
