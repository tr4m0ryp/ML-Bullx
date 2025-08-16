#ifndef AXIOM_REQUEST_HEADERS_H
#define AXIOM_REQUEST_HEADERS_H

#include <curl/curl.h>

// Function to set all Axiom API headers
struct curl_slist* set_axiom_request_headers(void) {
    struct curl_slist *headers = NULL;
    
    // Add all required headers
    headers = curl_slist_append(headers, "Accept: application/json, text/plain, */*");
    headers = curl_slist_append(headers, "Accept-Encoding: gzip, deflate, br, zstd");
    headers = curl_slist_append(headers, "Accept-Language: en-US,en;q=0.8");
    headers = curl_slist_append(headers, "Cookie: auth-refresh-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWZyZXNoVG9rZW5JZCI6ImIyOGIzYmFkLTQ0ZDktNDViOS1iZmExLTBhNmRkZGJiYjdmNCIsImlhdCI6MTc1NDMzNDg5N30.hS0AOlhntJXtGlEQmpQo1W6u214XozXb6shm2YmAjBQ; auth-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoZW50aWNhdGVkVXNlcklkIjoiZWM5NWYxNTYtYjhkYi00MzBjLWIyMDgtNjcwZmJmOTBmMDViIiwiaWF0IjoxNzU1MTI0NTg5LCJleHAiOjE3NTUxMjU1NDl9.16GUJN7Asx2u29hfvz1DQzdsktexI8GlT4BOeyxMAn4");
    headers = curl_slist_append(headers, "DNT: 1");
    headers = curl_slist_append(headers, "Origin: https://axiom.trade");
    headers = curl_slist_append(headers, "Priority: u=1, i");
    headers = curl_slist_append(headers, "Referer: https://axiom.trade/");
    headers = curl_slist_append(headers, "Sec-CH-UA: \"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Brave\";v=\"138\"");
    headers = curl_slist_append(headers, "Sec-CH-UA-Mobile: ?1");
    headers = curl_slist_append(headers, "Sec-CH-UA-Platform: \"Android\"");
    headers = curl_slist_append(headers, "Sec-Fetch-Dest: empty");
    headers = curl_slist_append(headers, "Sec-Fetch-Mode: cors");
    headers = curl_slist_append(headers, "Sec-Fetch-Site: same-site");
    headers = curl_slist_append(headers, "Sec-GPC: 1");
    headers = curl_slist_append(headers, "User-Agent: Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36");
    
    return headers;
}

#endif
