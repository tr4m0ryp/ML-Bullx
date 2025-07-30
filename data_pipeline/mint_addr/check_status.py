#!/usr/bin/env python3
"""
Check current scraper status and configuration
"""

import json
from config_loader import load_config
from datetime import datetime

def check_status():
    # Load config
    config = load_config()
    target = config.get('target_mint_count', 100000)
    
    print(f"🎯 Current target from config: {target:,} addresses")
    
    # Check checkpoint
    try:
        with open('mint_addresses_checkpoint_simple.json', 'r') as f:
            checkpoint = json.load(f)
        
        current_count = len(checkpoint.get('mint_addresses', []))
        timestamp = checkpoint.get('timestamp', 'Unknown')
        
        print(f"📊 Current collected: {current_count:,} addresses")
        print(f"⏰ Last updated: {timestamp}")
        print(f"📈 Progress: {current_count/target*100:.2f}%")
        print(f"🎯 Remaining: {target - current_count:,} addresses")
        
        if current_count >= target:
            print("✅ Target already reached!")
        else:
            print(f"🔄 Need {target - current_count:,} more addresses")
            
    except FileNotFoundError:
        print("❌ No checkpoint file found")
    except Exception as e:
        print(f"❌ Error reading checkpoint: {e}")

if __name__ == "__main__":
    check_status()
