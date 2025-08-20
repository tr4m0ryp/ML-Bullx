#ifndef DEV_TOKEN_H
#define DEV_TOKEN_H

#include <stdio.h>
#include "../api_request.h"


//protoypes
int api_request(char *pairAdress);

int dev_token(char *creator_address){
    char url[256];
    snprintf(url, sizeof(url), "https://api9.axiom.trade/dev-tokens-v2?devAddress=%s", creator_address);
    api_request(url);
    return 0;
}

#endif // DEV_TOKEN_H
