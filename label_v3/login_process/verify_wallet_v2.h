#ifndef _VERIFY_WALLET_V2_H
#define _VERIFY_WALLET_V2_H

#include <stdio.h>
#include "header_wallet_nonce.h"
#include <curl/curl.h>
#include "api_request.h"

typedef struct{
    char *response;
    char *cookies;
} VerifyWalletResult;

VerifyWalletResult* verify_wallet(char* walletAddress, char* signature, char* nonce){
    VerifyWalletResult* result = malloc(sizeof(VerifyWalletResult));
    if (!result) {
        return NULL;
    }
    
    struct curl_slist *headers = set_axiom_request_headers();
    char payload[512];
    snprintf(payload, sizeof(payload), "{\"walletAddress\":\"%s\",\"signature\":\"%s\",\"nonce\":\"%s\",\"referrer\":null,\"allowRegistration\":true,\"isVerify\":false,\"forAddCredential\":false,\"allowLinking\":false}", walletAddress, signature, nonce);
    printf("PAYLOAD: %s\n", payload);
    api_request("https://api9.axiom.trade/verify-wallet-v2", headers, payload);
    
    //response api
    result->response = strdup(response_data.memory);
    printf("Response Data: %s\n", result->response);
    if(strcmp(result->response,"{\"error\":\"Too many signup requests from your region today, you can still use login\"}") == 0){
        printf("Too many signup requests from your region today, you can still use login\n");
    }

    //response cookies
    result->cookies = extract_cookies_from_headers();
    if (result->cookies) {
        printf("Cookies: %s\n", result->cookies);
    } else {
        printf("No cookies found in response headers\n");
    }

    return result;
}

// Function to free VerifyWalletResult
void free_verify_wallet_result(VerifyWalletResult* result) {
    if (result) {
        if (result->response) {
            free(result->response);
        }
        if (result->cookies) {
            free(result->cookies);
        }
        free(result);
    }
}

#endif // _VERIFY_WALLET_V2_H