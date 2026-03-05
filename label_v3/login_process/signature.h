#define _POSIX_C_SOURCE 200809L

#ifndef _SIGNATURE_H
#define _SIGNATURE_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>



char* signature(const char* private_key, const char* nonce) {
    char command[2048];
    char* result = NULL;
    FILE* fp;
    char buffer[4096];
    size_t total_length = 0;
    
    // Build the path relative to this source file's location.
    // __FILE__ resolves to label_v3/login_process/signature.h at compile time.
    // The web3_signature directory sits alongside this header.
    const char *script_dir = __FILE__;
    char dir_buf[1024];
    strncpy(dir_buf, script_dir, sizeof(dir_buf) - 1);
    dir_buf[sizeof(dir_buf) - 1] = '\0';
    char *last_slash = strrchr(dir_buf, '/');
    if (last_slash) *last_slash = '\0';

    snprintf(command, sizeof(command),
             "cd %s/web3_signature && "
             "node -e \"const main = require('./signature.js').main; main('%s', '%s');\"",
             dir_buf, private_key, nonce);
    
    // Execute the command and capture output
    fp = popen(command, "r");
    if (fp == NULL) {
        fprintf(stderr, "Error: Failed to execute Node.js script\n");
        return NULL;
    }
    
    // Read the output
    result = malloc(4096);
    if (result == NULL) {
        pclose(fp);
        return NULL;
    }
    
    result[0] = '\0';
    while (fgets(buffer, sizeof(buffer), fp) != NULL) {
        size_t buffer_len = strlen(buffer);
        if (total_length + buffer_len >= 4095) {
            break; // Prevent buffer overflow
        }
        strcat(result, buffer);
        total_length += buffer_len;
    }
    
    pclose(fp);
    
    // Remove trailing newline if present
    if (total_length > 0 && result[total_length - 1] == '\n') {
        result[total_length - 1] = '\0';
    }
    
    return result;
}

#endif // _SIGNATURE_H