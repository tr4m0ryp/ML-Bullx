#!/bin/bash

# Progress Monitor for Token Labeling
echo "🏷️  Token Labeling Progress Monitor"
echo "=================================="

TOTAL_TOKENS=287869
OUTPUT_FILE="labels_final.csv"

while true; do
    # Check if process is still running
    if pgrep -f "simple_labeler.py" > /dev/null; then
        # Count processed tokens if output file exists
        if [ -f "$OUTPUT_FILE" ]; then
            PROCESSED=$(wc -l < "$OUTPUT_FILE" 2>/dev/null || echo "1")
            PROCESSED=$((PROCESSED - 1))  # Subtract header line
            if [ $PROCESSED -gt 0 ]; then
                PERCENTAGE=$(echo "scale=2; $PROCESSED * 100 / $TOTAL_TOKENS" | bc -l 2>/dev/null || echo "0")
                echo "📊 Progress: $PROCESSED / $TOTAL_TOKENS tokens ($PERCENTAGE%)"
            else
                echo "📊 Starting up..."
            fi
        else
            echo "📊 Initializing..."
        fi
        sleep 30
    else
        echo "✅ Process completed!"
        if [ -f "$OUTPUT_FILE" ]; then
            FINAL_COUNT=$(wc -l < "$OUTPUT_FILE")
            FINAL_COUNT=$((FINAL_COUNT - 1))
            echo "📈 Final count: $FINAL_COUNT tokens processed"
        fi
        break
    fi
done
