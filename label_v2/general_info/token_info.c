#include <stdio.h>
#include <stdlib.h>
#include <curl/curl.h>
#include <string.h>
#include "axiom_request_headers.h"

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

int token_request(void);
int response_cleanup(void);

int main(void) {
    printf("Starting token request...\n");
    token_request();
    printf("Token request completed.\n");
    
    printf("Extracting 24h data...\n");
    response_cleanup();
    printf("Data extraction completed.\n");
    remove("token_info.json");
    printf("Temporary file removed.\n");
    
    return 0;
}

int token_request(void) {
    CURL *curl = curl_easy_init();
    if(curl) {
        const char *url = "https://api2.axiom.trade/lighthouse";
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
            FILE *temp_file = fopen("token_info.json", "w");
            if (temp_file) {
                fprintf(temp_file, "%s", response_data.memory);
                fclose(temp_file);
                printf("Response saved to token_info.json\n");
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

int response_cleanup(void) {
    // Read the original token_info.json file
    FILE *input_file = fopen("token_info.json", "r");
    if (!input_file) {
        fprintf(stderr, "Failed to open token_info.json for reading\n");
        return -1;
    }

    // Get file size
    fseek(input_file, 0, SEEK_END);
    long file_size = ftell(input_file);
    fseek(input_file, 0, SEEK_SET);

    // Read entire file content
    char *content = malloc(file_size + 1);
    if (!content) {
        fprintf(stderr, "Failed to allocate memory for file content\n");
        fclose(input_file);
        return -1;
    }
    
    fread(content, 1, file_size, input_file);
    content[file_size] = '\0';
    fclose(input_file);

    // Find the "24h" section
    char *start_24h = strstr(content, "\"24h\":");
    if (!start_24h) {
        fprintf(stderr, "24h data not found in JSON\n");
        free(content);
        return -1;
    }

    // Find the "All" section within 24h
    char *all_section = strstr(start_24h, "\"All\":");
    if (!all_section) {
        fprintf(stderr, "All section not found in 24h data\n");
        free(content);
        return -1;
    }

    // Find the start of the "All" data (after the colon)
    char *data_start = strchr(all_section, '{');
    if (!data_start) {
        fprintf(stderr, "Invalid All data format\n");
        free(content);
        return -1;
    }

    // Find the end of the "All" section by counting braces
    int brace_count = 0;
    char *data_end = data_start;
    do {
        if (*data_end == '{') brace_count++;
        if (*data_end == '}') brace_count--;
        data_end++;
    } while (brace_count > 0 && *data_end != '\0');

    // Calculate length of "All" data
    size_t data_length = data_end - data_start;

    // Create output file for 24h "All" data
    FILE *output_file = fopen("token_info_24h_all.json", "w");
    if (!output_file) {
        fprintf(stderr, "Failed to create token_info_24h_all.json\n");
        free(content);
        return -1;
    }

    // Write "All" data to new file
    fwrite(data_start, 1, data_length, output_file);
    fclose(output_file);

    free(content);
    return 0;
}
