#include <stdio.h>
#include <stdlib.h>
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
#define _POSIX_C_SOURCE 200809L

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

    for(int i = 3; i < 1000; i++){
        if(request_count == 0 || request_count >= 150){
            if(headers) curl_slist_free_all(headers);
            cookies = cookies_main();
            headers = set_axiom_request_headers(cookies);
            request_count = 0;
        }


        search_pair(mint_add[i], &variable_data, headers);
        request_count++;
        printf("Token Ticker: %s\n", variable_data.tokenTicker);
        printf("Pair Address: %s\n", variable_data.pairAddress);
        printf("Creator: %s\n", variable_data.creator);
        
        if(variable_data.pairAddress[0] != 0){
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
            printf("Skipping mint address %s - search_pair failed\n", mint_add[i]);
        }
    }
    if(headers) curl_slist_free_all(headers);

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