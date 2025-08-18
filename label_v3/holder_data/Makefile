# Compiler and flags
CC = gcc
CFLAGS = -Wall -Wextra -std=c99 -O2
DEBUGFLAGS = -g -DDEBUG
LIBS = -lcurl

# Target executable
TARGET = holder_data_v3
SOURCE = holder_data_v3.c
OUTPUT_FILE = response_data.txt

# Default target
all: $(TARGET)

# Build the main target
$(TARGET): $(SOURCE)
	@echo "Compiling $(TARGET)..."
	$(CC) $(CFLAGS) $(SOURCE) -o $(TARGET) $(LIBS)
	@echo "Build successful!"

# Specific target as requested (alias)
holder_data_v3: $(SOURCE)
	@echo "Compiling $(TARGET)..."
	$(CC) $(CFLAGS) $(SOURCE) -o $(TARGET) $(LIBS)
	@echo "Build successful!"

# Debug build
debug: CFLAGS += $(DEBUGFLAGS)
debug: $(TARGET)

# Run the program
run: $(TARGET)
	@echo "Running $(TARGET)..."
	./$(TARGET)

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -f $(TARGET) $(OUTPUT_FILE)
	@echo "Clean complete!"

# Install dependencies (Ubuntu/Debian)
install-deps:
	@echo "Installing libcurl development package..."
	sudo apt-get update && sudo apt-get install -y libcurl4-openssl-dev

# Check if curl library is available
check-deps:
	@echo "Checking for libcurl..."
	@pkg-config --exists libcurl && echo "libcurl found" || echo "libcurl not found - run 'make install-deps'"

# Help target
help:
	@echo "Available targets:"
	@echo "  all           - Build the program (default)"
	@echo "  holder_data_v3 - Build the program (alias for all)"
	@echo "  debug         - Build with debug symbols"
	@echo "  run           - Build and run the program"
	@echo "  clean         - Remove build artifacts"
	@echo "  install-deps  - Install required dependencies"
	@echo "  check-deps    - Check if dependencies are installed"
	@echo "  help          - Show this help message"

# Declare phony targets
.PHONY: all holder_data_v3 debug run clean install-deps check-deps help
