CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lcurl

main: main.c
	$(CC) $(CFLAGS) main.c -o main $(LIBS)

search_pair: search_pair.c
	$(CC) $(CFLAGS) search_pair.c -o search_pair $(LIBS)

clean:
	rm -f main search_pair response_data.txt

.PHONY: clean
