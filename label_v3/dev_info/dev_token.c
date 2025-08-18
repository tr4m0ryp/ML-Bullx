#include <stdio.h>
#include "../api_request.h"


//protoypes
int api_request(char *pairAdress);

int main(void){
    api_request("https://api9.axiom.trade/dev-tokens-v2?devAddress=8dcBNsAU264EgNhtjzw21GmLVx5nDqvTKSJbymaiNrok");
    return 0;
}
