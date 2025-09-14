
const { Keypair } = require('@solana/web3.js');
const nacl = require('tweetnacl');

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

//sign message second message
async function SignMessage_second(keypair){
    const message = "Hello from ML-Bullx!";
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
    
    if (privateKey.startsWith('[')) {
        secretKey = new Uint8Array(JSON.parse(privateKey));
    } else if (privateKey.includes(',')) {
        secretKey = new Uint8Array(privateKey.split(',').map(n => parseInt(n.trim())));
    } else {
        const hexArray = privateKey.match(/.{1,2}/g);
        secretKey = new Uint8Array(hexArray.map(byte => parseInt(byte, 16)));
    }
    
    return Keypair.fromSecretKey(secretKey);
}

// Main function
async function main(privateKey) {
    
    try {
        const keypair = importKeypair(privateKey);
        const result = await signMessage_first(keypair);
        const result_2 = await SignMessage_second(keypair);
        /*
        console.log('Result:');
        console.log('Signature:', result.signature.map(b => b.toString(16).padStart(2, '0')).join(''));
        console.log('Public Key:', result.publicKey);
        console.log('Message:', result.message);

        console.log('Result 2:');
        console.log('Signature:', result_2.signature.map(b => b.toString(16).padStart(2, '0')).join(''));
        console.log('Public Key:', result_2.publicKey);
        console.log('Message:', result_2.message);
        */
        
        return result;
    } catch (error) {
        console.error('Error:', error.message);
    }
}


main('GbefH4GeKUQYDAW16GPYvCXCn7SnDcEhQ1vyZqvzmbq6Quh99RFVpoeA5KVXKDPipfz1YTFnUtLJTjx3Gd5G1Uv');