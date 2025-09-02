#ifndef TOKEN_INFO_PAIR_H
#define TOKEN_INFO_PAIR_H


#include <stdio.h>
#include "../api_request.h"

typedef struct{
    long top10HoldersPercent;
    long devHoldsPercent;
    long snipersHoldPercent;
    long insidersHoldPercent;
    long bundlersHoldPercent;
    int numHolders;
    int numBotUsers;
    long totalPairFeesPaid;
} TokenInfoPairData;


//prototyping
int token_info_pair_structure_filtering(TokenInfoPairData *data);

int token_info_pair(char *pairAddress) {
    TokenInfoPairData data;
    char url[256];
    
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/token-info?pairAddress=%s", pairAddress);

    // Call the API request function with the constructed URL
    int result =api_request(url);
    if(result == 0){
        token_info_pair_structure_filtering(&data);

        //free the memory
        if (response_data.memory) {
            free(response_data.memory);
            response_data.memory = NULL;
        }

        FILE *file = fopen("response_data_filtered.csv", "a");
        if(file){
            fseek(file, 0, SEEK_END);
            fprintf(file, "%ld, %ld, %ld, %ld, %ld, %d, %d, %ld\n",
                    data.top10HoldersPercent, data.devHoldsPercent,
                    data.snipersHoldPercent, data.insidersHoldPercent,
                    data.bundlersHoldPercent, data.numHolders,
                    data.numBotUsers, data.totalPairFeesPaid);
            printf("%ld, %ld, %ld, %ld, %ld, %d, %d, %ld\n",
                   data.top10HoldersPercent, data.devHoldsPercent,
                   data.snipersHoldPercent, data.insidersHoldPercent,
                   data.bundlersHoldPercent, data.numHolders,
                   data.numBotUsers, data.totalPairFeesPaid);
            fclose(file);
        }
    }
    return 0;
}



int token_info_pair_structure_filtering(TokenInfoPairData *data){
    char *json_data = response_data.memory;

    if (!json_data) {
        printf("Error: No JSON data to parse\n");
        return -1;
    }

    printf("Parsing JSON: %.200s...\n", json_data);  // Debug: show first 200 chars

    //top10HoldersPercent
    char *top10HoldersPercent = strstr(json_data, "\"top10HoldersPercent\"");
    if (top10HoldersPercent) {
        char *start = strchr(top10HoldersPercent, ':');
        if (start) {
            sscanf(start, ":%ld", &data->top10HoldersPercent);
        }
    }

    //devHoldsPercent
    char *devHoldsPercent = strstr(json_data, "\"devHoldsPercent\"");
    if (devHoldsPercent) {
        char *start = strchr(devHoldsPercent, ':');
        if (start) {
            sscanf(start, ":%ld", &data->devHoldsPercent);
        }
    }

    //snipersHoldPercent
    char *snipersHoldPercent = strstr(json_data, "\"snipersHoldPercent\"");
    if (snipersHoldPercent) {
        char *start = strchr(snipersHoldPercent, ':');
        if (start) {
            sscanf(start, ":%ld", &data->snipersHoldPercent);
        }
    }

    //insidersHoldPercent
    char *insidersHoldPercent = strstr(json_data, "\"insidersHoldPercent\"");
    if (insidersHoldPercent) {
        char *start = strchr(insidersHoldPercent, ':');
        if (start) {
            sscanf(start, ":%ld", &data->insidersHoldPercent);
        }
    }

    //bundlersHoldPercent
    char *bundlersHoldPercent = strstr(json_data, "\"bundlersHoldPercent\"");
    if (bundlersHoldPercent) {
        char *start = strchr(bundlersHoldPercent, ':');
        if (start) {
            sscanf(start, ":%ld", &data->bundlersHoldPercent);
        }
    }

    //numHolders
    char *numHolders = strstr(json_data, "\"numHolders\"");
    if (numHolders) {
        char *start = strchr(numHolders, ':');
        if (start) {
            sscanf(start, ":%d", &data->numHolders);
        }
    }

    //numBotUsers
    char *numBotUsers = strstr(json_data, "\"numBotUsers\"");
    if (numBotUsers) {
        char *start = strchr(numBotUsers, ':');
        if (start) {
            sscanf(start, ":%d", &data->numBotUsers);
        }
    }

    //totalPairFeesPaid
    char *totalPairFeesPaid = strstr(json_data, "\"totalPairFeesPaid\"");
    if (totalPairFeesPaid) {
        char *start = strchr(totalPairFeesPaid, ':');
        if (start) {
            sscanf(start, ":%ld", &data->totalPairFeesPaid);
        }
    }

    return 0;
}
#endif // TOKEN_INFO_PAIR_H