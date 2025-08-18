CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lcurl

dev_token: dev_token.c
	$(CC) $(CFLAGS) dev_token.c -o dev_token $(LIBS)

clean:
	rm -f dev_token response_data.txt

.PHONY: clean
