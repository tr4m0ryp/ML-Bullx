#ifndef HEADER_MINT_H
#define HEADER_MINT_H

#include <curl/curl.h>
#include <stdlib.h>
#include <string.h>

// Response data structure for curl callback
struct ResponseData {
    char *memory;
    size_t size;
};

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

// Callback function for writing header data
size_t WriteHeaderCallback(void *contents, size_t size, size_t nmemb, struct ResponseData *userp) {
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

// Function to set up Axiom trade request headers
struct curl_slist *set_axiom_request_headers(void) {
    struct curl_slist *headers = NULL;
    
    // Add all required headers for Axiom API
    headers = curl_slist_append(headers, "Accept: */*");
    headers = curl_slist_append(headers, "Accept-Encoding: gzip, deflate, br, zstd");
    headers = curl_slist_append(headers, "Accept-Language: en-US,en;q=0.8");
    headers = curl_slist_append(headers, "Cookie: auth-refresh-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWZyZXNoVG9rZW5JZCI6ImIyOGIzYmFkLTQ0ZDktNDViOS1iZmExLTBhNmRkZGJiYjdmNCIsImlhdCI6MTc1NDMzNDg5N30.hS0AOlhntJXtGlEQmpQo1W6u214XozXb6shm2YmAjBQ; auth-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoZW50aWNhdGVkVXNlcklkIjoiZWM5NWYxNTYtYjhkYi00MzBjLWIyMDgtNjcwZmJmOTBmMDViIiwiaWF0IjoxNzU1NTIyODIyLCJleHAiOjE3NTU1MjM3ODJ9.yYJKdvS1tsyR7hSXkeY-9WmMtXbPcs_kUs1j4DxcAew");
    headers = curl_slist_append(headers, "DNT: 1");
    headers = curl_slist_append(headers, "Next-Router-State-Tree: %5B%22%22%2C%7B%22children%22%3A%5B%22(platform)%22%2C%7B%22children%22%3A%5B%22meme%22%2C%7B%22children%22%3A%5B%5B%22pairAddress%22%2C%223WpJwy17ncxzhcrn7EZDAE9s2RmeexfjctW35e2NVEDn%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2C%22refetch%22%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D");
    headers = curl_slist_append(headers, "Priority: u=1, i");
    headers = curl_slist_append(headers, "Referer: https://axiom.trade/meme/3WpJwy17ncxzhcrn7EZDAE9s2RmeexfjctW35e2NVEDn");
    headers = curl_slist_append(headers, "RSC: 1");
    headers = curl_slist_append(headers, "Sec-CH-UA: \"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Brave\";v=\"138\"");
    headers = curl_slist_append(headers, "Sec-CH-UA-Mobile: ?1");
    headers = curl_slist_append(headers, "Sec-CH-UA-Platform: \"Android\"");
    headers = curl_slist_append(headers, "Sec-Fetch-Dest: empty");
    headers = curl_slist_append(headers, "Sec-Fetch-Mode: cors");
    headers = curl_slist_append(headers, "Sec-Fetch-Site: same-origin");
    headers = curl_slist_append(headers, "Sec-GPC: 1");
    headers = curl_slist_append(headers, "User-Agent: Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36");
    headers = curl_slist_append(headers, "X-Deployment-ID: dpl_kEvr5kj7rAH4KXEF6F1CerPmNWYH");
    
    return headers;
}

// Function to fetch token data from Axiom API
int header_fetch(void);

#endif // HEADER_MINT_H
