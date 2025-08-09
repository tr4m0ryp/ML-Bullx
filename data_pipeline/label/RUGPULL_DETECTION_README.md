# Rugpull vs Success Detection System

## Overview

This advanced detection system solves a critical problem in memecoin classification: **distinguishing between legitimate successful coins that experienced natural volatility and actual rugpulls with coordinated malicious intent**.

## The Problem

Many successful memecoins exhibit patterns that can appear similar to rugpulls:
- ✅ **Successful coins** may have extreme volume drops, price volatility, and temporary declines due to natural market cycles
- ❌ **Rugpulls** have coordinated liquidity removal, artificial pumps, and no legitimate recovery patterns
- 🤔 **Traditional algorithms** often misclassify successful coins as rugpulls due to surface-level similarities

## The Solution

Our **Legitimacy Analysis System** uses sophisticated pattern recognition to distinguish between organic and artificial behaviors:

### Key Differentiators

#### 🔍 **Volume Recovery Patterns**
- **Organic Recovery**: Gradual volume return over 6+ hours with varied transaction intervals
- **Artificial Recovery**: Rapid volume spikes within 2 hours with bot-like transaction patterns

#### ⏰ **Recovery Timing Analysis**
- **Legitimate**: Recovery takes time (6-168 hours) with sustainable growth
- **Suspicious**: Ultra-fast recovery (<2 hours) or no recovery at all

#### 📊 **Transaction Pattern Scoring**
- **Natural**: Multiple transactions (10+) with varied timing (15+ min intervals)
- **Artificial**: Few transactions (<10) with suspicious timing (<1 min intervals)

#### 💹 **Price-Volume Correlation**
- **Healthy**: Reasonable correlation between price and volume movements
- **Manipulated**: Volume drops without price correlation or extreme disconnection

## System Architecture

### Core Components

1. **`rugpull_vs_success_detector.py`** - Standalone legitimacy analysis engine
2. **Enhanced TokenLabeler** - Integrated classification with legitimacy verification
3. **VolumeDropEvent & RecoveryPattern** - Data structures for pattern analysis

### Analysis Pipeline

```python
# 1. Identify significant volume drop events (60%+ drops)
volume_drops = identify_volume_drop_events(ohlcv_data)

# 2. Analyze recovery patterns for each drop
recovery_patterns = analyze_recovery_patterns(volume_drops)

# 3. Score overall legitimacy (0.0 = rugpull, 1.0 = legitimate)
legitimacy_score = calculate_legitimacy_score(volume_drops, recovery_patterns)

# 4. Generate classification hint
classification_hint = generate_hint(legitimacy_score)  # "success_likely", "rugpull_likely", "unclear"
```

### Integration with Token Classification

The legitimacy analysis is seamlessly integrated into the main classification algorithm:

```python
def _classify(self, token_metrics):
    # Get legitimacy analysis
    legitimacy_hint = token_metrics.legitimacy_analysis.get("classification_hint")
    legitimacy_score = token_metrics.legitimacy_analysis.get("overall_legitimacy_score")
    
    # Enhanced rugpull detection
    if self._is_coordinated_rugpull_with_legitimacy(token_metrics, legitimacy_hint, legitimacy_score):
        return "rugpull"
    
    # Enhanced success detection  
    if self._is_breakthrough_success_with_legitimacy(token_metrics, legitimacy_hint, legitimacy_score):
        return "successful"
```

## Legitimacy Scoring System

### Score Components (0.0 - 1.0 scale)

#### Recovery Duration (30% weight)
- **0.3**: Recovery takes 6-168 hours (organic timing)
- **0.1**: Recovery takes >168 hours (too slow)
- **-0.2**: Recovery takes <6 hours (suspicious speed)

#### Volume Recovery Strength (30% weight)
- **0.3**: Strong recovery (80%+ of pre-drop volume)
- **0.2**: Moderate recovery (50-80%)
- **0.1**: Weak recovery (<50%)

#### Transaction Count (20% weight)
- **0.2**: Many transactions (10+) during recovery
- **0.1**: Some transactions (5-9)
- **-0.1**: Too few transactions (<5)

#### Transaction Timing (20% weight)
- **0.2**: Natural intervals (15+ minutes between transactions)
- **0.1**: Somewhat natural (5-15 minutes)
- **-0.2**: Highly suspicious (<1 minute intervals)

### Final Classification Thresholds

- **≥0.7**: `success_likely` - Strong evidence of legitimacy
- **≤0.3**: `rugpull_likely` - Strong evidence of manipulation  
- **0.3-0.7**: `unclear` - Requires additional analysis

## Enhanced Classification Logic

### For Successful Coins
```python
# If legitimacy suggests rugpull, need stronger success evidence
if legitimacy_hint == "rugpull_likely":
    # Require 3+ strong indicators:
    # - 3x+ breakthrough ratio
    # - 3x+ sustained price  
    # - 100+ holders + $25k+ volume
    # - 10x+ historical recovery
    strong_evidence_count >= 3  # Override negative legitimacy

# If legitimacy suggests success, confirm it
elif legitimacy_hint == "success_likely":
    return "successful"  # Trust the analysis
```

### For Rugpulls
```python
# If legitimacy suggests rugpull, look for confirmation
if legitimacy_hint == "rugpull_likely":
    # Any traditional rugpull indicator confirms it
    if liquidity_removal OR mega_rugpull_pattern:
        return "rugpull"

# If legitimacy suggests success, need very strong rugpull evidence
elif legitimacy_hint == "success_likely":
    # Only classify as rugpull with extreme evidence
    if liquidity_removal AND post_recovery < 10% of pre_removal:
        return "rugpull"  # Override positive legitimacy
```

## Usage Examples

### Basic Usage
```python
from rugpull_vs_success_detector import analyze_token_legitimacy

# Analyze OHLCV data
result = analyze_token_legitimacy(ohlcv_data)

print(f"Classification hint: {result['classification_hint']}")
print(f"Legitimacy score: {result['overall_legitimacy_score']:.2f}")
print(f"Volume drops detected: {len(result['volume_drop_events'])}")
print(f"Recovery patterns: {len(result['recovery_patterns'])}")
```

### Integrated Classification
```python
from token_labeler_copy import EnhancedTokenLabeler

async with EnhancedTokenLabeler() as labeler:
    # The legitimacy analysis is automatically performed
    result = await labeler._process("mint_address")
    print(f"Final classification: {result[1]}")
```

## Test Cases

Run the test suite to see how different coin types are classified:

```bash
python test_rugpull_detector.py
```

### Test Scenarios

1. **🟢 Successful Coin with Natural Volatility**
   - Expected: `success_likely` (score: 0.7+)
   - Pattern: Organic volume drops with gradual recovery

2. **🔴 Clear Rugpull**  
   - Expected: `rugpull_likely` (score: 0.3-)
   - Pattern: Rapid dump with dead volume, no recovery

3. **🟡 Successful Coin with Extreme Volatility**
   - Expected: `success_likely` or `unclear` (score: 0.4-0.8)
   - Pattern: Major volume drops but organic recovery patterns

## Benefits

### ✅ **Prevents Misclassification**
- Successful memecoins with natural volatility won't be labeled as rugpulls
- Actual rugpulls are caught even if they attempt recovery manipulation

### 📊 **Improves ML Training Data Quality**
- More accurate labels lead to better ML model performance
- Reduces false positives and false negatives

### 🔍 **Detailed Analysis**
- Provides reasoning for each classification decision
- Offers granular insights into volume and recovery patterns

### 🚀 **Scalable and Fast**
- Processes OHLCV data efficiently
- Can analyze thousands of tokens quickly

## Configuration

Key parameters in `RugpullVsSuccessDetector`:

```python
# Volume drop thresholds
SIGNIFICANT_VOLUME_DROP = 0.60  # 60%+ is significant
EXTREME_VOLUME_DROP = 0.80     # 80%+ is extreme

# Recovery timing
ORGANIC_RECOVERY_MIN_HOURS = 6    # Organic recovery takes time
ARTIFICIAL_RECOVERY_MAX_HOURS = 2 # Artificial is very fast

# Transaction patterns  
MIN_RECOVERY_TRANSACTIONS = 10    # Legitimate recovery has multiple txs
ORGANIC_TX_INTERVAL_MINUTES = 15  # Natural timing between transactions

# Classification thresholds
RUGPULL_LEGITIMACY_THRESHOLD = 0.3  # Below = likely rugpull
SUCCESS_LEGITIMACY_THRESHOLD = 0.7  # Above = likely success
```

## Future Enhancements

- **Holder Behavior Analysis**: Track unique addresses during drops/recoveries
- **Cross-Platform Correlation**: Analyze social media sentiment during events
- **ML Integration**: Train models on legitimacy patterns for even better accuracy
- **Real-Time Monitoring**: Detect rugpulls as they happen

---

This system represents a significant advancement in cryptocurrency analysis, providing the nuanced understanding needed to distinguish between legitimate market volatility and coordinated manipulation.
