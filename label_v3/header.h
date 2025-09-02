#ifndef HEADER_H
#define HEADER_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h>

//header requirements for api request
struct curl_slist* set_axiom_request_headers(void) {
    struct curl_slist *headers = NULL;
    
    // Add all required headers
    headers = curl_slist_append(headers, "Accept: application/json, text/plain, */*");
    headers = curl_slist_append(headers, "Accept-Encoding: gzip, deflate, br, zstd");
    headers = curl_slist_append(headers, "Accept-Language: en-US,en;q=0.8");
    //headers = curl_slist_append(headers, "Cookie: auth-refresh-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWZyZXNoVG9rZW5JZCI6ImIyOGIzYmFkLTQ0ZDktNDViOS1iZmExLTBhNmRkZGJiYjdmNCIsImlhdCI6MTc1NDMzNDg5N30.hS0AOlhntJXtGlEQmpQo1W6u214XozXb6shm2YmAjBQ; auth-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoZW50aWNhdGVkVXNlcklkIjoiZWM5NWYxNTYtYjhkYi00MzBjLWIyMDgtNjcwZmJmOTBmMDViIiwiaWF0IjoxNzU1NTIyODIyLCJleHAiOjE3NTU1MjM3ODJ9.yYJKdvS1tsyR7hSXkeY-9WmMtXbPcs_kUs1j4DxcAew");
    headers = curl_slist_append(headers, "Cookie: auth-refresh-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWZyZXNoVG9rZW5JZCI6Ijg4NTIxMjk5LTBlMzItNGNjYi05ODViLTdmOWNlMGUwNTNmYSIsImlhdCI6MTc1Njc5NDc5NX0.r2tQ_CE3XdSW9iaDrYF1Am5SGwZnFkLZFMTTB-vg5bk; auth-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoZW50aWNhdGVkVXNlcklkIjoiMzM1NjQxZTItNDQyNi00YjY5LTljYzMtNDA3ZTEzZWRlZmMyIiwiaWF0IjoxNzU2Nzk0Nzk1LCJleHAiOjE3NTY3OTU3NTV9.gGtKYAiU1UKbcgcJmKtgCKi-A5J16KcCYNkzYWuPzqg");
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

#endif // HEADER_H