CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lcurl

token_info_pair: token_info_pair.c
	$(CC) $(CFLAGS) token_info_pair.c -o token_info_pair $(LIBS)

clean:
	rm -f token_info_pair response_data.txt

.PHONY: clean
