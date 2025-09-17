#ifndef HEADER_H
#define HEADER_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h>

//header requirements for api request
struct curl_slist* set_axiom_request_headers(char* cookies) {
    struct curl_slist *headers = NULL;
    char* cookie_header = malloc(strlen("Cookie: ") + strlen(cookies) + 1);
    
    // Properly format the cookie header
    strcpy(cookie_header, "Cookie: ");
    strcat(cookie_header, cookies);

    // Add all required headers
    headers = curl_slist_append(headers, "Accept: application/json, text/plain, */*");
    headers = curl_slist_append(headers, "Accept-Encoding: gzip, deflate, br, zstd");
    headers = curl_slist_append(headers, "Accept-Language: en-US,en;q=0.8");
    //headers = curl_slist_append(headers, "Cookie: auth-refresh-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWZyZXNoVG9rZW5JZCI6IjY5OGZhM2RlLTk3NTUtNDQ5MS1iNzgyLWMxZWI5MTA2YTY2ZCIsImlhdCI6MTc1ODEyMzg2MH0.6d1yTHuMbQnfrPRCoMFnEjvrzj9DqKR_UuMxiaNZUQs; auth-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoZW50aWNhdGVkVXNlcklkIjoiMGJjMzA5YWYtNjYwZS00OWE2LWJkMjItYWQ0OWJkZWZmMGZjIiwiaWF0IjoxNzU4MTIzODYwLCJleHAiOjE3NTgxMjQ4MjB9.qooKdqiivm0bl4-58SCVuWZMHGzG3gie55KMb2-jgfc");
    headers = curl_slist_append(headers, cookie_header);
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
    
    // Free the allocated cookie header string as it's copied into the curl_slist
    free(cookie_header);
    
    return headers;
}

#endif // HEADER_H