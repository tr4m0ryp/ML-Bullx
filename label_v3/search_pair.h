#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include "api_request.h"

typedef struct {
    char tokenTicker[256];
    char pairAddress[256];
    char creator[256];
} SearchPairData;

int search_token_Data(SearchPairData *data) {
    // Open the file and check for errors
    FILE *file = fopen("response_data.txt", "r");
    if (!file) {
        fprintf(stderr, "Error: Could not open response_data.txt\n");
        return -1;
    }

    // Get file size
    fseek(file, 0, SEEK_END);
    long file_size = ftell(file);
    if (file_size <= 0) {
        fprintf(stderr, "Error: File is empty or seek failed\n");
        fclose(file);
        return -1;
    }
    fseek(file, 0, SEEK_SET);

    // Allocate memory for file content
    char *content = malloc(file_size + 1);
    if (!content) {
        fprintf(stderr, "Error: Memory allocation failed\n");
        fclose(file);
        return -1;
    }

    // Read file content
    size_t read_size = fread(content, 1, file_size, file);
    content[read_size] = '\0';
    fclose(file);

    if (read_size != file_size) {
        fprintf(stderr, "Error: Failed to read entire file\n");
        free(content);
        return -1;
    }

    // Initialize output structure
    memset(data->tokenTicker, 0, sizeof(data->tokenTicker));
    memset(data->pairAddress, 0, sizeof(data->pairAddress));
    memset(data->creator, 0, sizeof(data->creator));

    // Helper function to extract quoted string
    char temp[256];
    char *start, *end;

    // Parse tokenTicker
    char *tokenTicker = strstr(content, "\"tokenTicker\":\"");
    if (tokenTicker) {
        start = tokenTicker + strlen("\"tokenTicker\":\"");
        end = strchr(start, '\"');
        if (end && (end - start) < sizeof(data->tokenTicker)) {
            strncpy(temp, start, end - start);
            temp[end - start] = '\0';
            strncpy(data->tokenTicker, temp, sizeof(data->tokenTicker) - 1);
        }
    }

    // Parse pairAddress
    char *pairAddress = strstr(content, "\"pairAddress\":\"");
    if (pairAddress) {
        start = pairAddress + strlen("\"pairAddress\":\"");
        end = strchr(start, '\"');
        if (end && (end - start) < sizeof(data->pairAddress)) {
            strncpy(temp, start, end - start);
            temp[end - start] = '\0';
            strncpy(data->pairAddress, temp, sizeof(data->pairAddress) - 1);
        }
    }

    // Parse creator
    char *creator = strstr(content, "\"creator\":\"");
    if (creator) {
        start = creator + strlen("\"creator\":\"");
        end = strchr(start, '\"');
        if (end && (end - start) < sizeof(data->creator)) {
            strncpy(temp, start, end - start);
            temp[end - start] = '\0';
            strncpy(data->creator, temp, sizeof(data->creator) - 1);
        }
    }


    // Free memory
    free(content);
    return 0;
}

int search_pair(char *mint_address, SearchPairData *data) {
    char url[512];
    snprintf(url, sizeof(url), "https://api3.axiom.trade/search-v3?searchQuery=%s&isOg=false&isPumpSearch=false&isBonkSearch=false&isBagsSearch=false&onlyBonded=false", mint_address);
    api_request(url); // Assume this writes to response_data.txt
    return search_token_Data(data);
}