#include <stdio.h>
#include "header_wallet_nonce.h"
#include <curl/curl.h>
#include "api_request.h"


int main(char* walletAddress, char* nonce, char* signature){
    struct curl_slist *headers = set_axiom_request_headers();
    char payload[512];
    snprintf(payload, sizeof(payload), "{\"walletAddress\":\"%s\",\"signature\":\"%s\",\"nonce\":\"%s\",\"referrer\":null,\"allowRegistration\":true,\"isVerify\":false,\"forAddCredential\":false,\"allowLinking\":false}", walletAddress, signature, nonce);

    api_request("https://api6.axiom.trade/verify-wallet-v2", headers, payload);
    char *response = response_data.memory;
    printf("Response Data: %s\n", response);

    return 0;
}

