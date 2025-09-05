#ifndef LAST_TRANSACTION_H
#define LAST_TRANSACTION_H

#include <stdio.h>
#include <string.h>
#include "../api_request.h"


typedef struct{
    char type[256];
    long double liquiditySol;
    long double liquidityToken; 
    long double priceSol;
    long double priceUsd;
    long double tokenAmount;
    long double totalSol;
    long double totalUsd;
    int innerIndex;
    int outerIndex;
} LastTransactionData;

// Function prototypes
int last_transaction_structure_filtering(LastTransactionData *data);

int last_transaction(char *pairAddress){
    LastTransactionData data;
    char url[256];
    
    
    data.outerIndex = -1;  // Use -1 to indicate null
    
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/last-transaction?pairAddress=%s", pairAddress);

    // Call the API request function with the constructed URL
    int result = api_request(url);
    if (result == 0) {
        // Parse the response and fill the data structure
        last_transaction_structure_filtering(&data);
        
        // Free the memory after parsing
        if (response_data.memory) {
            free(response_data.memory);
            response_data.memory = NULL;
        }
        
        FILE *file = fopen("response_data_filtered.csv", "a");
        fseek(file, 0, SEEK_END);
        fprintf(file, "%s, %.0Lf, %.0Lf, %.0Lf, %.0Lf, %.0Lf, %.0Lf, %.0Lf, %d, %d, ",
                data.type, data.liquiditySol, data.liquidityToken,
                data.priceSol, data.priceUsd, data.tokenAmount,
                data.totalSol, data.totalUsd, data.innerIndex,
                data.outerIndex);
        fclose(file);
        printf("Last transaction data: %s, %.0Lf, %.0Lf, %.0Lf, %.0Lf, %.0Lf, %.0Lf, %.0Lf, %d, %d\n",
               data.type, data.liquiditySol, data.liquidityToken,
               data.priceSol, data.priceUsd, data.tokenAmount,
               data.totalSol, data.totalUsd, data.innerIndex,
               data.outerIndex);
    }


    return 0;
}


int last_transaction_structure_filtering(LastTransactionData *data){
    char *json_data = response_data.memory;
    
    if (!json_data) {
        printf("Error: No JSON data to parse\n");
        return -1;
    }

    //printf("Parsing JSON: %.200s...\n", json_data);  // Debug: show first 200 chars

    // Parse type field
    char *type_field = strstr(json_data, "\"type\"");
    
    if (type_field) {
        char *start = strstr(type_field, ":");
        if (start) {
            start = strchr(start, '"');
            if (start) {
                start++;  // Skip opening quote
                char *end = strchr(start, '"');
                if (end) {
                    int len = end - start;
                    if (len < 255) {  // Ensure we don't overflow
                        strncpy(data->type, start, len);
                        data->type[len] = '\0';
                    }
                }
            }
        }
    }

    //liquiditySol
    char *liquiditySol = strstr(json_data, "\"liquiditySol\"");
    if (liquiditySol) {
        char *start = strchr(liquiditySol, ':');
        if (start) {
            sscanf(start, ":%Lf", &data->liquiditySol);
        }
    }

    //liquidityToken - using long double format
    char *liquidityToken = strstr(json_data, "\"liquidityToken\"");
    if (liquidityToken) {
        char *start = strchr(liquidityToken, ':');
        if (start) {
            sscanf(start, ":%Lf", &data->liquidityToken);
        }
    }
    
 
    char *priceSol = strstr(json_data, "\"priceSol\"");
    if (priceSol) {
        char *start = strchr(priceSol, ':');
        if (start) {
            sscanf(start, ":%Lf", &data->priceSol);
        }
    }

 
    char *priceUsd = strstr(json_data, "\"priceUsd\"");
    if (priceUsd) {
        char *start = strchr(priceUsd, ':');
        if (start) {
            sscanf(start, ":%Lf", &data->priceUsd);
        }
    }

    //tokenAmount
    char *tokenAmount = strstr(json_data, "\"tokenAmount\"");
    if (tokenAmount) {
        char *start = strchr(tokenAmount, ':');
        if (start) {
            sscanf(start, ":%Lf", &data->tokenAmount);
        }
    }

    //totalSol
    char *totalSol = strstr(json_data, "\"totalSol\"");
    if (totalSol) {
        char *start = strchr(totalSol, ':');
        if (start) {
            sscanf(start, ":%Lf", &data->totalSol);
        }
    }

    //totalUsd
    char *totalUsd = strstr(json_data, "\"totalUsd\"");
    if (totalUsd) {
        char *start = strchr(totalUsd, ':');
        if (start) {
            sscanf(start, ":%Lf", &data->totalUsd);
        }
    }

    //innerIndex - handle null values
    char *innerIndex = strstr(json_data, "\"innerIndex\"");
    if (innerIndex) {
        char *start = strchr(innerIndex, ':');
        if (start) {
            start++;
            while (*start == ' ') start++;  // Skip whitespace
            if (strncmp(start, "null", 4) == 0) {
                data->innerIndex = -1;  // Use -1 for null
            } else {
                sscanf(start, "%d", &data->innerIndex);
            }
        }
    }

    //outerIndex - handle null values
    char *outerIndex = strstr(json_data, "\"outerIndex\"");
    if (outerIndex) {
        char *start = strchr(outerIndex, ':');
        if (start) {
            start++;
            while (*start == ' ') start++;  // Skip whitespace
            if (strncmp(start, "null", 4) == 0) {
                data->outerIndex = -1;  // Use -1 for null
            } else {
                sscanf(start, "%d", &data->outerIndex);
            }
        }
    }

    return 0;
}

#endif // LAST_TRANSACTION_H