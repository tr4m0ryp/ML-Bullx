#include <stdio.h>
#include <stdlib.h>
#include "header_mint.h"


int main(void){
    header_fetch();
    return 0;
}


int header_fetch(void){
    CURL *curl = curl_easy_init();
    if(curl) {
        const char *url = "https://axiom.trade/meme/3WpJwy17ncxzhcrn7EZDAE9s2RmeexfjctW35e2NVEDn?_rsc=1j7by";
        struct curl_slist *headers = set_axiom_request_headers();
        
        // Initialize response data structure for headers
        struct ResponseData header_data;
        header_data.memory = malloc(1);
        header_data.size = 0;
        
        curl_easy_setopt(curl, CURLOPT_URL, url);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, WriteHeaderCallback);
        curl_easy_setopt(curl, CURLOPT_HEADERDATA, (void *)&header_data);
        printf("Request URL: %s\n", url);
        
        // Perform the request
        CURLcode res = curl_easy_perform(curl);
        if(res != CURLE_OK) {
            fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
        } else {
            // Write headers to file
            FILE *temp_file = fopen("token_headers.txt", "w");
            if (temp_file) {
                fprintf(temp_file, "%s", header_data.memory);
                fclose(temp_file);
                printf("Headers saved to token_headers.txt\n");
                printf("Headers size: %zu bytes\n", header_data.size);
            } else {
                fprintf(stderr, "Failed to create headers file\n");
            }
        }
        
        // Cleanup
        free(header_data.memory);
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }
    
    return 0;
}

//{"totalTransactions":11818297,"totalTransactionsPct":12.20857053310644,"totalTraders":548490,"totalTradersPct":15.186643565915892,"totalVolume":2336143620.3356247,"totalVolumePct":16.070883470758275,"totalBuyVolume":1165189577.631237,"totalSellVolume":1170954042.7043903,"totalBuyTransactions":6136786,"totalSellTransactions":5681511,"totalTokensCreated":33520,"totalTokensCreatedPct":0.9152215799614644,"totalMigrations":275,"totalMigrationsPct":0}
//{"totalTransactions":11843960,"totalTransactionsPct":12.847885700445783,"totalTraders":554416,"totalTradersPct":16.21831811121336,"totalVolume":2342428785.1815453,"totalVolumePct":16.420300698172557,"totalBuyVolume":1166893291.1356158,"totalSellVolume":1175535494.0459304,"totalBuyTransactions":6146186,"totalSellTransactions":5697774,"totalTokensCreated":34041,"totalTokensCreatedPct":2.04136690647482,"totalMigrations":275,"totalMigrationsPct":0}