#ifndef TOKEN_ANALYSIS_H
#define TOKEN_ANALYSIS_H

#include <stdio.h>
#include "../api_request.h"

typedef struct{
    long creatorRiskLevel;
    int creatorRugCount;
    int creatorTokenCount;
    int amount_topMarketCapCoins;
    int amount_topOgCoins;
    long average_marketCap_TMCC;
    long average_marketCap_TOC;
} TokenAnalysisData; 




//prototyping
int token_analysis_structure_filtering(TokenAnalysisData *data);


int token_analysis(char *devAddress, char *tokenTicker) {
    TokenAnalysisData data;
    char url[256];
    
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/token-analysis?devAddress=%s&tokenTicker=%s", devAddress, tokenTicker);
    printf("URL: %s\n", url); // Debugging line to check the URL    
    // Call the API request function with the constructed URL
    int result = api_request(url);
   if (result == 0){
    token_analysis_structure_filtering(&data);

    //free the memory
    if(response_data.memory){
        free(response_data.memory);
        response_data.memory = NULL;
    }
    
    FILE *file = fopen("response_data_filtered.csv", "a");
    if(file){
        fseek(file, 0, SEEK_END);
        fprintf(file, "%ld, %d, %d, %d, %d, %ld, %ld, ",
                data.creatorRiskLevel, data.creatorRugCount,
                data.creatorTokenCount, data.amount_topMarketCapCoins,
                data.amount_topOgCoins, data.average_marketCap_TMCC,
                data.average_marketCap_TOC);
    }
   }
    return 0;
}

int token_analysis_structure_filtering(TokenAnalysisData *data){
    char *json_data = response_data.memory;

    if (!json_data) {
        printf("Error: No JSON data to parse\n");
        return -1;
    }

    printf("Parsing JSON: %.200s...\n", json_data);  // Debug: show first 200 chars

    //creatorRiskLevel
    char *creatorRiskLevel = strstr(json_data, "\"creatorRiskLevel\"");
    if (creatorRiskLevel) {
        char *start = strchr(creatorRiskLevel, ':');
        if (start) {
            sscanf(start, ":%ld", &data->creatorRiskLevel);
        }
    }

    //creatorRugCount
    char *creatorRugCount = strstr(json_data, "\"creatorRugCount\"");
    if (creatorRugCount) {
        char *start = strchr(creatorRugCount, ':');
        if (start) {
            sscanf(start, ":%d", &data->creatorRugCount);
        }
    }

    //creatorTokenCount
    char *creatorTokenCount = strstr(json_data, "\"creatorTokenCount\"");
    if (creatorTokenCount) {
        char *start = strchr(creatorTokenCount, ':');
        if (start) {
            sscanf(start, ":%d", &data->creatorTokenCount);
        }
    }

    //amount_topMarketCapCoins
    char *amount_topMarketCapCoins = strstr(json_data, "\"topMarketCapCoins\"");
    if (amount_topMarketCapCoins) {
        char *start = strchr(amount_topMarketCapCoins, ':');
        if (start) {
            sscanf(start, ":%d", &data->amount_topMarketCapCoins);
        }
    }

    //amount_topOgCoins
    char *amount_topOgCoins = strstr(json_data, "\"topOgCoins\"");
    if (amount_topOgCoins) {
        char *start = strchr(amount_topOgCoins, ':');
        if (start) {
            sscanf(start, ":%d", &data->amount_topOgCoins);
        }
    }

    //average_marketCap_TMCC
    //optional - will not work at all coins, could better be removed
    char *average_marketCap_TMCC = strstr(json_data, "\"average_marketCap_TMCC\"");
    if (average_marketCap_TMCC) {
        char *start = strchr(average_marketCap_TMCC, ':');
        if (start) {
            sscanf(start, ":%ld", &data->average_marketCap_TMCC);
        }
    }

    //average_marketCap_TOC
    //optional - will not work at all coins, could better be removed
    char *average_marketCap_TOC = strstr(json_data, "\"average_marketCap_TOC\"");
    if (average_marketCap_TOC) {
        char *start = strchr(average_marketCap_TOC, ':');
        if (start) {
            sscanf(start, ":%ld", &data->average_marketCap_TOC);
        }
    }

    return 0;
}

#endif // TOKEN_ANALYSIS_H