#!/usr/bin/env python3
"""
Configuration and Checkpoint Status Reporter.

Displays the current scraper configuration alongside checkpoint data to
provide a unified view of collection state:
- Loads the YAML configuration via config_loader to show the target count.
- Reads the simplified checkpoint JSON to report collected addresses.
- Computes and displays percentage progress and remaining count.

Author: ML-Bullx Team
Date: 2025-08-01
"""

# ============================================================================
# Standard Library Imports
# ============================================================================
import json
from datetime import datetime

# ============================================================================
# Local Imports
# ============================================================================
from data_pipeline.mint_addr.config_loader import load_config


# ============================================================================
# Status Reporting
# ============================================================================

def check_status():
    """Load configuration and checkpoint data, then print a status summary.

    Reads the configured target count and the current checkpoint file to
    display collected address count, last-updated timestamp, percentage
    progress, and remaining addresses needed to reach the target.
    """
    # Load config
    config = load_config()
    target = config.get('target_mint_count', 100000)

    print(f"Current target from config: {target:,} addresses")

    # Check checkpoint
    try:
        with open('mint_addresses_checkpoint_simple.json', 'r') as f:
            checkpoint = json.load(f)

        current_count = len(checkpoint.get('mint_addresses', []))
        timestamp = checkpoint.get('timestamp', 'Unknown')

        print(f"Current collected: {current_count:,} addresses")
        print(f"Last updated: {timestamp}")
        print(f"Progress: {current_count/target*100:.2f}%")
        print(f"Remaining: {target - current_count:,} addresses")

        if current_count >= target:
            print("[DONE] Target already reached!")
        else:
            print(f"Need {target - current_count:,} more addresses")

    except FileNotFoundError:
        print("[ERROR] No checkpoint file found")
    except Exception as e:
        print(f"[ERROR] Error reading checkpoint: {e}")


# ============================================================================
# Script Entry Point
# ============================================================================

if __name__ == "__main__":
    check_status()
