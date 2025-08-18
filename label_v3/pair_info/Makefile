CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lcurl

pair_info: pair_info.c
	$(CC) $(CFLAGS) pair_info.c -o pair_info $(LIBS)

clean:
	rm -f pair_info response_data.txt

.PHONY: clean
