#ifndef LAST_TRANSACTION_H
#define LAST_TRANSACTION_H

#include <stdio.h>
#include "../api_request.h"


typedef struct{
    char type[256];
    float liquiditySol;
    int liquidityToken;
    float priceSol;
    float priceUsd;
    float tokenAmount;
    float totalSol;
    float totalUsd;
    int innerIndex;
    int outerIndex;
} LastTransactionData;

// Function prototypes
int last_transaction_structure_filtering(LastTransactionData *data);

int last_transaction(char *pairAddress){
    LastTransactionData data;
    char url[256];
    
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/last-transaction?pairAddress=%s", pairAddress);

    // Call the API request function with the constructed URL
    int result = api_request(url);
    if (result == 0) {
        // Parse the response and fill the data structure
        last_transaction_structure_filtering(&data);
        FILE *file = fopen("response_data_filtered.txt", "a");
        fseek(file, 0, SEEK_END);
        fprintf(file, "%s, %f, %d, %f, %f, %f, %f, %f, %d, %d\n",
                data.type, data.liquiditySol, data.liquidityToken,
                data.priceSol, data.priceUsd, data.tokenAmount,
                data.totalSol, data.totalUsd, data.innerIndex,
                data.outerIndex);
        fclose(file);
        printf("Last transaction data: %s, %f, %d, %f, %f, %f, %f, %f, %d, %d\n",
               data.type, data.liquiditySol, data.liquidityToken,
               data.priceSol, data.priceUsd, data.tokenAmount,
               data.totalSol, data.totalUsd, data.innerIndex,
               data.outerIndex);
    }


    return 0;
}


int last_transaction_structure_filtering(LastTransactionData *data){
    char *json_data = response_data.memory;

    //liquiditySol
    char *liquiditySol = strstr(json_data, " \"liquiditySol\"");
    if (liquiditySol) {
        sscanf(liquiditySol, " \"liquiditySol\": %f", &data->liquiditySol);
    }

    //liquidityToken
    char *liquidityToken = strstr(json_data, "\"liquidityToken\"");
    if (liquidityToken) {
        sscanf(liquidityToken, "\"liquidityToken\": %d", &data->liquidityToken);
    }
    //priceSol
    char *priceSol = strstr(json_data, "\"priceSol\"");
    if (priceSol) {
        sscanf(priceSol, "\"priceSol\": %f", &data->priceSol);
    }

    //priceUsd
    char *priceUsd = strstr(json_data, "\"priceUsd\"");
    if (priceUsd) {
        sscanf(priceUsd, "\"priceUsd\": %f", &data->priceUsd);
    }

    //tokenAmount
    char *tokenAmount = strstr(json_data, "\"tokenAmount\"");
    if (tokenAmount) {
        sscanf(tokenAmount, "\"tokenAmount\": %f", &data->tokenAmount);
    }

    //totalSol
    char *totalSol = strstr(json_data, "\"totalSol\"");
    if (totalSol) {
        sscanf(totalSol, "\"totalSol\": %f", &data->totalSol);
    }

    //totalUsd
    char *totalUsd = strstr(json_data, "\"totalUsd\"");
    if (totalUsd) {
        sscanf(totalUsd, "\"totalUsd\": %f", &data->totalUsd);
    }

    //innerIndex
    char *innerIndex = strstr(json_data, "\"innerIndex\"");
    if (innerIndex) {
        sscanf(innerIndex, "\"innerIndex\": %d", &data->innerIndex);
    }

    //outerIndex
    char *outerIndex = strstr(json_data, "\"outerIndex\"");
    if (outerIndex) {
        sscanf(outerIndex, "\"outerIndex\": %d", &data->outerIndex);
    }

    return 0;
}

#endif // LAST_TRANSACTION_H