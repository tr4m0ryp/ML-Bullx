#ifndef _SIGNATURE_H
#define _SIGNATURE_H
#define _POSIX_C_SOURCE 200809L

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
    
    // Build the command to run the Node.js script
    snprintf(command, sizeof(command), 
             "cd /home/tramoryp/Tr4m0ryp_B/ML-Bullx/label_v3/login_process/web3_signature && "
             "node -e \"const main = require('./signature.js').main; main('%s', '%s');\"", 
             private_key, nonce);
    
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