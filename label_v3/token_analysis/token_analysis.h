#ifndef TOKEN_ANALYSIS_H
#define TOKEN_ANALYSIS_H

#include <stdio.h>
#include "../api_request.h"

int token_analysis(char *devAddress, char *tokenTicker) {
    char url[256];
    
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/token-analysis?devAddress=%s&tokenTicker=%s", devAddress, tokenTicker);
    printf("URL: %s\n", url); // Debugging line to check the URL    
    // Call the API request function with the constructed URL
    api_request(url);
    return 0;
}

#endif // TOKEN_ANALYSIS_H
