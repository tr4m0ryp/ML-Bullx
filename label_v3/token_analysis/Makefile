CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lcurl

token_analysis: token_analysis.c
	$(CC) $(CFLAGS) token_analysis.c -o token_analysis $(LIBS)

clean:
	rm -f token_analysis response_data.txt

.PHONY: clean
