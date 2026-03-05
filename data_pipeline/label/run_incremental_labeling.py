#!/usr/bin/env python3
"""
Enhanced Token Labeling with Incremental CSV Saving

Saves results incrementally to CSV and can resume from existing progress.

Usage:
    python run_incremental_labeling.py <input_csv> <output_csv> [--batch-size N] [--reset]

Examples:
    python run_incremental_labeling.py input.csv output.csv --batch-size 10
    python run_incremental_labeling.py input.csv output.csv --batch-size 10 --reset
"""

import asyncio
import argparse
import logging
import sys
import os
from pathlib import Path
import pandas as pd

# Import the enhanced token labeler
from data_pipeline.label.token_labeler import EnhancedTokenLabeler

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
    parser.add_argument("--reset", action="store_true", help="Reset progress and start from the beginning (ignores existing output)")
    parser.add_argument("--allow-insufficient", action="store_true", help="Allow coercing partial data into labels (default: use INSUFFICIENT_DATA label)")
    parser.add_argument("--limit", type=int, help="Limit number of tokens to process (for debugging)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and failure tracking")
    
    args = parser.parse_args()
    
    # Validate input file exists
    if not Path(args.input_csv).exists():
        print(f"Error: Input file '{args.input_csv}' not found")
        sys.exit(1)
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("ENHANCED TOKEN LABELING")
    logger.info("=" * 80)
    logger.info("Input: %s", args.input_csv)
    logger.info("Output: %s", args.output_csv)
    logger.info("Batch size: %d", args.batch_size)
    if args.limit:
        logger.info("LIMIT MODE: Processing only %d tokens", args.limit)
    if args.reset:
        logger.info("RESET MODE: Starting from the beginning, ignoring existing progress")
    else:
        logger.info("RESUME MODE: Continuing from existing progress if available")
    if args.allow_insufficient:
        logger.info("ALLOW INSUFFICIENT: Will coerce partial data into labels")
    else:
        logger.info("ROBUST MODE: Will use INSUFFICIENT_DATA label for incomplete data")
    if args.debug:
        logger.info("DEBUG MODE: Enhanced logging and failure tracking enabled")
    logger.info("=" * 80)
    
    try:
        # Initialize the enhanced token labeler
        async with EnhancedTokenLabeler(config_path=args.config) as labeler:
            # Get initial stats (before reset if applicable)
            if not args.reset:
                stats = labeler.get_processing_stats(args.input_csv, args.output_csv)
                logger.info("Initial processing stats: %s", stats)

                if stats["remaining"] == 0:
                    logger.info("All tokens have already been processed.")
                    return
            
            # Set labeler options based on args
            labeler.allow_insufficient_data = args.allow_insufficient
            labeler.debug_mode = args.debug
            
            # Run the labeling process with incremental saving
            await labeler.label_tokens_from_csv(
                inp=args.input_csv,
                out=args.output_csv,
                batch=args.batch_size,
                reset_progress=args.reset,
                limit=args.limit
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
            logger.info("=" * 80)
            logger.info("PROCESSING COMPLETED")
            logger.info("=" * 80)
            logger.info("Final stats: %s", final_stats)
            logger.info("Results saved to: %s", args.output_csv)

            # Show distribution of labels
            if not result_df.empty:
                logger.info("Label distribution:")
                label_counts = result_df["label"].value_counts()
                for label, count in label_counts.items():
                    percentage = (count / len(result_df)) * 100
                    logger.info(f"   {label}: {count} ({percentage:.1f}%)")
            logger.info("=" * 80)
    
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Progress has been saved.")
        logger.info("To resume, run the same command again: %s", ' '.join(sys.argv))
    except Exception as e:
        logger.error("Error during processing: %s", e)
        logger.info("Check the log file for detailed error information.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
