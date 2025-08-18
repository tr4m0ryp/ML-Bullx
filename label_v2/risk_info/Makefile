# Compiler and flags
CC = gcc
CFLAGS = -Wall -Wextra -std=c99
LIBS = -lcurl

# Targets
all: risk_count token_info

# Build risk_count with cURL library
risk_count: risk_count.c
	$(CC) $(CFLAGS) risk_count.c $(LIBS) -o risk_count

# Build token_info with cURL library  
token_info: token_info.c
	$(CC) $(CFLAGS) token_info.c $(LIBS) -o token_info

# Custom rule for curl library compilation
curlib: risk_count.c
	$(CC) $(CFLAGS) risk_count.c $(LIBS) -o risk_count

# Clean build artifacts
clean:
	rm -f risk_count token_info *.json

# Phony targets
.PHONY: all clean curlib
