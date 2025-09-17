#ifndef API_REQUEST_V2_H
#define API_REQUEST_V2_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <curl/curl.h>
#include "./header_wallet_nonce.h"


// Response data structure for curl callback
struct ResponseDataV2 {
    char *memory;
    size_t size;
};

// Header data structure for curl callback
struct HeaderDataV2 {
    char *memory;
    size_t size;
};

// Global response data variable
struct ResponseDataV2 response_data_v2;
// Global header data variable  
struct HeaderDataV2 header_data_v2;
// Callback function for writing response data
size_t WriteMemoryCallbackV2(void *contents, size_t size, size_t nmemb, struct ResponseDataV2 *userp) {
    size_t realsize = size * nmemb;
    struct ResponseDataV2 *mem = (struct ResponseDataV2 *)userp;
    
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

// Callback function for writing header data
size_t WriteHeaderCallbackV2(void *contents, size_t size, size_t nmemb, struct HeaderDataV2 *userp) {
    size_t realsize = size * nmemb;
    struct HeaderDataV2 *mem = (struct HeaderDataV2 *)userp;
    
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


// Function to configure rotating proxy for login requests
void configure_login_proxy(CURL *curl) {
    // Configure rotating proxy for login requests
    curl_easy_setopt(curl, CURLOPT_PROXY, "p.webshare.io:80");
    curl_easy_setopt(curl, CURLOPT_PROXYTYPE, CURLPROXY_HTTP);
    curl_easy_setopt(curl, CURLOPT_PROXYUSERPWD, "uqfntenh-rotate:2mqxqanmjmr2");
    
    // Enable verbose output for debugging proxy connection (can be disabled in production)
    // curl_easy_setopt(curl, CURLOPT_VERBOSE, 1L);
}

int api_request_post(char *url, struct curl_slist *headers, const char *payload){
    CURL *curl;
    CURLcode result;
    
    // Initialize response data structure
    response_data_v2.memory = malloc(1);
    response_data_v2.size = 0;
    
    // Initialize header data structure
    header_data_v2.memory = malloc(1);
    header_data_v2.size = 0;
    
    curl = curl_easy_init();
    if(curl == NULL) {
        fprintf(stderr, "Failed to initialize curl\n");
        free(response_data_v2.memory);
        free(header_data_v2.memory);
        return 1;
    }

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteMemoryCallbackV2);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&response_data_v2);
    curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, WriteHeaderCallbackV2);
    curl_easy_setopt(curl, CURLOPT_HEADERDATA, (void *)&header_data_v2);

    // Configure rotating proxy for login requests
    configure_login_proxy(curl);

    result = curl_easy_perform(curl);
    
    
    if(result != CURLE_OK) {
        fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(result));
    } else {
        // Write response data to file
        FILE *file = fopen("response_data.txt", "w");
        if(file) {
            fprintf(file, "%s \n", response_data_v2.memory);
            fclose(file);
            //printf("Response data: %s\n", response_data_v2.memory);
            //printf("Response data saved to response_data.txt\n");
        } else {
            fprintf(stderr, "Failed to create response data file\n");
        }
    }

    // Cleanup
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    // DON'T free response_data_v2.memory here - it will be freed after filtering
    return result;
}

// Function to extract cookies from headers
char* extract_cookies_from_headers() {
    if (!header_data_v2.memory) {
        return NULL;
    }
    
    char *cookies = malloc(2048); // Allocate space for cookies
    if (!cookies) {
        return NULL;
    }
    
    cookies[0] = '\0'; // Initialize empty string
    
    // Split headers by lines and look for Set-Cookie headers
    // Create a copy of headers manually instead of using strdup
    size_t header_len = strlen(header_data_v2.memory);
    char *headers_copy = malloc(header_len + 1);
    if (!headers_copy) {
        free(cookies);
        return NULL;
    }
    strcpy(headers_copy, header_data_v2.memory);
    
    char *line = strtok(headers_copy, "\r\n");
    
    while (line != NULL) {
        // Check if line starts with "Set-Cookie:" (case insensitive)
        if (strncasecmp(line, "Set-Cookie:", 11) == 0) {
            // Extract cookie value (skip "Set-Cookie: ")
            char *cookie_value = line + 12; // Skip "Set-Cookie: "
            
            // Find semicolon to get just the cookie name=value part
            char *semicolon = strchr(cookie_value, ';');
            if (semicolon) {
                *semicolon = '\0'; // Terminate at semicolon
            }
            
            // Add to cookies string
            if (strlen(cookies) > 0) {
                strcat(cookies, "; "); // Add separator if not first cookie
            }
            strcat(cookies, cookie_value);
        }
        line = strtok(NULL, "\r\n");
    }
    
    free(headers_copy);
    
    // Return NULL if no cookies found
    if (strlen(cookies) == 0) {
        free(cookies);
        return NULL;
    }
    
    return cookies;
}

#endif // API_REQUEST_V2_H