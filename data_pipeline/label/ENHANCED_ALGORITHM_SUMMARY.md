# Enhanced Token Classification Algorithm

## Overview

The token labeling algorithm has been significantly improved to address the issue where tokens with early large drops but later successful pumps were incorrectly labeled as rugpulls. The new algorithm is much more sophisticated and considers recovery patterns, timing, and context.

## Key Problems Solved

### Previous Issue
- Tokens with 70%+ drops were immediately labeled as "rugpull"
- No consideration for recovery potential
- Early phase volatility treated the same as coordinated dumps
- No distinction between rapid coordinated sells vs natural market fluctuations

### Enhanced Solution
- **Recovery-aware classification**: Tokens can be "successful" even after major early drops if they show strong recovery
- **Time-based analysis**: Early phase drops (first 7 days) are treated more leniently than late phase drops
- **Pattern recognition**: Multiple rapid drops indicate coordinated dumps vs single volatile events
- **Trend analysis**: Current trend helps distinguish recovering vs declining tokens

## New Classification Categories

### 1. Successful ✅
**Traditional Success:**
- 10x+ appreciation from 72h ATH to post-ATH peak
- 100+ holders minimum
- No sustained major drops

**Recovery Success (NEW):**
- Strong recovery (5x+) after early major drops
- 150+ holders (higher threshold for recovered tokens)
- Stable or recovering trend for 7+ days after recovery
- Early phase drops with 5x+ recovery ratios

### 2. Rugpull ❌
**Enhanced Detection:**
- **Multiple rapid drops**: 2+ drops within 6 hours (coordinated dumping)
- **Late phase unrecovered drops**: Major drops after early phase without 5x recovery within 14+ days
- **Persistent decline**: Declining trend 7+ days after major drops
- **Early drops without recovery**: Early drops without ANY significant recovery after 14+ days

### 3. Inactive 💤 (NEW)
- Very low 24h volume (< $1,000 USD)
- Very few holders (< 10)
- Minimal market activity

### 4. Unsuccessful 📉
- Doesn't meet success criteria
- Not a clear rugpull
- Limited growth or moderate drops without strong recovery

## Technical Implementation

### Enhanced Metrics Tracking
```python
@dataclass
class TokenMetrics:
    # Original metrics...
    
    # New enhanced metrics
    early_phase_drops: List[Tuple[datetime, float, float]]  # (time, drop%, recovery_ratio)
    late_phase_drops: List[Tuple[datetime, float, float]]   # (time, drop%, recovery_ratio)
    max_recovery_after_drop: Optional[float]               # Best recovery ratio
    rapid_drops_count: int                                  # Rapid drops within 6h
    days_since_last_major_drop: Optional[int]             # Time for recovery analysis
    has_shown_recovery: bool                               # Any 5x+ recovery
    current_trend: str                                     # "recovering", "declining", "stable"
```

### Time Windows
- **Early Phase**: First 7 days (more lenient on drops)
- **Recovery Analysis**: 30-day windows to detect recoveries
- **Rapid Drop Detection**: 6-hour window for coordinated dumps
- **Recovery Grace Period**: 14+ days for significant recovery
- **Trend Analysis**: Last 7 days for current direction

### Thresholds
```python
RUG_THRESHOLD = 0.70                    # 70% drop threshold
RUG_RAPID_DROP_HOURS = 6               # Hours for rapid drop detection
RUG_NO_RECOVERY_DAYS = 14              # Days without recovery = potential rug
SUCCESS_RECOVERY_MULTIPLIER = 5.0       # Must recover to 5x the drop low
INACTIVE_VOLUME_THRESHOLD = 1000        # USD volume threshold
```

## Examples

### Scenario 1: Early Drop + Recovery Success ✅
```
Token drops 75% in day 3 (early phase) but recovers to 8x the low within 2 weeks
- OLD: "rugpull" (due to 75% drop)
- NEW: "successful" (early drop + strong recovery + good holders)
```

### Scenario 2: Coordinated Rugpull ❌
```
Token has 2 rapid drops of 70%+ within hours of each other
- OLD: "rugpull" (correct)
- NEW: "rugpull" (enhanced detection of coordination)
```

### Scenario 3: Late Phase Failed Recovery ❌
```
Token drops 80% after 30 days, only recovers to 1.2x the low in 20 days
- OLD: "rugpull" (correct)
- NEW: "rugpull" (late phase drop without adequate recovery)
```

## Benefits

1. **Reduced False Positives**: Legitimate tokens with early volatility are no longer mislabeled
2. **Better Rugpull Detection**: More sophisticated pattern recognition
3. **Recovery Recognition**: Algorithm rewards genuine comeback stories
4. **Time-Aware**: Considers market maturity and development phases
5. **Trend-Aware**: Current direction matters for classification
6. **Activity-Based**: Distinguishes between low-activity and failed projects

## Configuration

The algorithm is highly configurable with clear constants that can be tuned based on market conditions and analysis requirements:

```python
# Adjustable thresholds
RUG_THRESHOLD = 0.70                    # Drop percentage for rug consideration
SUCCESS_APPRECIATION = 10.0             # Traditional success multiplier
SUCCESS_RECOVERY_MULTIPLIER = 5.0       # Recovery success multiplier
EARLY_PHASE_DAYS = 7                    # Early phase leniency period
RECOVERY_ANALYSIS_DAYS = 30             # Recovery detection window
```

## Testing

The enhanced algorithm has been tested with various scenarios:
- ✅ Traditional successful tokens
- ✅ Early drop + recovery success cases
- ✅ Multiple rapid drop rugpulls
- ✅ Late phase unrecovered drops
- ✅ Inactive tokens
- ✅ Regular unsuccessful tokens

All test cases pass with the expected classifications, demonstrating the algorithm's improved accuracy and sophistication.
