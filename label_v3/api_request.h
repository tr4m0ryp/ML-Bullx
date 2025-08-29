#ifndef API_REQUEST_H
#define API_REQUEST_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h>
#include "./header.h"


// Response data structure for curl callback
struct ResponseData {
    char *memory;
    size_t size;
};

// Global response data variable
struct ResponseData response_data;

// Callback function for writing response data
size_t WriteMemoryCallback(void *contents, size_t size, size_t nmemb, struct ResponseData *userp) {
    size_t realsize = size * nmemb;
    struct ResponseData *mem = (struct ResponseData *)userp;
    
    char *ptr = realloc(mem->memory, mem->size + realsize + 1);
    if (!ptr) {
        // Out of memory
        printf("Not enough memory (realloc returned NULL)\n");
        return 0;
    }
    
    mem->memory = ptr;
    memcpy(&(mem->memory[mem->size]), contents, realsize);
    mem->size += realsize;
    mem->memory[mem->size] = 0;
    
    return realsize;
}


int api_request(char *pairAdress){

    struct curl_slist *headers = NULL;
    CURL *curl;
    CURLcode result;
    
    // Initialize response data structure
    response_data.memory = malloc(1);
    response_data.size = 0;
    
    curl = curl_easy_init();
    if(curl == NULL) {
        fprintf(stderr, "Failed to initialize curl\n");
        free(response_data.memory);
        return 1;
    }

    headers = set_axiom_request_headers();

    curl_easy_setopt(curl, CURLOPT_URL, pairAdress);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteMemoryCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&response_data);

    result = curl_easy_perform(curl);
    
    
    if(result != CURLE_OK) {
        fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(result));
    } else {
        // Write response data to file
        FILE *file = fopen("response_data.txt", "w");
        if(file) {
            fprintf(file, "%s \n", response_data.memory);
            fclose(file);
            //printf("Response data: %s\n", response_data.memory);
            printf("Response data saved to response_data.txt\n");
        } else {
            fprintf(stderr, "Failed to create response data file\n");
        }
    }

    // Cleanup
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    // DON'T free response_data.memory here - it will be freed after filtering
    return result;
}

#endif // API_REQUEST_H