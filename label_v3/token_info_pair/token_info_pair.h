#ifndef TOKEN_INFO_PAIR_H
#define TOKEN_INFO_PAIR_H


#include <stdio.h>
#include "../api_request.h"

int token_info_pair(char *pairAddress) {
    char url[256];
    
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/token-info?pairAddress=%s", pairAddress);

    // Call the API request function with the constructed URL
    api_request(url);
    return 0;
}

#endif // TOKEN_INFO_PAIR_H