"""
Test script to verify the corrected labeling for specific token
"""

from simple_labeler import SimpleTokenLabeler

def test_specific_token():
    labeler = SimpleTokenLabeler()
    
    # Test the problematic token
    problem_token = "B2NzCVnSTr5xystCTA2CYAZXJKPw4VFgWLG6rFzbpump"
    
    print(f"Testing token: {problem_token}")
    print("="*60)
    
    # Get metrics
    metrics = labeler.simulate_token_metrics(problem_token)
    
    print("Simulated Metrics:")
    print(f"Launch Price: ${metrics['launch_price']:.8f}")
    print(f"Price at 72h: ${metrics['price_72h']:.8f}")
    print(f"Current Price: ${metrics['current_price']:.8f}")
    print(f"Price change at 72h: {metrics['price_change_72h']:.2f}x ({(metrics['price_change_72h']-1)*100:.1f}%)")
    print(f"Sustained growth: {metrics['sustained_growth']:.2f}x ({(metrics['sustained_growth']-1)*100:.1f}%)")
    print(f"Overall change: {metrics['overall_change']:.2f}x ({(metrics['overall_change']-1)*100:.1f}%)")
    print(f"Volume 24h: ${metrics['volume_24h']:,.2f}")
    print(f"Holder count: {metrics['holder_count']:,}")
    print(f"Liquidity stable: {metrics['liquidity_stable']}")
    print(f"Dev dump: {metrics['dev_dump']}")
    
    # Classify
    label = labeler.classify_token(metrics)
    
    print(f"\nClassification Analysis:")
    print(f"Final Label: {label.upper()}")
    
    # Show why it got this label
    price_gain_72h = metrics['price_change_72h'] >= 10.0
    sustained_gains = metrics['sustained_growth'] >= 0.8
    high_volume = metrics['volume_24h'] > 100000
    good_adoption = metrics['holder_count'] > 500
    
    print(f"\nSuccess Criteria Check:")
    print(f"✓ Price gain >1000% at 72h: {price_gain_72h} ({metrics['price_change_72h']:.1f}x)")
    print(f"✓ Sustained growth (>0.8x): {sustained_gains} ({metrics['sustained_growth']:.2f}x)")
    print(f"✓ High volume (>$100K): {high_volume} (${metrics['volume_24h']:,.0f})")
    print(f"✓ Good adoption (>500): {good_adoption} ({metrics['holder_count']:,})")
    
    if label == 'successful':
        print(f"\n🚀 SUCCESS: All criteria met!")
    elif label == 'rugpull':
        print(f"\n🚨 RUGPULL: Malicious behavior detected!")
    else:
        print(f"\n📉 UNSUCCESSFUL: Failed to meet success criteria")
        if price_gain_72h and not sustained_gains:
            print("   → Had good gains at 72h but failed to sustain them (pump & dump pattern)")

if __name__ == "__main__":
    test_specific_token()
