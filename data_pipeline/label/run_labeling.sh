#!/bin/bash

# Token Labeling Script Runner
# Usage: ./run_labeling.sh [options]

set -e

echo "🏷️  Solana Token Labeling Pipeline"
echo "================================="

# Default values
INPUT_FILE="../mint_addr/solana_mint_addresses_3months_to_1year.csv"
OUTPUT_FILE="labels.csv"
SAMPLE_SIZE=""
BATCH_SIZE=50

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --input)
            INPUT_FILE="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --sample)
            SAMPLE_SIZE="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --install-deps)
            echo "📦 Installing dependencies..."
            pip install -r requirements.txt
            shift
            ;;
        --test)
            echo "🧪 Running test mode with sample data..."
            SAMPLE_SIZE=100
            OUTPUT_FILE="labels_test.csv"
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --input FILE       Input CSV file path (default: $INPUT_FILE)"
            echo "  --output FILE      Output CSV file path (default: $OUTPUT_FILE)"
            echo "  --sample N         Process only first N tokens"
            echo "  --batch-size N     Batch size for processing (default: $BATCH_SIZE)"
            echo "  --install-deps     Install required Python packages"
            echo "  --test             Run in test mode with 100 sample tokens"
            echo "  --help             Show this help message"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check if input file exists
if [[ ! -f "$INPUT_FILE" ]]; then
    echo "❌ Error: Input file $INPUT_FILE not found"
    exit 1
fi

# Create output directory if it doesn't exist
OUTPUT_DIR=$(dirname "$OUTPUT_FILE")
mkdir -p "$OUTPUT_DIR"

echo "📁 Input file: $INPUT_FILE"
echo "📁 Output file: $OUTPUT_FILE"
echo "📊 Batch size: $BATCH_SIZE"

if [[ -n "$SAMPLE_SIZE" ]]; then
    echo "🔬 Sample size: $SAMPLE_SIZE tokens"
fi

echo ""
echo "🚀 Starting token labeling process..."
echo ""

# Build Python command
PYTHON_CMD="python token_labeler.py --input \"$INPUT_FILE\" --output \"$OUTPUT_FILE\" --batch-size $BATCH_SIZE"

if [[ -n "$SAMPLE_SIZE" ]]; then
    PYTHON_CMD="$PYTHON_CMD --sample $SAMPLE_SIZE"
fi

# Run the labeling process
eval $PYTHON_CMD

# Check if output file was created
if [[ -f "$OUTPUT_FILE" ]]; then
    echo ""
    echo "✅ Labeling completed successfully!"
    echo "📊 Results saved to: $OUTPUT_FILE"
    echo ""
    
    # Show basic statistics
    echo "📈 Label Distribution:"
    python -c "
import pandas as pd
df = pd.read_csv('$OUTPUT_FILE')
print(df['label'].value_counts().to_string())
print(f'\nTotal tokens processed: {len(df)}')
print(f'Timestamp: {df[\"labeled_at\"].iloc[0] if \"labeled_at\" in df.columns else \"N/A\"}')
"
else
    echo "❌ Error: Output file was not created"
    exit 1
fi

echo ""
echo "🎉 Token labeling pipeline completed!"
