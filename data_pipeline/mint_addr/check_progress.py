#!/usr/bin/env python3
"""
Quick check script to see current scraping progress and restart if needed.
"""

import json
import os
import subprocess
import sys
from datetime import datetime

def check_progress():
    """Check current scraping progress."""
    
    print("Checking current scraping progress...")
    print("="*50)
    
    # Check checkpoint file
    checkpoint_file = "mint_addresses_checkpoint_simple.json"
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'r') as f:
                data = json.load(f)
            
            count = data.get('count', 0)
            timestamp = data.get('timestamp', 'Unknown')
            age_range = data.get('age_range', 'Unknown')
            
            print(f"Checkpoint found: {checkpoint_file}")
            print(f"Addresses collected: {count:,}")
            print(f"Last updated: {timestamp}")
            print(f"Age range filter: {age_range}")
            
            # Calculate progress
            target = 10_000_000
            progress_pct = (count / target) * 100
            
            print(f"Progress: {progress_pct:.2f}% of {target:,} target")
            
            # Check CSV file
            csv_file = "solana_mint_addresses_3months_to_1year.csv"
            if os.path.exists(csv_file):
                print(f"CSV export: {csv_file}")
                
            # Check log file
            log_file = "mint_scraper_simple.log"
            if os.path.exists(log_file):
                print(f"Log file: {log_file}")
                
                # Show last few lines
                print("\nRecent log entries:")
                try:
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                        for line in lines[-5:]:
                            print(f"   {line.strip()}")
                except Exception as e:
                    print(f"   Error reading log: {e}")
            
            print()
            
            if count < target:
                print(f"[WARN] Still need {target - count:,} more addresses to reach target")
                print("Run the scraper again to continue collecting")
            else:
                print("[DONE] Target reached!")
                
        except Exception as e:
            print(f"[ERROR] Error reading checkpoint: {e}")
    else:
        print("No checkpoint found - scraping not started or checkpoint deleted")
        print("Run ./run_scraper.sh to start collecting addresses")
    
    print()

def main():
    """Main function."""
    check_progress()
    
    # Ask if user wants to continue scraping
    if len(sys.argv) > 1 and sys.argv[1] == "--continue":
        print("Continuing scraping...")
        subprocess.run(["./run_scraper.sh"], check=True)

if __name__ == "__main__":
    main()
