#include <stdio.h>
#include "api_request.h"


//prototyping
int tokenTicker();


//main function
int main(void){
    char *url = "https://api3.axiom.trade/search-v3?searchQuery=8iYfd4azYc9j3QJ75zTyf6HVhs6PjbzYaka2oQxGpump&isOg=false&isPumpSearch=false&isBonkSearch=false&isBagsSearch=false&onlyBonded=false";
    api_request(url);
    tokenTicker();
    return 0;
}

int tokenTicker(void){
    FILE *file = fopen("response_data.txt", "r");
    if (file == NULL) {
        fprintf(stderr, "Error opening file.\n");
        return -1;
    } 
    fseek(file, 0, SEEK_END);
    long file_size = ftell(file);
    fseek(file, 0, SEEK_SET);

    char *content = malloc(file_size + 1);
    if (content == NULL) {
        fprintf(stderr, "Memory allocation failed.\n");
        fclose(file);
        return -1;
    }

    fread(content, 1, file_size, file);
    content[file_size] = '\0';

    fclose(file);
    char *tokenTicker = strstr(content, "\"tokenTicker\":");
    char *pairAdress = strstr(content, "\"pairAddress\":");
    char *creator = strstr(content, "\"creator\":");
    if (tokenTicker && pairAdress && creator) {
        tokenTicker += strlen("\"tokenTicker\":");
        pairAdress += strlen("\"pairAddress\":");
        creator += strlen("\"creator\":");
        char *end_tokenTicker = strchr(tokenTicker, ',');
        char *end_pairAdress = strchr(pairAdress, ',');
        char *end_creator = strchr(creator, ',');
        if (end_tokenTicker && end_pairAdress && end_creator) {
            *end_tokenTicker = '\0';
            *end_pairAdress = '\0';
            *end_creator = '\0';
            printf("Token Ticker: %s\n", tokenTicker);
            printf("Pair Address: %s\n", pairAdress);
            printf("Creator: %s\n", creator);
        } else {
            fprintf(stderr, "Error parsing JSON content.\n");
            free(content);
            return -1;
        }
    }
    free(content);
    return 0;
}