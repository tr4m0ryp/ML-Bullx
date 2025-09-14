#include <stdio.h>
#include "wallet_nonce.h"
#include "wallet_generation.h"

int main(void){
    printf("Generating new cookies\n");
    printf("--------------\n");
    Wallet wallet; 
    wallet = wallet_generation();
    char *walletAddress = wallet.address;
    char *nonce = wallet_nonce(walletAddress);


    //free
    free(wallet.address);
    free(wallet.privateKey);
    free(wallet.mnemonic);
    return 0;
}

