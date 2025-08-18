#include <stdio.h>
#include "../api_request.h"

int main(void){
    char *pairAdress = "4obJCWMWJFPhBZL3EyBr1DPbe87uo8JmFahUVMfKAGUq";
    char url[256];
    
    // Construct the URL using snprintf (safer than sprintf)
    snprintf(url, sizeof(url), "https://api9.axiom.trade/token-info?pairAddress=%s", pairAdress);

    // Call the API request function with the constructed URL
    api_request(url);
    return 0;
}