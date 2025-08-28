#ifndef DEV_TOKEN_H
#define DEV_TOKEN_H

#include <stdio.h>
#include <string.h>
#include "../api_request.h"


typedef struct{
    int totalCount;
    int migratedCount;

}DevTokenData;

//protoypes
int api_request(char *pairAdress);
int dev_token_structure_filtering(DevTokenData *data);


int dev_token(char *creator_address)
{
    DevTokenData data;

    char url[256];
    snprintf(url, sizeof(url), "https://api9.axiom.trade/dev-tokens-v2?devAddress=%s", creator_address);
    int result = api_request(url);
    
    if (result == 0) {
        // Parse the response data
        dev_token_structure_filtering(&data);

        FILE *file = fopen("response_data_filtered.csv", "a");
        if(file) {
            fseek(file, 0, SEEK_END);
            fprintf(file, "%d, %d, ", data.totalCount, data.migratedCount);
            fclose(file);
            printf("Dev token data: totalCount=%d, migratedCount=%d\n", data.totalCount, data.migratedCount);
        } else {
            fprintf(stderr, "Failed to create response data file\n");
        }
    }
    
    return result;
}



int dev_token_structure_filtering(DevTokenData *data){
   char *json_data = response_data.memory;
   
   // Initialize data structure
   data->totalCount = 0;
   data->migratedCount = 0;
   
   //searching for position of totalCount 
   char *totalCountpos = strstr(json_data, "\"totalCount\"");
   if (totalCountpos) {
       // Extract the totalCount value
       sscanf(totalCountpos, "\"totalCount\": %d", &data->totalCount);
   }

   //searching for position of migratedCount
   char *migratedCountpos = strstr(json_data, "\"migratedCount\"");
   if (migratedCountpos) {
       // Extract the migratedCount value
       sscanf(migratedCountpos, "\"migratedCount\": %d", &data->migratedCount);
   }

   return 0;
}
#endif // DEV_TOKEN_H