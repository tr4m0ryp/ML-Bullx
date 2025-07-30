#!/bin/bash

echo "🚀 FULL DATASET TOKEN LABELING - PROGRESS REPORT"
echo "================================================"
echo "Started: $(date)"
echo ""

# Check if process is running
if pgrep -f "token_labeler.py.*full_dataset_labels.csv" > /dev/null; then
    pid=$(pgrep -f 'token_labeler.py.*full_dataset_labels.csv')
    echo "✅ Status: RUNNING (PID: $pid)"
    
    # Get current batch
    current_batch=$(grep "Batch " full_labeling.log | tail -1 | grep -o "Batch [0-9]*" | grep -o "[0-9]*")
    total_batches=8803
    
    if [ ! -z "$current_batch" ]; then
        progress_pct=$(echo "scale=2; $current_batch * 100 / $total_batches" | bc)
        echo "📊 Progress: Batch $current_batch/$total_batches ($progress_pct%)"
        
        # Estimate completion time
        start_time=$(stat -c %Y full_labeling.log)
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        elapsed_minutes=$((elapsed / 60))
        
        if [ $current_batch -gt 0 ]; then
            rate=$(echo "scale=4; $current_batch / $elapsed_minutes" | bc)
            remaining_batches=$((total_batches - current_batch))
            eta_minutes=$(echo "scale=0; $remaining_batches / $rate" | bc)
            eta_hours=$((eta_minutes / 60))
            eta_remaining_minutes=$((eta_minutes % 60))
            
            echo "⏱️  Runtime: ${elapsed_minutes} minutes"
            echo "🎯 ETA: ~${eta_hours}h ${eta_remaining_minutes}m remaining"
        fi
    fi
else
    echo "❌ Status: NOT RUNNING"
fi

echo ""
echo "📈 PROCESSING STATS:"

# Count different outcomes
total_processed=$(grep -c "skipped\|unsuccessful\|successful\|rugpull" full_labeling.log 2>/dev/null || echo 0)
skipped=$(grep -c "skipped" full_labeling.log 2>/dev/null || echo 0)
successful=$(grep -c "successful" full_labeling.log 2>/dev/null || echo 0)
unsuccessful=$(grep -c "unsuccessful" full_labeling.log 2>/dev/null || echo 0)
rugpull=$(grep -c "rugpull" full_labeling.log 2>/dev/null || echo 0)
labeled=$((successful + unsuccessful + rugpull))

echo "  📦 Total processed: $total_processed"
echo "  ⏭️  Skipped (no data): $skipped"
echo "  🏷️  Labeled tokens: $labeled"
if [ $labeled -gt 0 ]; then
    echo "    ✅ Successful: $successful"
    echo "    ❌ Unsuccessful: $unsuccessful"  
    echo "    💥 Rugpull: $rugpull"
fi

# Check output file
if [ -f "full_dataset_labels.csv" ]; then
    output_lines=$(wc -l < full_dataset_labels.csv)
    echo "  📄 Output file: $output_lines lines"
else
    echo "  📄 Output file: Not created yet"
fi

echo ""
echo "📋 Recent activity:"
tail -3 full_labeling.log | head -3

echo ""
echo "Run './monitor_full_labeling.sh' for continuous monitoring"
