#include <stdio.h>
#include <stdlib.h>
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

    for(int i = 1; i < 2; i++){
        search_pair(mint_add[i], &variable_data);
        printf("Token Ticker: %s\n", variable_data.tokenTicker);
        printf("Pasir Address: %s\n", variable_data.pairAddress);
        printf("Creatos: %s\n", variable_data.creator);
        
        dev_token(variable_data.creator);
        //holder_data(variable_data.pairAddress);
        last_transaction(variable_data.pairAddress);
        pair_info(variable_data.pairAddress);
        //token_info_pair(variable_data.pairAddress);
        token_analysis(variable_data.creator, variable_data.tokenTicker);
    }

    return 0;

}


CSV_Data mint_token_csv(void){

    CSV_Data data = {0, NULL};

    //opening the file
    FILE *file = fopen("input.csv", "r");
    if(file == NULL){
        fprintf(stderr, "Could not open file input.csv\n");
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