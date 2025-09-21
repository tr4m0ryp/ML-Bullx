#include <stdio.h>
#include <stdlib.h>
#include <curl/curl.h>
#include "api_request_v2.h"
#include "header_wallet_nonce.h"

int main() {
    printf("Testing local rotating proxy configuration...\n");
    
    // Initialize curl globally
    curl_global_init(CURL_GLOBAL_DEFAULT);
    
    // Test a simple API request with the new proxy configuration
    struct curl_slist *headers = set_axiom_request_headers_v2();
    if (!headers) {
        printf("Failed to set headers\n");
        return 1;
    }
    
    // Simple test payload
    const char* test_payload = "{\"test\": \"proxy_connection\"}";
    
    printf("Making test request through local rotating proxy (127.0.0.1:8889)...\n");
    
    int result = api_request_post("https://httpbin.org/post", headers, test_payload);
    
    if (result == 0) {
        printf("✓ Proxy connection successful!\n");
        printf("Response received and saved to response_data.txt\n");
    } else {
        printf("✗ Proxy connection failed with error code: %d\n", result);
    }
    
    // Cleanup
    curl_global_cleanup();
    
    return result;
}