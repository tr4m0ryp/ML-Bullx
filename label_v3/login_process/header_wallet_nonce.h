#ifndef HEADER_WALLET_NONCE_H
#define HEADER_WALLET_NONCE_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h>

//header requirements for api request
struct curl_slist* set_axiom_request_headers_v2(void) {
    struct curl_slist *headers = NULL;

    // Add all required headers for wallet-nonce endpoint
    headers = curl_slist_append(headers, "Accept: application/json, text/plain, */*");
    headers = curl_slist_append(headers, "Accept-Encoding: gzip, deflate, br, zstd");
    headers = curl_slist_append(headers, "Accept-Language: en-US,en;q=0.7");
    headers = curl_slist_append(headers, "Content-Type: application/json");
    headers = curl_slist_append(headers, "Origin: https://axiom.trade");
    headers = curl_slist_append(headers, "Priority: u=1, i");
    headers = curl_slist_append(headers, "Referer: https://axiom.trade/");
    headers = curl_slist_append(headers, "Sec-CH-UA: \"Not;A=Brand\";v=\"99\", \"Brave\";v=\"139\", \"Chromium\";v=\"139\"");
    headers = curl_slist_append(headers, "Sec-CH-UA-Mobile: ?0");
    headers = curl_slist_append(headers, "Sec-CH-UA-Platform: \"Linux\"");
    headers = curl_slist_append(headers, "Sec-Fetch-Dest: empty");
    headers = curl_slist_append(headers, "Sec-Fetch-Mode: cors");
    headers = curl_slist_append(headers, "Sec-Fetch-Site: same-site");
    headers = curl_slist_append(headers, "Sec-GPC: 1");
    headers = curl_slist_append(headers, "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36");
    
    return headers;
}

#endif // HEADER_WALLET_NONCE_H