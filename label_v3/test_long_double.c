#include <stdio.h>
#include "pair_info/pair_info.h"
#include "last_transaction/last_transaction.h"
#include "token_analysis/token_analysis.h"

int main() {
    printf("Testing long double conversion:\n");
    printf("Size of long double: %zu bytes\n", sizeof(long double));
    printf("Size of long: %zu bytes\n", sizeof(long));
    printf("Size of double: %zu bytes\n", sizeof(double));
    
    // Test PairInfoData structure
    PairInfoData pairData;
    pairData.initialLiquiditySol = 123456789012345678901234567890.0L;
    pairData.supply = 999999999999999999999999999999.0L;
    
    printf("\nPairInfoData test:\n");
    printf("initialLiquiditySol: %.0Lf\n", pairData.initialLiquiditySol);
    printf("supply: %.0Lf\n", pairData.supply);
    
    // Test LastTransactionData structure
    LastTransactionData transData;
    transData.liquiditySol = 123456789012345678901234567890.0L;
    transData.tokenAmount = 888888888888888888888888888888.0L;
    
    printf("\nLastTransactionData test:\n");
    printf("liquiditySol: %.0Lf\n", transData.liquiditySol);
    printf("tokenAmount: %.0Lf\n", transData.tokenAmount);
    
    // Test TokenAnalysisData structure
    TokenAnalysisData tokenData;
    tokenData.creatorRiskLevel = 777777777777777777777777777777.0L;
    tokenData.average_marketCap_TMCC = 555555555555555555555555555555.0L;
    
    printf("\nTokenAnalysisData test:\n");
    printf("creatorRiskLevel: %.0Lf\n", tokenData.creatorRiskLevel);
    printf("average_marketCap_TMCC: %.0Lf\n", tokenData.average_marketCap_TMCC);
    
    return 0;
}
