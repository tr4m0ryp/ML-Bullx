#ifndef PAIR_INFO_H
#define PAIR_INFO_H

#include <stdio.h>
#include <stdbool.h>
#include "../api_request.h"

typedef struct{
    int initialLiquiditySol;
    int initialLiquidityToken;
    int supply;
    long top10Holders;
    long lpBurned;
    bool has_freezeAuthority;
    int slot;
} PairInfoData;


//prototyping
int api_request(char *url);
int pair_info_structure_filtering(PairInfoData *data);


int pair_info(char *pairAddress){
    PairInfoData data;
    char url[256];
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/pair-info?pairAddress=%s", pairAddress);
    
    // Call the API request function with the constructed URL
    int result = api_request(url);
    if (result == 0) {
        // Parse the response data
        pair_info_structure_filtering(&data);

        
        //free the memory
        if (response_data.memory) {
            free(response_data.memory);
            response_data.memory = NULL;
        }

        FILE *file = fopen("response_data_filtered.csv", "a");
        if (file) {
            fseek(file, 0, SEEK_END);
            fprintf(file, "%d, %d, %d, %ld, %ld, %d, %d, ",
                    data.initialLiquiditySol, data.initialLiquidityToken,
                    data.supply, data.top10Holders, data.lpBurned,
                    data.has_freezeAuthority, data.slot);
            fclose(file);
            printf("Pair info data: %d, %d, %d, %ld, %ld, %d, %d\n",
                   data.initialLiquiditySol, data.initialLiquidityToken,
                   data.supply, data.top10Holders, data.lpBurned,
                   data.has_freezeAuthority, data.slot);
        } else {
            fprintf(stderr, "Failed to create response data file\n");
        }
    }
    return 0;
}


int pair_info_structure_filtering(PairInfoData *data){
    char *json_data = response_data.memory;
    
    if (!json_data) {
        printf("Error: No JSON data to parse\n");
        return -1;
    }

    printf("Parsing JSON: %.200s...\n", json_data);  // Debug: show first 200 chars

    //initialLiquiditySol
    char *initialLiquiditySol = strstr(json_data, "\"initialLiquiditySol\"");
    if (initialLiquiditySol) {
        char *start = strchr(initialLiquiditySol, ':');
        if (start) {
            sscanf(start, ":%d", &data->initialLiquiditySol);
        }
    }

    //initialLiquidityToken
    char *initialLiquidityToken = strstr(json_data, "\"initialLiquidityToken\"");
    if (initialLiquidityToken) {
        char *start = strchr(initialLiquidityToken, ':');
        if (start) {
            sscanf(start, ":%d", &data->initialLiquidityToken);
        }
    }

    //supply
    char *supply = strstr(json_data, "\"supply\"");
    if (supply) {
        char *start = strchr(supply, ':');
        if (start) {
            sscanf(start, ":%d", &data->supply);
        }
    }

    //top10Holders
    char *top10Holders = strstr(json_data, "\"top10Holders\"");
    if (top10Holders) {
        char *start = strchr(top10Holders, ':');
        if (start) {
            sscanf(start, ":%ld", &data->top10Holders);
        }
    }

    //lpBurned
    char *lpBurned = strstr(json_data, "\"lpBurned\"");
    if (lpBurned) {
        char *start = strchr(lpBurned, ':');
        if (start) {
            sscanf(start, ":%ld", &data->lpBurned);
        }
    }

    //has_freezeAuthority
    char *has_freezeAuthority = strstr(json_data, "\"freezeAuthority\"");
    if (has_freezeAuthority) {
        char *start = strchr(has_freezeAuthority, ':');
        if (start) {
            start++;
            while (*start == ' ') start++;  // Skip whitespace
            if (strncmp(start, "true", 4) == 0) {
                data->has_freezeAuthority = true;
            } else if (strncmp(start, "false", 5) == 0) {
                data->has_freezeAuthority = false;
            }
        }
    }

    //slot
    char *slot = strstr(json_data, "\"slot\"");
    if (slot) {
        char *start = strchr(slot, ':');
        if (start) {
            sscanf(start, ":%d", &data->slot);
        }
    }



    //implementing Socials & DexPaid
    return 0;
}
#endif // PAIR_INFO_H