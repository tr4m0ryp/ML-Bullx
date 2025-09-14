#ifndef _WALLET_NONCE_H
#define _WALLET_NONCE_H

#include <stdio.h>
#include "header_wallet_nonce.h"
#include <curl/curl.h>
#include "api_request.h"

char* wallet_nonce(char* walletAddress){
    struct curl_slist *headers = set_axiom_request_headers();
    char payload[256];
    snprintf(payload, sizeof(payload), "{\"walletAddress\":\"%s\"}", walletAddress);

    api_request("https://api9.axiom.trade/wallet-nonce", headers, payload);
    //printf("Response Data: %s", response_data.memory);
    char *nonce = response_data.memory;
    //printf("Nonce: %s\n", nonce);
    return nonce;
}

#endif // _WALLET_NONCE_H