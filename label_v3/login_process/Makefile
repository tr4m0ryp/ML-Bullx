# Makefile for Login Process with Tor Proxy Support
CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lssl -lcrypto -lcurl

# Original targets
Wallet_nonce: header_wallet_nonce.h api_request.h wallet_nonce.c
	$(CC) $(CFLAGS) -o wallet_nonce wallet_nonce.c $(LIBS)

verify_wallet_v2: header_wallet_nonce.h api_request.h verify_wallet_v2.c
	$(CC) $(CFLAGS) -o verify_wallet_v2 verify_wallet_v2.c $(LIBS)

# Tor proxy targets
test_tor: test_tor.c api_request.h header_wallet_nonce.h tor_proxy.h
	$(CC) $(CFLAGS) -o test_tor test_tor.c $(LIBS)

# Build all targets
all: Wallet_nonce verify_wallet_v2 test_tor

# Setup Tor system
setup_tor:
	./setup_tor.sh

# Test Tor functionality
test: test_tor
	./test_tor

# Install dependencies
install_deps:
	sudo apt-get update
	sudo apt-get install -y libcurl4-openssl-dev libssl-dev tor netcat-openbsd

clean:
	rm -f wallet_nonce verify_wallet_v2 test_tor response_data.txt response_data_filtered.txt

.PHONY: all clean install_deps test setup_tor