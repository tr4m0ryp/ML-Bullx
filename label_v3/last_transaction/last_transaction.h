#ifndef LAST_TRANSACTION_H
#define LAST_TRANSACTION_H

#include <stdio.h>
#include "../api_request.h"

int last_transaction(char *pairAddress){
    char url[256];
    
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/last-transaction?pairAddress=%s", pairAddress);

    // Call the API request function with the constructed URL
    api_request(url);
    return 0;
}

#endif // LAST_TRANSACTION_H