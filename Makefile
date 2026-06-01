.PHONY: test test-coref test-augment clean help

# Default target
help:
	@echo "Available targets:"
	@echo "  make test              - Run all tests"
	@echo "  make test ARGS=-v      - Run all tests verbosely"
	@echo "  make test-coref        - Run only coreference resolver tests"
	@echo "  make test-coref ARGS=-v - Run coref tests verbosely"
	@echo "  make test-augment      - Run only augmentation / KB pipeline tests"
	@echo "  make test-augment ARGS=-v - Run augment tests verbosely"
	@echo "  make clean             - Remove Python cache files"
	@echo ""
	@echo "Environment:"
	@echo "  BRAIN_LOG_LEVEL=DEBUG  - Enable debug logging during tests"
	@echo "  INSPECT_ONTOLOGY=1     - Enable the verbose ontology inspection test"

# Run all tests using unittest discover.
# For verbose output: make test ARGS="-v"
# For debug logging: BRAIN_LOG_LEVEL=DEBUG make test
test:
	python -m unittest discover -s . -p "test_*.py" $(ARGS)

# Run only the coreference resolver tests (including the demo example test)
test-coref:
	python -m unittest test_coreference_resolver $(ARGS)

# Run only the augmentation / ontology pipeline tests
test-augment:
	python -m unittest test_augment $(ARGS)

# Remove Python cache files and directories
clean:
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
