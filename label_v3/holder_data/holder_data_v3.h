#ifndef HOLDER_DATA_V3_H
#define HOLDER_DATA_V3_H

#include <stdio.h>
#include "../api_request.h"

int holder_data(char *pairAddress){
    char url[256];
    
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/holder-data-v3?pairAddress=%s", pairAddress);

    // Call the API request function with the constructed URL
    api_request(url);
    return 0;
}

#endif // HOLDER_DATA_V3_H


//unvalid for csv and labelment