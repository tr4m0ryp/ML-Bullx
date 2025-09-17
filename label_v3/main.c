#include <stdio.h>
#include <stdlib.h>
#include <unistd.h> // for sleep function
#include "login_process/maincook.h"
#include "header.h"
#include "api_request.h"
#include "./search_pair.h"
#include "./dev_info/dev_token.h"
#include "./holder_data/holder_data_v3.h"
#include "./last_transaction/last_transaction.h"
#include "./pair_info/pair_info.h"
#include "./token_info_pair/token_info_pair.h"
#include "./token_analysis/token_analysis.h"

//stuctures
typedef struct{
        int number_of_lines;
        char **mint_address;
}CSV_Data;


//prototyping
CSV_Data mint_token_csv(void);

int main (void){
    SearchPairData variable_data;
    CSV_Data mint = mint_token_csv();
    
    //int line = mint.number_of_lines;
    char **mint_add = mint.mint_address;


    FILE *file = fopen("response_data_filtered.csv", "w");
    if(file){
        fprintf(file, "Mint_Adress, Dev_Total_count,Dev_Total_migrated_count,Type,LiquiditySOL,"
            "LiquidityToken,priceSOL,priceUsd,tokenAmount,totalSOL,TotalUSd,InnerIndex,OuterIndex,"
            "initialLiquiditySOL,InitialLiquidityToken,Supply,top10Holders,LpBurner,has_freezeAUthority,slot,DexPaid, Socials, Is_updated,"
            //"CreatorRiskLevel,CreatorRugcount,CreatorTokenCount,Amount_topMarketCapcoins,Amount_topOgCoins," //token_analysis.h
            "top10HoldersPercent,DevHoldsPercent,SniperHoldPercent,InsiderHoldPercent,BundlersHoldPercent,numHolders,numBotUsers,totalPairfeesPaid\n" //token_info_pair.h
        );
    }

    fclose(file);

    char *cookies = NULL;
    struct curl_slist *headers = NULL;
    int request_count = 0;

    for(int i = 2; i < 1000; i++){
        if(request_count == 0 || request_count >= 150){  // Refresh cookies every 150 requests
            // Clean up existing headers first
            if(headers) {
                curl_slist_free_all(headers);
                headers = NULL;
            }
            if(cookies) {
                free(cookies);
                cookies = NULL;
            }
            
            // Retry cookie generation until successful
            int cookie_retry_count = 0;
            const int max_cookie_retries = 3000;
            
            while(cookie_retry_count < max_cookie_retries) {
                cookies = cookies_main();
                if(cookies) {
                    // Generate new headers with the fresh cookies
                    headers = set_axiom_request_headers(cookies);
                    if(headers) {
                        request_count = 0;
                        printf("Successfully refreshed cookies for request #%d\n", i);
                        break; // Success, exit retry loop
                    } else {
                        printf("Failed to create headers for request #%d\n", i);
                        free(cookies);
                        cookies = NULL;
                    }
                } else {
                    printf("Failed to generate cookies for request #%d (attempt %d)\n", 
                           i, cookie_retry_count + 1);
                }
                
                cookie_retry_count++;
                
                // Add delay between retries (exponential backoff)
                if(cookie_retry_count < max_cookie_retries) {
                    int delay = cookie_retry_count * 2; // 2, 4, 6, 8 seconds
                    printf("Waiting %d seconds before retry...\n", delay);
                    sleep(delay);
                }
            }
            
            // If all retries failed, skip this iteration but don't advance i
            if(!cookies || !headers) {
                printf("All cookie generation attempts failed for request #%d. Retrying same request...\n", i);
                i--; // Decrement i so it will be the same on next iteration
                continue;
            }
        }

        // Try to search for the pair with retry mechanism
        int search_retry_count = 0;
        const int max_search_retries = 3;
        int search_success = 0;
        
        while(search_retry_count < max_search_retries && !search_success) {
            if(search_retry_count > 0) {
                printf("Retrying search_pair for mint %s (attempt %d/%d)\n", 
                       mint_add[i], search_retry_count + 1, max_search_retries);
            }
            
            search_pair(mint_add[i], &variable_data, headers);
            
            if(variable_data.pairAddress[0] != 0) {
                search_success = 1;
                request_count++;
                printf("Token Ticker: %s\n", variable_data.tokenTicker);
                printf("Pair Address: %s\n", variable_data.pairAddress);
                printf("Creator: %s\n", variable_data.creator);
                
                //opening the file to write the data in
                FILE *file = fopen("response_data_filtered.csv", "a");
                if(file){
                    fseek(file, 0, SEEK_END);
                    fprintf(file, "%s, ", mint_add[i]);
                }
                fclose(file);
                
                dev_token(variable_data.creator, headers);
                //holder_data(variable_data.pairAddress, headers);
                last_transaction(variable_data.pairAddress, headers);
                pair_info(variable_data.pairAddress, headers);
                //token_analysis(variable_data.creator, variable_data.tokenTicker, headers);
                token_info_pair(variable_data.pairAddress, headers);
            } else {
                search_retry_count++;
                printf("search_pair failed for mint address %s (attempt %d)\n", 
                       mint_add[i], search_retry_count);
                
                // If this wasn't the last retry, wait before trying again
                if(search_retry_count < max_search_retries) {
                    printf("Waiting 2 seconds before retry...\n");
                    sleep(2);
                }
            }
        }
        
        // If all search retries failed, log it but continue to next mint address
        if(!search_success) {
            printf("All search attempts failed for mint address %s - moving to next\n", mint_add[i]);
            // Still increment request_count to avoid infinite cookie refreshing
            request_count++;
        }
    }
    if(headers) curl_slist_free_all(headers);
    if(cookies) free(cookies);  // Free cookies at end

    return 0;

}


CSV_Data mint_token_csv(void){

    CSV_Data data = {0, NULL};

    //opening the file
    FILE *file = fopen("input.csv", "r");
    if(file == NULL){
        fprintf(stderr, "Could noot open file input.csv\n");
        return data;
    }

    //getting number of lines
    char line[1024];
    char c;
    int number_of_lines = 0;
    

    while ( (c =fgetc(file)) != EOF){
        if (c == '\n'){
            number_of_lines++;
        }
    }
    printf("Number of lsines is %i\n", number_of_lines);

    rewind(file);
    data.number_of_lines = number_of_lines;

    //filtering out all mint adress and adding them to a array; so it can be used lateron.
    data.mint_address = malloc(number_of_lines * sizeof(char*));
    for (int i = 1; i < number_of_lines; i++) { 
        if (fgets(line, sizeof(line), file) == NULL) {
            break; 
        }
        
        int j = 0;
        data.mint_address[i] = malloc(256);
        
        // Copy characters until we hit a comma or end of line
        while (line[j] != ',' && line[j] != '\n' && line[j] != '\0' && j < 255) {
            data.mint_address[i][j] = line[j];
            j++;
        }
        data.mint_address[i][j] = '\0';
    }
    
    fclose(file);
    return data;

}