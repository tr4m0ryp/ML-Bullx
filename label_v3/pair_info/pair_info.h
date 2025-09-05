#ifndef PAIR_INFO_H
#define PAIR_INFO_H

#include <stdio.h>
#include <stdbool.h>
#include "../api_request.h"
#include <string.h>

typedef struct{
    long initialLiquiditySol;
    long initialLiquidityToken;
    long supply;
    long top10Holders;
    long lpBurned;
    bool has_freezeAuthority;
    long slot;
    bool DexPaid;
    bool Socials;
    bool is_updated;
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
            fprintf(file, "%ld, %ld, %ld, %ld, %ld, %d, %ld, %d, %d, %d,",
                    data.initialLiquiditySol, data.initialLiquidityToken,
                    data.supply, data.top10Holders, data.lpBurned,
                    data.has_freezeAuthority, data.slot, data.DexPaid,
                    data.Socials, data.is_updated);
            fclose(file);
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
            sscanf(start, ":%ld", &data->initialLiquiditySol);
        }
    }

    //initialLiquidityToken
    char *initialLiquidityToken = strstr(json_data, "\"initialLiquidityToken\"");
    if (initialLiquidityToken) {
        char *start = strchr(initialLiquidityToken, ':');
        if (start) {
            sscanf(start, ":%ld", &data->initialLiquidityToken);
        }
    }

    //supply
    char *supply = strstr(json_data, "\"supply\"");
    if (supply) {
        char *start = strchr(supply, ':');
        if (start) {
            sscanf(start, ":%ld", &data->supply);
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
            sscanf(start, ":%ld", &data->slot);
        }
    }

    char *DexPaid = strstr(json_data, "\"DexPaid\"");
    if (DexPaid) {
        char *start = strchr(DexPaid, ':');
        if (start) {
            start++;
            while (*start == ' ') start++;  // Skip whitespace
            if (strncmp(start, "null", 4) == 0) {
                data->DexPaid = false;
            } else{
                data->DexPaid = true;
            }
        }
    }


    char *discord = strstr(json_data, "\"discord\"");
    char *twitter = strstr(json_data, "\"twitter\"");
    char *telegram = strstr(json_data, "\"telegram\"");
    char *website = strstr(json_data, "\"website\"");
    if (discord != NULL || twitter != NULL || telegram != NULL ||website != NULL) {
        data->Socials = true;
    } else {
        data->Socials = false;
    }

    char *createdAT = strstr(json_data, "\"createdAt\"");
    char *updatedAT = strstr(json_data, "\"updatedAt\"");

    if (strcmp(createdAT, updatedAT) == 0) {
        data->is_updated = false;
    } else {
        data->is_updated = true;
    }

    return 0;
}
#endif // PAIR_INFO_H