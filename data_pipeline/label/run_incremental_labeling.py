#!/usr/bin/env python3
"""
Enhanced Token Labeling with Incremental CSV Saving

This script demonstrates how to use the enhanced token labeler that saves
results incrementally to CSV. If the process crashes or is interrupted,
you can restart it and it will resume from where it left off.

Usage:
    python run_incremental_labeling.py <input_csv> <output_csv> [batch_size]

Example:
    python run_incremental_labeling.py tokens_to_label.csv labeled_tokens.csv 10
"""

import asyncio
import argparse
import logging
import sys
import os
from pathlib import Path
import pandas as pd

from token_labeler import EnhancedTokenLabeler

def setup_logging():
    """Setup logging with both file and console output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("incremental_labeling.log"),
            logging.StreamHandler()
        ]
    )

async def main():
    """Main function to run incremental token labeling."""
    parser = argparse.ArgumentParser(description="Run incremental token labeling")
    parser.add_argument("input_csv", help="Input CSV file with mint addresses")
    parser.add_argument("output_csv", help="Output CSV file for labeled tokens")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for processing (default: 10)")
    parser.add_argument("--config", help="Path to config file (optional)")
    
    args = parser.parse_args()
    
    # Validate input file exists
    if not Path(args.input_csv).exists():
        print(f"Error: Input file '{args.input_csv}' not found")
        sys.exit(1)
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting incremental token labeling")
    logger.info(f"Input: {args.input_csv}")
    logger.info(f"Output: {args.output_csv}")
    logger.info(f"Batch size: {args.batch_size}")
    
    try:
        # Initialize the enhanced token labeler
        async with EnhancedTokenLabeler(config_path=args.config) as labeler:
            # Get initial stats
            stats = labeler.get_processing_stats(args.input_csv, args.output_csv)
            logger.info(f"Initial processing stats: {stats}")
            
            if stats["remaining"] == 0:
                logger.info("All tokens have already been processed!")
                return
            
            # Run the labeling process with incremental saving
            await labeler.label_tokens_from_csv(
                inp=args.input_csv,
                out=args.output_csv,
                batch=args.batch_size
            )
            
            # Load the final results from the CSV for the report
            if os.path.exists(args.output_csv):
                try:
                    result_df = pd.read_csv(args.output_csv)
                except pd.errors.EmptyDataError:
                    result_df = pd.DataFrame(columns=['mint_address', 'label'])
            else:
                result_df = pd.DataFrame(columns=['mint_address', 'label'])
            
            # Final summary
            final_stats = labeler.get_processing_stats(args.input_csv, args.output_csv)
            logger.info(f"Processing completed!")
            logger.info(f"Final stats: {final_stats}")
            logger.info(f"Results saved to: {args.output_csv}")
            
            # Show distribution of labels
            if not result_df.empty:
                label_counts = result_df["label"].value_counts()
                logger.info("Label distribution:")
                for label, count in label_counts.items():
                    percentage = (count / len(result_df)) * 100
                    logger.info(f"  {label}: {count} ({percentage:.1f}%)")
    
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Progress has been saved.")
        logger.info(f"To resume, run the same command again: {' '.join(sys.argv)}")
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        logger.info("Check the log file for detailed error information.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
