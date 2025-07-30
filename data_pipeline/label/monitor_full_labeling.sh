#!/bin/bash

echo "=== Token Labeling Progress Monitor ==="
echo "Started at: $(date)"
echo ""

while true; do
    echo "=== $(date) ==="
    
    # Check if process is still running
    if pgrep -f "token_labeler.py.*full_dataset_labels.csv" > /dev/null; then
        echo "✅ Process is running (PID: $(pgrep -f 'token_labeler.py.*full_dataset_labels.csv'))"
    else
        echo "❌ Process not found - may have completed or crashed"
        break
    fi
    
    # Show current batch progress
    echo "📊 Latest batch info:"
    tail -5 full_labeling.log | grep "Batch " | tail -1
    
    # Count processed vs skipped
    total_processed=$(grep -c "skipped\|unsuccessful\|successful\|rugpull" full_labeling.log || echo 0)
    skipped=$(grep -c "skipped" full_labeling.log || echo 0)
    labeled=$(grep -c "unsuccessful\|successful\|rugpull" full_labeling.log || echo 0)
    
    echo "📈 Stats:"
    echo "  - Total processed: $total_processed"
    echo "  - Skipped (no data): $skipped"
    echo "  - Labeled: $labeled"
    
    # Check output file size
    if [ -f "full_dataset_labels.csv" ]; then
        output_lines=$(wc -l < full_dataset_labels.csv)
        echo "  - Output file lines: $output_lines"
    else
        echo "  - Output file: Not created yet"
    fi
    
    echo ""
    sleep 30  # Check every 30 seconds
done

echo "Process completed at: $(date)"
