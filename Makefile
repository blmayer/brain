.PHONY: test clean help

# Default target
help:
	@echo "Available targets:"
	@echo "  make test    - Run all tests"
	@echo "  make clean   - Remove Python cache files"

# Run all tests using unittest discover (with debug logging enabled)
test:
	BRAIN_LOG_LEVEL=DEBUG python -m unittest discover -s . -p "test_*.py" -v

# Remove Python cache files and directories
clean:
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
