#ifndef _WALLET_GENERATION_H
#define _WALLET_GENERATION_H

#include <stdio.h>
#include <curl/curl.h>
#include <string.h>
#include <stdlib.h>


//Data structures
typedef struct {
    char* address;
    char* privateKey;
    char* mnemonic;
} Wallet;

//prototyping
char* generate_wallet();
Wallet filter_data(char* json_data);

//main function
Wallet wallet_generation(void){
    char* json_data = generate_wallet();
    //printf("Response: %s\n", json_data);
    Wallet wallet = filter_data(json_data);
    printf("Address: %s\n", wallet.address);
    printf("Private Key: %s\n", wallet.privateKey);
    printf("Mnemonic: %s\n", wallet.mnemonic);

    free(json_data);
    return wallet;
}

struct WriteResult {
    char* memory;
    size_t size;
};

static size_t WriteCallback(void* contents, size_t size, size_t nmemb, struct WriteResult* result) {
    size_t realsize = size * nmemb;
    char* ptr = realloc(result->memory, result->size + realsize + 1);
    result->memory = ptr;
    memcpy(&(result->memory[result->size]), contents, realsize);
    result->size += realsize;
    result->memory[result->size] = 0;
    return realsize;
}

char* generate_wallet(){
    CURL *hnd = curl_easy_init();
    struct WriteResult result;
    result.memory = malloc(1);
    result.size = 0;

    curl_easy_setopt(hnd, CURLOPT_CUSTOMREQUEST, "GET");
    curl_easy_setopt(hnd, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(hnd, CURLOPT_WRITEDATA, &result);
    curl_easy_setopt(hnd, CURLOPT_URL, "https://api.tatum.io/v3/solana/wallet");

    struct curl_slist *headers = NULL;
    headers = curl_slist_append(headers, "accept: application/json");
    headers = curl_slist_append(headers, "x-api-key: t-68c69c46ad765116b4b4f4eb-50e40a0ae881434ab1d7f0e6");
    curl_easy_setopt(hnd, CURLOPT_HTTPHEADER, headers);

    CURLcode ret = curl_easy_perform(hnd);
    curl_slist_free_all(headers);
    curl_easy_cleanup(hnd);
    return result.memory;
}


Wallet filter_data(char* json_data){
    Wallet wallet;
    
    //filter out mnemonic
    char* mnemonic_start = strstr(json_data, "\"mnemonic\":\"");
    if (mnemonic_start) {
        mnemonic_start += strlen("\"mnemonic\":\"");
        char* mnemonic_end = strstr(mnemonic_start, "\"");
        if (mnemonic_end) {
            size_t len = mnemonic_end - mnemonic_start;
            wallet.mnemonic = malloc(len + 1);
            strncpy(wallet.mnemonic, mnemonic_start, len);
            wallet.mnemonic[len] = '\0';
        }
    }
    
    //filter out the public address
    char* address_start = strstr(json_data, "\"address\":\"");
    if (address_start) {
        address_start += strlen("\"address\":\"");
        char* address_end = strstr(address_start, "\"");
        if (address_end) {
            size_t len = address_end - address_start;
            wallet.address = malloc(len + 1);
            strncpy(wallet.address, address_start, len);
            wallet.address[len] = '\0';
        }
    }

    //filter out the private key
    char* privateKey_start = strstr(json_data, "\"privateKey\":\"");
    if (privateKey_start) {
        privateKey_start += strlen("\"privateKey\":\"");
        char* privateKey_end = strstr(privateKey_start, "\"");
        if (privateKey_end) {
            size_t len = privateKey_end - privateKey_start;
            wallet.privateKey = malloc(len + 1);
            strncpy(wallet.privateKey, privateKey_start, len);
            wallet.privateKey[len] = '\0';
        }
    }
    return wallet;
}

#endif // _WALLET_GENERATION_H