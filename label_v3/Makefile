CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lcurl

search_pair: search_pair.c
	$(CC) $(CFLAGS) search_pair.c -o search_pair $(LIBS)

clean:
	rm -f search_pair response_data.txt

.PHONY: clean
