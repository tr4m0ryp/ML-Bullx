CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lcurl

last_transaction: last_transaction.c
	$(CC) $(CFLAGS) last_transaction.c -o last_transaction $(LIBS)

last_transaction: last_transaction.c
	$(CC) $(CFLAGS) last_transaction.c -o last_transaction $(LIBS)

clean:
	rm -f last_transaction last_transaction response_data.txt

.PHONY: clean
