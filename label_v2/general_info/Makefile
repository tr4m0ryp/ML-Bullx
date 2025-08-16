CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lcurl

token_info: token_info.c axiom_request_headers.h
	$(CC) $(CFLAGS) token_info.c $(LIBS) -o token_info

clean:
	rm -f token_info token_info.json

.PHONY: clean
