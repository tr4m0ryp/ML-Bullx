# Makefile for Login Process with Tor Proxy Support
CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lssl -lcrypto -lcurl

# Original targets
Wallet_nonce: header_wallet_nonce.h api_request.h wallet_nonce.h
	$(CC) $(CFLAGS) -o wallet_nonce wallet_nonce.h $(LIBS)

verify_wallet_v2: header_wallet_nonce.h api_request.h verify_wallet_v2.c
	$(CC) $(CFLAGS) -o verify_wallet_v2 verify_wallet_v2.c $(LIBS)

wallet_generation: wallet_generation.h
	$(CC) $(CFLAGS) -o wallet_generation wallet_generation.h $(LIBS)


main: main.c wallet_nonce.h wallet_generation.h wallet_nonce.h wallet_generation.h header_wallet_nonce.h api_request.h
	$(CC) $(CFLAGS) -o main main.c wallet_nonce.h wallet_generation.h $(LIBS)

clean:
	rm -f wallet_nonce verify_wallet_v2 test_tor response_data.txt response_data_filtered.txt
