#!/usr/bin/env python3
"""Minimal explicit test runner.

Prints only the test name and result:
    test_foo ... ok
    test_bar ... FAIL
    test_baz ... SKIP

Much less verbose than -v, more explicit than dots.
"""

import logging
import os
import sys
import time
import unittest
import traceback

# Force quiet logging during tests unless user overrides
os.environ.setdefault("BRAIN_LOG_LEVEL", "WARNING")

# Quiet noisy third-party libraries that tests may pull in (Stanza, HF, etc.)
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Suppress at runtime for anything that ignores the env vars
for noisy in ("transformers", "huggingface_hub", "stanza", "nltk", "filelock"):
    logging.getLogger(noisy).setLevel(logging.ERROR)


def _test_name(test):
    """Return just the bare test method name."""
    return test._testMethodName


class CleanTestResult(unittest.TestResult):
    """Result collector that prints 'name ... ok/FAIL/SKIP' as tests run."""

    def __init__(self, stream=None):
        super().__init__()
        self.stream = stream or sys.stdout
        self._last_test = None

    def startTest(self, test):
        super().startTest(test)
        self._last_test = test
        # Print the name immediately; result suffix comes in stopTest / addError etc.
        self.stream.write(f"{_test_name(test)} ... ")
        self.stream.flush()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.stream.write("ok\n")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.stream.write("FAIL\n")

    def addError(self, test, err):
        super().addError(test, err)
        self.stream.write("ERROR\n")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        # Show the skip reason briefly if short, otherwise just SKIP
        if reason and len(reason) < 60:
            self.stream.write(f"SKIP ({reason})\n")
        else:
            self.stream.write("SKIP\n")

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.stream.write("XFAIL\n")

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.stream.write("XPASS\n")

    def printErrors(self):
        """Print detailed tracebacks for failures and errors after the run."""
        if self.failures:
            self.stream.write("\n" + "=" * 70 + "\n")
            self.stream.write("FAILURES\n")
            self.stream.write("=" * 70 + "\n")
            for test, err in self.failures:
                self.stream.write(f"\n{_test_name(test)}\n")
                self.stream.write("-" * 70 + "\n")
                self.stream.write(err)
                self.stream.write("\n")

        if self.errors:
            self.stream.write("\n" + "=" * 70 + "\n")
            self.stream.write("ERRORS\n")
            self.stream.write("=" * 70 + "\n")
            for test, err in self.errors:
                self.stream.write(f"\n{_test_name(test)}\n")
                self.stream.write("-" * 70 + "\n")
                self.stream.write(err)
                self.stream.write("\n")


def _make_suite(targets):
    """Build a test suite from module names or patterns."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    if not targets:
        # Discover everything
        discovered = loader.discover(start_dir=".", pattern="test_*.py")
        suite.addTests(discovered)
        return suite

    for name in targets:
        if name.endswith(".py"):
            name = name[:-3]
        try:
            mod = __import__(name, fromlist=["*"])
            suite.addTests(loader.loadTestsFromModule(mod))
        except ImportError:
            # Try as file pattern
            discovered = loader.discover(start_dir=".", pattern=f"{name}*.py")
            suite.addTests(discovered)

    return suite


def run(targets=None):
    """Run tests and return (success: bool, result)."""
    suite = _make_suite(targets or [])

    result = CleanTestResult(stream=sys.stdout)

    start = time.time()
    suite.run(result)
    duration = time.time() - start

    # Print compact summary
    print()
    print("-" * 70)
    print(f"Ran {result.testsRun} tests in {duration:.3f}s")
    print()

    if result.wasSuccessful():
        print("OK")
    else:
        failed = len(result.failures) + len(result.errors)
        print(f"FAILED (failures={failed}, errors={len(result.errors)}, skipped={len(result.skipped)})")

    # Show detailed errors/failures
    result.printErrors()

    return result.wasSuccessful(), result


def main(argv=None):
    argv = argv or sys.argv[1:]

    # Support simple invocation:
    #   python run_tests.py
    #   python run_tests.py test_augment
    #   python run_tests.py test_coreference_resolver
    targets = argv if argv else None

    success, _ = run(targets)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
