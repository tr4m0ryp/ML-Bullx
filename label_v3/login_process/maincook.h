#ifndef _MAINCOOK_H
#define _MAINCOOK_H


#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include "wallet_nonce.h"
#include "wallet_generation.h"
#include "signature.h"
#include "verify_wallet_v2.h"

int main(void){
    printf("Generating new cookies\n");
    printf("--------------\n");
    Wallet wallet; 
    wallet = wallet_generation();
    char *walletAddress = wallet.address;
    char *nonce = wallet_nonce(walletAddress);
    char *signature_v1 = signature(wallet.privateKey, nonce);
    printf("Signature result:\n%s\n", signature_v1);
    VerifyWalletResult *result = verify_wallet(walletAddress, signature_v1, nonce);

    free(wallet.address);
    free(wallet.privateKey);
    free(wallet.mnemonic);
    free(nonce);
    free(signature_v1);
    free_verify_wallet_result(result);
    return 0;
}

#endif // _MAINCOOK_H
