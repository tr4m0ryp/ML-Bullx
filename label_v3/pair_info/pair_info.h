#ifndef PAIR_INFO_H
#define PAIR_INFO_H

#include <stdio.h>
#include "../api_request.h"

typedef struct{
    int initialLiquiditySol;
    int initialLiquidityToken;
    int supply;
    float top10Holders;
    float lpBurned;
    bool has_freezeAuthority;
    int slot;
} labelAlgorithmData;

int api_request(char *url);

int pair_info(char *pairAddress){
    char url[256];
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/pair-info?pairAddress=%s", pairAddress);
    
    // Call the API request function with the constructed URL
    api_request(url);
    return 0;
}

#endif // PAIR_INFO_H