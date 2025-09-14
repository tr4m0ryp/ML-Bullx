#ifndef _VERIFY_WALLET_V2_H
#define _VERIFY_WALLET_V2_H

#include <stdio.h>
#include "header_wallet_nonce.h"
#include <curl/curl.h>
#include "api_request.h"


char* verify_wallet(char* walletAddress, char* signature, char* nonce){
    struct curl_slist *headers = set_axiom_request_headers();
    char payload[512];
    snprintf(payload, sizeof(payload), "{\"walletAddress\":\"%s\",\"signature\":\"%s\",\"nonce\":\"%s\",\"referrer\":null,\"allowRegistration\":true,\"isVerify\":false,\"forAddCredential\":false,\"allowLinking\":false}", walletAddress, signature, nonce);
    printf("PAYLOAD: %s\n", payload);
    api_request("https://api9.axiom.trade/verify-wallet-v2", headers, payload);
    char *response = response_data.memory;
    printf("Response Data: %s\n", response);
    if(strcmp(response,"{\"error\":\"Too many signup requests from your region today, you can still use login\"}") == 0){
        printf("Too many signup requests from your region today, you can still use login\n");
    }
    return response;
}

#endif // _VERIFY_WALLET_V2_H