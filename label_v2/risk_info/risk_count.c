#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h>
#include <string.h>
#include "./general_info/axiom_request_headers.h"

// Structure to hold response data
struct ResponseData {
    char *memory;
    size_t size;
};

// Callback function to write response data
static size_t WriteMemoryCallback(void *contents, size_t size, size_t nmemb, struct ResponseData *userp) {
    size_t realsize = size * nmemb;
    char *ptr = realloc(userp->memory, userp->size + realsize + 1);
    
    if (!ptr) {
        printf("Not enough memory (realloc returned NULL)\n");
        return 0;
    }
    
    userp->memory = ptr;
    memcpy(&(userp->memory[userp->size]), contents, realsize);
    userp->size += realsize;
    userp->memory[userp->size] = 0;
    
    return realsize;
}


//prototyping
int token_request(void);
int clean_up(void);

int main (void){
    token_request();
    clean_up();
    remove("dev_risk_info.json");
    return 0;
}

int token_request(void) {
    CURL *curl = curl_easy_init();
    if(curl) {
        const char *url = "https://api10.axiom.trade/token-analysis?devAddress=BSW9sDK3bDgr8MYi5uGoTUSQNTvVPwiEJQXmAV2wsQdu&tokenTicker=Fartcoin+";
        struct curl_slist *headers = set_axiom_request_headers();
        
        // Initialize response data structure
        struct ResponseData response_data;
        response_data.memory = malloc(1);
        response_data.size = 0;
        
        curl_easy_setopt(curl, CURLOPT_URL, url);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteMemoryCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&response_data);
        printf("Request URL: %s\n", url);

        // Perform the request
        CURLcode res = curl_easy_perform(curl);
        if(res != CURLE_OK) {
            fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
        } else {
            // Write response to JSON file
            FILE *temp_file = fopen("dev_risk_info.json", "w");
            if (temp_file) {
                fprintf(temp_file, "%s", response_data.memory);
                fclose(temp_file);
                printf("Response saved to dev_risk_info.json\n");
                printf("Response size: %zu bytes\n", response_data.size);
            } else {
                fprintf(stderr, "Failed to create JSON file\n");
            }
        }
        
        // Cleanup
        free(response_data.memory);
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }
    return 0;
}

int clean_up(void){
    FILE *input_file = fopen("dev_risk_info.json", "r");
    if (!input_file){
        fprintf(stderr, "Failed to open dev_risk_info.json for reading\n");
        return -1;
    }

    // Get file size
    fseek(input_file, 0, SEEK_END);
    long file_size = ftell(input_file);
    fseek(input_file, 0, SEEK_SET);

    if(file_size <= 0) {
        fprintf(stderr, "File is empty or error in file size\n");
        fclose(input_file);
        return -1;
    }

    //allocate memory
    char *content = malloc(file_size + 1);
    if (!content) {
        fprintf(stderr, "Failed to allocate memory for file content\n");
        fclose(input_file);
        return -1;
    }

    fread(content, 1, file_size, input_file);
    content[file_size] = '\0';
    

    //find "topmarketCap" section
    char *start_topmarket_capcoins = strstr(content, "\"topMarketCapCoins\":");  //topMarketCapCoins"
    if (!start_topmarket_capcoins) {
        fprintf(stderr, "topmarketCapCoins data not found in JSON\n");  
        return -1;
    }

    //create a file with new data
    FILE *output_file = fopen("dev_risk_info_cleaned.json", "w");
    if (!output_file) {
        fprintf(stderr, "Failed to open dev_risk_info_cleaned.json for writing\n");
        free(content);
        fclose(input_file);
        return -1;
    }
  
    //calculate amount of bytes to write (up to the topmarketCapCoins section)
    long bytes_to_write = start_topmarket_capcoins - content;

    // Find and remove trailing comma before topMarketCapCoins
    char *end_pos = start_topmarket_capcoins - 1;
    while (end_pos > content && (*end_pos == ' ' || *end_pos == '\n' || *end_pos == '\t' || *end_pos == '\r')) {
        end_pos--;
    }
    if (*end_pos == ',') {
        bytes_to_write = end_pos - content;
    }

    // Write the cleaned data to the output file (everything before topmarketCapCoins)
    fwrite(content, 1, bytes_to_write, output_file);
    
    // Add closing brace to make valid JSON
    fprintf(output_file, "\n}");
    fclose(input_file);
    fclose(output_file);

    free(content);
    return 0;
}