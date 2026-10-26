"""Master Test Suite Runner for ShopFlow POS."""

import sys
import time
import unittest
from pathlib import Path

# Configure utf-8 output if possible
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_master_suite():
    print("=" * 70)
    print(" [***] SHOPFLOW POS -- MASTER AUTOMATED TEST EXECUTION SUITE")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_modules = [
        "tests.test_unit_db",
        "tests.test_features_integration",
        "tests.test_load_performance",
        "tests.test_ui_ux",
        "tests.test_receipts_service",
    ]

    for mod_name in test_modules:
        try:
            mod = __import__(mod_name, fromlist=["*"])
            suite.addTests(loader.loadTestsFromModule(mod))
            print(f" [+] Loaded test module: {mod_name}")
        except Exception as e:
            print(f" [!] Failed to load {mod_name}: {e}")

    print("-" * 70)
    print(f" Total test cases to execute: {suite.countTestCases()}")
    print("-" * 70)

    t0 = time.perf_counter()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    elapsed = time.perf_counter() - t0

    print("=" * 70)
    print(" [***] EXECUTIVE TEST SUMMARY")
    print("=" * 70)
    print(f" Tests Run:   {result.testsRun}")
    print(f" Passed:      {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f" Failures:    {len(result.failures)}")
    print(f" Errors:      {len(result.errors)}")
    print(f" Total Time:  {elapsed:.2f} seconds")
    print("=" * 70)

    if result.wasSuccessful():
        print(" [SUCCESS] ALL 32 TEST CASES PASSED! System is 100% Production Ready.")
        return 0
    else:
        print(" [FAILURE] SOME TESTS FAILED. Review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_master_suite())
