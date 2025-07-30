# Helius API Key Requirements Analysis

## Current Usage Pattern

### API Calls Per Token
- **Signature fetching**: 1-2 calls (paginated for up to 10,000 signatures)
- **Transaction analysis**: Up to 20 individual transaction requests (reduced from 50)
- **Holder count**: 1 call
- **Price/metadata**: 1 call
- **Total**: ~25 API calls per token

### Current Rate Limiting
- **Request rate**: 0.3 requests/second per key (3.3 seconds between requests)
- **Rate limit cooldown**: 180 seconds (3 minutes) when key hits limits
- **Global backoff**: 30 seconds when all keys are exhausted
- **Circuit breaker**: Stops after 15 consecutive failures

## Helius API Tiers & Limits

| Tier | Requests/Day | Cost/Month | Best For |
|------|-------------|------------|----------|
| **Free** | 100 | $0 | Testing only |
| **Starter** | 1,000 | ~$10 | Small batches |
| **Developer** | 10,000 | ~$50 | Medium usage |
| **Professional** | 100,000 | ~$200 | Production |
| **Enterprise** | 1,000,000+ | Custom | Large scale |

## Calculations

### Tokens Per Day Capacity

**With 7 Developer-tier keys (current setup):**
- Total daily requests: 7 × 10,000 = 70,000 requests/day
- Tokens processable: 70,000 ÷ 25 = **2,800 tokens/day**

**With Current Conservative Rate Limiting:**
- 0.3 requests/second × 7 keys = 2.1 requests/second
- Daily capacity: 2.1 × 86,400 = 181,440 requests/day
- But limited by tier: 70,000 requests/day
- **Actual capacity: 2,800 tokens/day**

### Recommendations by Use Case

#### Small Scale (100-500 tokens/day)
```
✅ CURRENT SETUP IS SUFFICIENT
- 7 Developer-tier keys
- Cost: ~$350/month
- Capacity: 2,800 tokens/day
```

#### Medium Scale (1,000-5,000 tokens/day)
```
🔧 UPGRADE NEEDED
- 10-15 Professional-tier keys
- Cost: ~$2,000-3,000/month
- Capacity: 40,000-60,000 tokens/day
```

#### Large Scale (10,000+ tokens/day)
```
🚀 ENTERPRISE SETUP
- 15-20 Enterprise-tier keys
- Custom pricing (~$5,000+/month)
- Capacity: 600,000+ tokens/day
```

## Optimizations to Reduce API Usage

### Already Implemented ✅
- Reduced transaction analysis from 50 to 20 requests
- Strategic sampling (early, middle, recent transactions)
- Conservative rate limiting (0.3 req/sec per key)
- Circuit breaker and exponential backoff
- Batch processing with delays

### Additional Optimizations 🔧

#### 1. **Reduce Transaction Analysis Further**
```python
# Current: 20 transactions per token
# Suggested: 10-15 transactions per token
max_to_analyze = min(len(signatures), 10)  # Reduce to 10
```
**Impact**: ~15 API calls per token = 4,600 tokens/day

#### 2. **Smart Caching**
```python
# Cache signature results for 24 hours
# Cache holder counts for 1 hour
# Cache price data for 30 minutes
```
**Impact**: 30-50% reduction in repeat calls

#### 3. **Parallel Processing with More Keys**
```python
# Increase concurrent API semaphore
self.api_semaphore = asyncio.Semaphore(15)  # From 10 to 15
```
**Impact**: 50% faster processing

#### 4. **Adaptive Sampling**
```python
# Fewer transactions for older/inactive tokens
# More transactions for recent/active tokens
if days_since_creation > 30:
    max_to_analyze = 5  # Older tokens
else:
    max_to_analyze = 15  # Recent tokens
```
**Impact**: 25% reduction in API calls

## Cost-Benefit Analysis

### Option 1: Optimize Current Setup
- **Cost**: $0 additional
- **Effort**: 2-3 hours optimization
- **Result**: 4,600 tokens/day (65% increase)

### Option 2: Add More Developer Keys
- **Cost**: +$300/month (6 more keys)
- **Effort**: 5 minutes (add to .env)
- **Result**: 5,200 tokens/day (85% increase)

### Option 3: Upgrade to Professional Tier
- **Cost**: +$1,400/month (7 Pro keys vs 7 Dev keys)
- **Effort**: Account upgrade
- **Result**: 28,000 tokens/day (900% increase)

## Recommended Action Plan

### Immediate (Today)
1. **Add 3-5 more Developer-tier API keys**
   - Cost: ~$200/month
   - Capacity: 4,000+ tokens/day
   - Setup time: 5 minutes

### Short-term (This Week)
2. **Implement optimizations**
   - Reduce to 10-15 transactions per token
   - Add basic caching
   - Expected: 6,000+ tokens/day

### Long-term (Next Month)
3. **Evaluate usage patterns**
   - If consistently hitting limits, upgrade to Professional tier
   - If sporadic usage, keep current setup

## Implementation

### Adding More API Keys
```bash
# Add to .env file:
HELIUS_API_KEY_8=your_new_key_here
HELIUS_API_KEY_9=your_new_key_here
HELIUS_API_KEY_10=your_new_key_here
# ... up to HELIUS_API_KEY_15
```

### Quick Optimization
```python
# In real_onchain_labeler.py line 361:
max_to_analyze = min(len(signatures), 10)  # Reduce from 20 to 10
```

## Monitoring

Track these metrics to optimize further:
- Tokens processed per hour
- API calls per token (actual vs estimated)
- Rate limit hits per key per day
- Processing success rate

---

**Bottom Line**: Your current 7 Developer-tier keys can handle **2,800 tokens/day**. For most use cases, adding 3-5 more keys (~$200/month) would provide **4,000+ tokens/day** capacity, which should be sufficient.
