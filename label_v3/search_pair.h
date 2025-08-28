#ifndef SEARCH_PAIR_H
#define SEARCH_PAIR_H

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


typedef struct{
    char tokenTicker[256];
    char pairAddress[256];
    char tokenAddress[256];
    int tokenDecimals;
    int supply;
    int liquiditySol;
    int liquidityToken;
    int marketCapSol;
    int bondingCurvePercent;
    int volumeSol;
    bool has_website;
    bool has_twitter;
    bool has_telegram;
    bool has_extra;
    bool has_dexPaid;
}SearchPairTokenData;

// Function declarations
int search_token_Data(SearchPairData *data);

//main function
int search_pair(char *mint_adress, SearchPairData *data){
    char url[512];
    snprintf(url, sizeof(url), "https://api3.axiom.trade/search-v3?searchQuery=%s&isOg=false&isPumpSearch=false&isBonkSearch=false&isBagsSearch=false&onlyBonded=false", mint_adress);
    api_request(url);
    search_token_Data(data);
    return 0;
}

int search_token_Data(SearchPairData *data){
    FILE *file = fopen("response_data.txt", "r");
    if (file == NULL) {
        fprintf(stderr, "Error opening file.\n");
        return -1;
    } 
    fseek(file, 0, SEEK_END);
    long file_size = ftell(file);
    fseek(file, 0, SEEK_SET);

    char *content = malloc(file_size + 1);
    if (content == NULL) {
        fprintf(stderr, "Memory allocation failed.\n");
        fclose(file);
        return -1;
    }

    fread(content, 1, file_size, file);
    content[file_size] = '\0';

    fclose(file);
    char *tokenTicker = strstr(content, "\"tokenTicker\":");
    char *pairAdress = strstr(content, "\"pairAddress\":");
    char *creator = strstr(content, "\"creator\":");
    if (tokenTicker && pairAdress && creator) {
        tokenTicker += strlen("\"tokenTicker\":");
        pairAdress += strlen("\"pairAddress\":");
        creator += strlen("\"creator\":");
        
        // Skip whitespace and opening quote
        while (*tokenTicker == ' ' || *tokenTicker == '\t') tokenTicker++;
        if (*tokenTicker == '"') tokenTicker++;
        while (*pairAdress == ' ' || *pairAdress == '\t') pairAdress++;
        if (*pairAdress == '"') pairAdress++;
        while (*creator == ' ' || *creator == '\t') creator++;
        if (*creator == '"') creator++;
        
        // Find the closing quote or comma
        char *end_tokenTicker = strchr(tokenTicker, '"');
        if (!end_tokenTicker) end_tokenTicker = strchr(tokenTicker, ',');
        char *end_pairAdress = strchr(pairAdress, '"');
        if (!end_pairAdress) end_pairAdress = strchr(pairAdress, ',');
        char *end_creator = strchr(creator, '"');
        if (!end_creator) end_creator = strchr(creator, ',');
        
        if (end_tokenTicker && end_pairAdress && end_creator) {
            *end_tokenTicker = '\0';
            *end_pairAdress = '\0';
            *end_creator = '\0';
            
            //saving data to SearchPairData struct
            strncpy(data->tokenTicker, tokenTicker, sizeof(data->tokenTicker) - 1);
            strncpy(data->pairAddress, pairAdress, sizeof(data->pairAddress) - 1);
            strncpy(data->creator, creator, sizeof(data->creator) - 1);
            
            // Ensure null termination
            data->tokenTicker[sizeof(data->tokenTicker) - 1] = '\0';
            data->pairAddress[sizeof(data->pairAddress) - 1] = '\0';
            data->creator[sizeof(data->creator) - 1] = '\0';
        } else {
            fprintf(stderr, "Error parsing JSON content.\n");
            free(content);
            return -1;
        }
    }
    free(content);
    return 0;
}

#endif // SEARCH_PAIR_H