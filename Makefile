.PHONY: test test-coref test-augment test-verbose clean help

# Default target
help:
	@echo "Available targets:"
	@echo "  make test              - Run all tests (clean output: name + result only)"
	@echo "  make test-coref        - Run only coreference resolver tests"
	@echo "  make test-augment      - Run only augmentation / KB pipeline tests"
	@echo "  make test-verbose      - Run all tests with full unittest -v output"
	@echo "  make clean             - Remove Python cache files"
	@echo ""
	@echo "Environment:"
	@echo "  BRAIN_LOG_LEVEL=DEBUG  - Enable debug logging during tests"
	@echo "  INSPECT_ONTOLOGY=1     - Enable the verbose ontology inspection test"
	@echo ""
	@echo "For classic unittest dots/verbose output:"
	@echo "  python -m unittest discover -v"

# Run all tests with clean, explicit, minimal output (test name + PASS/FAIL/SKIP only).
# This is the recommended way to run tests.
test:
	python run_tests.py

# Run only the coreference resolver tests
test-coref:
	python run_tests.py test_coreference_resolver

# Run only the augmentation / ontology pipeline tests
test-augment:
	python run_tests.py test_augment

# Full verbose unittest output (original behavior)
test-verbose:
	python -m unittest discover -s . -p "test_*.py" -v

# Remove Python cache files and directories
clean:
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
