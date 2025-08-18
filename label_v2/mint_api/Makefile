CC=gcc
CFLAGS=-Wall -Wextra -std=c99
LIBS=-lcurl

TARGET=mint_request
SOURCES=mint_request.c

all: $(TARGET)

$(TARGET): $(SOURCES)
	$(CC) $(CFLAGS) -o $(TARGET) $(SOURCES) $(LIBS)

clean:
	rm -f $(TARGET) *.o token_info.json

install:
	sudo apt-get update
	sudo apt-get install libcurl4-openssl-dev

.PHONY: all clean install
