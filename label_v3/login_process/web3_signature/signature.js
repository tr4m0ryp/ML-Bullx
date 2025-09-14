
const { Keypair } = require('@solana/web3.js');
const nacl = require('tweetnacl');
const bs58 = require('bs58').default;

// Sign message with keypair
async function signMessage_first(keypair, Nonce) {
    const message = "By signing, you agree to Axiom's Terms of Use & Privacy Policy (axiom.trade/legal). \n\n Nonce:" + Nonce;
    const messageBytes = new TextEncoder().encode(message);
    const signature = nacl.sign.detached(messageBytes, keypair.secretKey);
    
    return {
        signature: Array.from(signature),
        publicKey: keypair.publicKey.toString(),
        message: message
    };
}


// Import keypair from private key
function importKeypair(privateKey) {
    let secretKey;
    
    try {
        // Try Base58 format first (most common for Solana)
        if (privateKey.length > 40 && !privateKey.includes(',') && !privateKey.startsWith('[')) {
            secretKey = bs58.decode(privateKey);
        } else if (privateKey.startsWith('[')) {
            // JSON array format
            secretKey = new Uint8Array(JSON.parse(privateKey));
        } else if (privateKey.includes(',')) {
            // Comma-separated format
            secretKey = new Uint8Array(privateKey.split(',').map(n => parseInt(n.trim())));
        } else {
            // Hexadecimal format
            const hexArray = privateKey.match(/.{1,2}/g);
            secretKey = new Uint8Array(hexArray.map(byte => parseInt(byte, 16)));
        }
        
        // Validate secret key length (should be 64 bytes for Solana)
        if (secretKey.length !== 64) {
            throw new Error(`Invalid secret key length: ${secretKey.length}. Expected 64 bytes.`);
        }
        
        return Keypair.fromSecretKey(secretKey);
    } catch (error) {
        throw new Error(`Failed to import keypair: ${error.message}`);
    }
}

// Main function
async function main(privateKey, nonce) {
    
    try {
        const keypair = importKeypair(privateKey);
        const result = await signMessage_first(keypair, nonce);
        
        //console log results
        console.log(result.signature.map(b => b.toString(16).padStart(2, '0')).join(''));
        //console.log('Message_1:\n', result.message);

        
        
        return result;
    } catch (error) {
        console.error('Error:', error.message);
    }
}

// Export functions for use in other modules
module.exports = {
    signMessage_first,
    importKeypair,
    main
};