#!/usr/bin/env python3
"""
Comprehensive Token Analysis Tool for Algorithm Fine-tuning
Analyzes actual token data to identify misclassification patterns
"""

import asyncio
import sys
import os
import pandas as pd
from typing import Dict, List, Tuple, Optional

# Add pipeline path for imports
pipeline_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "on_chain_solana_pipeline")
sys.path.insert(0, pipeline_dir)
config_dir = os.path.join(pipeline_dir, "config")
sys.path.insert(0, config_dir)

try:
    from token_labeler import EnhancedTokenLabeler, TokenMetrics
except ImportError:
    print("Could not import token_labeler, running in analysis mode only")

class TokenAnalyzer:
    """Analyze token patterns to fine-tune classification algorithm"""
    
    def __init__(self):
        self.analysis_results = []
        
    async def analyze_sample_tokens(self, csv_path: str, sample_size: int = 20):
        """Analyze a sample of tokens to understand data patterns"""
        
        df = pd.read_csv(csv_path)
        if 'mint_address' not in df.columns:
            print("Error: CSV must have mint_address column")
            return
            
        # Get a sample of different classifications
        sample_tokens = []
        
        if 'label' in df.columns:
            # Get samples from each category
            for label in ['successful', 'rugpull', 'unsuccessful', 'inactive']:
                label_tokens = df[df['label'] == label]['mint_address'].tolist()
                if label_tokens:
                    sample_tokens.extend(label_tokens[:5])  # 5 from each category
        else:
            # Just take first N tokens
            sample_tokens = df['mint_address'].head(sample_size).tolist()
        
        print(f"Analyzing {len(sample_tokens)} tokens...")
        
        try:
            async with EnhancedTokenLabeler() as labeler:
                for i, mint in enumerate(sample_tokens):
                    print(f"\n{'='*60}")
                    print(f"ANALYZING TOKEN {i+1}/{len(sample_tokens)}: {mint}")
                    print(f"{'='*60}")
                    
                    try:
                        # Get raw metrics
                        metrics = await labeler._gather_metrics(mint)
                        
                        # Analyze the token
                        analysis = self.analyze_token_metrics(metrics)
                        
                        # Get current classification
                        current_label = labeler._classify(metrics)
                        
                        # Store results
                        self.analysis_results.append({
                            'mint': mint,
                            'metrics': metrics,
                            'analysis': analysis,
                            'current_label': current_label
                        })
                        
                        print(f"Current Classification: {current_label.upper()}")
                        print(f"Analysis Score: {analysis['score']:.3f}")
                        print(f"Recommended: {analysis['recommended_label']}")
                        
                        if current_label != analysis['recommended_label']:
                            print(f"⚠️  MISMATCH DETECTED!")
                            print(f"Reason: {analysis['reason']}")
                        
                    except Exception as e:
                        print(f"Error analyzing {mint}: {e}")
                        continue
                        
        except Exception as e:
            print(f"Error with EnhancedTokenLabeler: {e}")
            return
    
    def analyze_token_metrics(self, m: TokenMetrics) -> Dict:
        """Comprehensive analysis of token metrics to determine correct classification"""
        
        analysis = {
            'score': 0.0,
            'recommended_label': 'unsuccessful',
            'reason': 'Default classification',
            'factors': [],
            'red_flags': [],
            'missing_data': []
        }
        
        # Check for missing critical data
        missing = []
        if m.launch_price is None:
            missing.append('launch_price')
        if m.volume_24h is None:
            missing.append('volume_24h')
        if m.mega_appreciation is None:
            missing.append('mega_appreciation')
        analysis['missing_data'] = missing
        
        # Calculate or estimate key metrics
        appreciation = self.calculate_appreciation(m)
        collapse_ratio = self.calculate_collapse_ratio(m)
        volume_status = self.assess_volume_status(m)
        holder_status = self.assess_holder_status(m)
        
        print(f"\n📊 KEY METRICS:")
        print(f"  Appreciation: {appreciation:.1f}x" if appreciation else "  Appreciation: Unknown")
        print(f"  Collapse Ratio: {collapse_ratio:.4f}" if collapse_ratio else "  Collapse Ratio: Unknown")
        print(f"  Volume Status: {volume_status}")
        print(f"  Holder Status: {holder_status}")
        print(f"  Missing Data: {', '.join(missing) if missing else 'None'}")
        
        # Apply fine-tuned classification logic
        if self.is_clear_rugpull(m, appreciation, collapse_ratio, volume_status):
            analysis['recommended_label'] = 'rugpull'
            analysis['reason'] = f"Clear rugpull: {appreciation:.0f}x → {collapse_ratio:.4f} collapse, {volume_status}"
            analysis['score'] = 0.9
            
        elif self.is_truly_inactive(m, appreciation, volume_status, holder_status):
            analysis['recommended_label'] = 'inactive'
            analysis['reason'] = f"Never gained traction: {appreciation:.1f}x max, {holder_status}, {volume_status}"
            analysis['score'] = 0.1
            
        elif self.is_genuine_success(m, appreciation, collapse_ratio, volume_status, holder_status):
            analysis['recommended_label'] = 'successful'
            analysis['reason'] = f"Genuine success: {appreciation:.0f}x appreciation, sustained performance"
            analysis['score'] = 0.8
            
        else:
            analysis['recommended_label'] = 'unsuccessful'
            analysis['reason'] = f"Failed project: {appreciation:.1f}x appreciation but didn't meet success criteria"
            analysis['score'] = 0.3
        
        return analysis
    
    def calculate_appreciation(self, m: TokenMetrics) -> Optional[float]:
        """Calculate total appreciation using multiple methods"""
        
        # Method 1: Direct mega appreciation
        if m.mega_appreciation:
            return m.mega_appreciation
        
        # Method 2: ATH vs current (reverse calculation)
        if m.current_price and m.post_ath_peak_price and m.current_price > 0:
            return m.post_ath_peak_price / m.current_price
        
        # Method 3: 72h peak vs current
        if m.current_price and m.peak_price_72h and m.current_price > 0:
            return m.peak_price_72h / m.current_price
        
        # Method 4: Launch vs ATH
        if m.launch_price and m.post_ath_peak_price and m.launch_price > 0:
            return m.post_ath_peak_price / m.launch_price
        
        return None
    
    def calculate_collapse_ratio(self, m: TokenMetrics) -> Optional[float]:
        """Calculate how much the token collapsed from ATH"""
        if m.current_vs_ath_ratio:
            return m.current_vs_ath_ratio
        
        if m.current_price and m.post_ath_peak_price and m.post_ath_peak_price > 0:
            return m.current_price / m.post_ath_peak_price
            
        return None
    
    def assess_volume_status(self, m: TokenMetrics) -> str:
        """Assess volume status"""
        if m.volume_24h is None:
            return "unknown"
        elif m.volume_24h < 10:
            return "dead"
        elif m.volume_24h < 1000:
            return "very_low"
        elif m.volume_24h < 10000:
            return "low"
        elif m.volume_24h < 50000:
            return "moderate"
        else:
            return "high"
    
    def assess_holder_status(self, m: TokenMetrics) -> str:
        """Assess holder status"""
        if m.holder_count is None:
            return "unknown"
        elif m.holder_count < 10:
            return "very_few"
        elif m.holder_count < 25:
            return "few"
        elif m.holder_count < 100:
            return "moderate"
        elif m.holder_count < 500:
            return "good"
        else:
            return "excellent"
    
    def is_clear_rugpull(self, m: TokenMetrics, appreciation: Optional[float], 
                        collapse_ratio: Optional[float], volume_status: str) -> bool:
        """Determine if token is a clear rugpull"""
        
        # Must have had significant appreciation first
        if not appreciation or appreciation < 10:
            return False
        
        # Must have collapsed significantly
        if not collapse_ratio or collapse_ratio > 0.05:  # Still above 5% of ATH
            return False
        
        # Volume should be dead or very low
        if volume_status not in ['dead', 'very_low', 'unknown']:
            return False
        
        # Additional confirmation for high appreciation cases
        if appreciation >= 100:  # 100x+ appreciation
            if collapse_ratio <= 0.01:  # Collapsed to <1% of ATH
                return True
        
        # Very high appreciation gets lower thresholds
        if appreciation >= 500:  # 500x+ appreciation
            if collapse_ratio <= 0.02:  # Collapsed to <2% of ATH
                return True
        
        return False
    
    def is_truly_inactive(self, m: TokenMetrics, appreciation: Optional[float],
                         volume_status: str, holder_status: str) -> bool:
        """Determine if token is truly inactive"""
        
        # Never gained significant traction
        if appreciation and appreciation >= 5:  # Even 5x is some traction
            return False
        
        # Must have very few holders
        if holder_status not in ['very_few', 'few']:
            return False
        
        # Must have dead or very low volume
        if volume_status not in ['dead', 'very_low', 'unknown']:
            return False
        
        return True
    
    def is_genuine_success(self, m: TokenMetrics, appreciation: Optional[float],
                          collapse_ratio: Optional[float], volume_status: str, 
                          holder_status: str) -> bool:
        """Determine if token is genuinely successful"""
        
        # Must have significant appreciation
        if not appreciation or appreciation < 10:
            return False
        
        # Must have sustained some value (not completely collapsed)
        if collapse_ratio and collapse_ratio < 0.1:  # Less than 10% of ATH might be rugpull
            # Only allow if appreciation is moderate (not extreme pump and dump)
            if appreciation > 100:  # High appreciation + extreme collapse = likely rugpull
                return False
        
        # Must have good community adoption
        if holder_status in ['very_few', 'few']:
            return False
        
        # Volume should be reasonable
        if volume_status == 'dead':
            return False
        
        # Additional criteria for high confidence
        if appreciation >= 50 and holder_status in ['good', 'excellent']:
            return True
        
        if appreciation >= 20 and holder_status == 'moderate' and volume_status in ['moderate', 'high']:
            return True
        
        return False
    
    def generate_recommendations(self):
        """Generate recommendations for algorithm improvements"""
        
        print(f"\n{'='*60}")
        print("ALGORITHM IMPROVEMENT RECOMMENDATIONS")
        print(f"{'='*60}")
        
        mismatches = [r for r in self.analysis_results 
                     if r['current_label'] != r['analysis']['recommended_label']]
        
        print(f"Total tokens analyzed: {len(self.analysis_results)}")
        print(f"Misclassifications found: {len(mismatches)}")
        print(f"Accuracy: {(len(self.analysis_results) - len(mismatches)) / len(self.analysis_results) * 100:.1f}%")
        
        if mismatches:
            print("\n🔧 RECOMMENDED FIXES:")
            
            # Group mismatches by type
            mismatch_types = {}
            for m in mismatches:
                key = f"{m['current_label']} → {m['analysis']['recommended_label']}"
                if key not in mismatch_types:
                    mismatch_types[key] = []
                mismatch_types[key].append(m)
            
            for mismatch_type, examples in mismatch_types.items():
                print(f"\n{mismatch_type}: {len(examples)} cases")
                for ex in examples[:3]:  # Show first 3 examples
                    print(f"  - {ex['mint'][:20]}... : {ex['analysis']['reason']}")
        
        print(f"\n{'='*60}")

async def main():
    """Main analysis function"""
    
    # Check if we have the CSV file
    csv_files = ['output.csv', 'output.csv.backup_1754000685', 'input.csv']
    csv_path = None
    
    for f in csv_files:
        if os.path.exists(f):
            csv_path = f
            break
    
    if not csv_path:
        print("No CSV file found. Please ensure output.csv or input.csv exists.")
        return
    
    print(f"Using CSV file: {csv_path}")
    
    analyzer = TokenAnalyzer()
    await analyzer.analyze_sample_tokens(csv_path, sample_size=15)
    analyzer.generate_recommendations()

if __name__ == "__main__":
    asyncio.run(main())
