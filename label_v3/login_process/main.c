#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include "wallet_nonce.h"
#include "wallet_generation.h"
#include "signature.h"

int main(void){
    printf("Generating new cookies\n");
    printf("--------------\n");
    Wallet wallet; 
    wallet = wallet_generation();
    char *walletAddress = wallet.address;
    char *nonce = wallet_nonce(walletAddress);
    char *result = signature(wallet.privateKey, nonce);
    printf("Signature result:\n%s\n", result);


    //free
    free(wallet.address);
    free(wallet.privateKey);
    free(wallet.mnemonic);
    free(nonce);
    free(result);
    return 0;
}

