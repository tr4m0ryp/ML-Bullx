#!/usr/bin/env python3
"""
Practical Mint Address Collection Strategy

This script provides a realistic approach to collecting Solana mint addresses
with achievable targets and multiple collection strategies.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from data_pipeline.mint_addr.scrape_mint_simple import SimpleMintScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('practical_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PracticalMintCollector:
    """Practical mint collector with realistic targets."""
    
    def __init__(self):
        self.collected_addresses = set()
        self.target_tiers = {
            'minimal': 500_000,      # 500K - very achievable
            'good': 1_000_000,       # 1M - realistic target
            'excellent': 2_000_000,  # 2M - optimistic but possible
            'stretch': 5_000_000     # 5M - stretch goal
        }
    
    async def collect_with_realistic_targets(self):
        """Collect addresses with tiered, realistic targets."""
        
        logger.info("Starting Practical Mint Address Collection")
        logger.info("=" * 60)
        
        # Tier 1: Core sources (should get us to 500K-1M)
        logger.info("TIER 1: Core Sources (Target: 500K-1M addresses)")
        await self.run_core_collection()
        
        if len(self.collected_addresses) >= self.target_tiers['minimal']:
            logger.info(f"[OK] Tier 1 SUCCESS: {len(self.collected_addresses):,} addresses")
        else:
            logger.warning(f"[WARN] Tier 1 partial: {len(self.collected_addresses):,} addresses")
        
        # Tier 2: Extended sources (should get us to 1M-2M)
        if len(self.collected_addresses) < self.target_tiers['excellent']:
            logger.info("TIER 2: Extended Collection (Target: 1M-2M addresses)")
            await self.run_extended_collection()
            
            if len(self.collected_addresses) >= self.target_tiers['good']:
                logger.info(f"[OK] Tier 2 SUCCESS: {len(self.collected_addresses):,} addresses")
            else:
                logger.warning(f"[WARN] Tier 2 partial: {len(self.collected_addresses):,} addresses")
        
        # Tier 3: Aggressive collection (stretch goal)
        if len(self.collected_addresses) < self.target_tiers['stretch']:
            logger.info("TIER 3: Aggressive Collection (Target: 2M-5M addresses)")
            await self.run_aggressive_collection()
        
        await self.finalize_collection()
    
    async def run_core_collection(self):
        """Run core collection from best sources."""
        logger.info("Starting core collection...")
        
        scraper = SimpleMintScraper(target_count=1_000_000)  # Realistic target
        
        try:
            async with scraper:
                # Load any existing progress
                scraper.load_checkpoint()
                if len(scraper.mint_addresses) > 0:
                    self.collected_addresses.update(scraper.mint_addresses)
                    logger.info(f"Loaded {len(scraper.mint_addresses):,} from checkpoint")
                
                # Core sources in order of reliability/yield
                core_sources = [
                    ("Jupiter", scraper.fetch_from_jupiter()),
                    ("Raydium", scraper.fetch_from_raydium()),
                    ("Orca", scraper.fetch_from_orca()),
                ]
                
                for source_name, source_coro in core_sources:
                    try:
                        logger.info(f"Collecting from {source_name}...")
                        addresses = await asyncio.wait_for(source_coro, timeout=600)  # 10min timeout
                        new_addresses = addresses - self.collected_addresses
                        self.collected_addresses.update(new_addresses)
                        
                        logger.info(f"[OK] {source_name}: +{len(new_addresses):,} new | Total: {len(self.collected_addresses):,}")

                        # Save progress
                        self.save_progress(f"after_{source_name.lower()}")

                    except Exception as e:
                        logger.error(f"[ERROR] {source_name} failed: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error in core collection: {e}")
    
    async def run_extended_collection(self):
        """Run extended collection from additional sources."""
        logger.info("Starting extended collection...")
        
        scraper = SimpleMintScraper(target_count=2_000_000)
        
        try:
            async with scraper:
                extended_sources = [
                    ("DexScreener", scraper.fetch_from_dexscreener()),
                    ("Additional", scraper.fetch_from_additional_sources()),
                    ("CoinGecko", scraper.fetch_from_coingecko()),
                ]
                
                for source_name, source_coro in extended_sources:
                    try:
                        logger.info(f"Extended: {source_name}...")
                        addresses = await asyncio.wait_for(source_coro, timeout=900)  # 15min timeout
                        new_addresses = addresses - self.collected_addresses
                        self.collected_addresses.update(new_addresses)
                        
                        logger.info(f"[OK] {source_name}: +{len(new_addresses):,} new | Total: {len(self.collected_addresses):,}")

                        # Save progress
                        self.save_progress(f"after_extended_{source_name.lower()}")

                    except Exception as e:
                        logger.error(f"[ERROR] Extended {source_name} failed: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error in extended collection: {e}")
    
    async def run_aggressive_collection(self):
        """Run aggressive collection with all possible methods."""
        logger.info("Starting aggressive collection...")
        
        # This would include more intensive methods like:
        # - Multiple DexScreener searches with many terms
        # - Blockchain scanning (if we had RPC access)
        # - Token discovery through transaction analysis
        
        logger.info("Aggressive collection methods would go here...")
        logger.info("(Placeholder for advanced collection techniques)")
    
    def save_progress(self, stage: str):
        """Save progress at different stages."""
        try:
            progress_data = {
                'stage': stage,
                'count': len(self.collected_addresses),
                'addresses': list(self.collected_addresses),
                'timestamp': datetime.now().isoformat(),
                'tier_progress': self.get_tier_progress()
            }
            
            filename = f"practical_collection_{stage}.json"
            with open(filename, 'w') as f:
                json.dump(progress_data, f, indent=2)
                
            logger.info(f"Progress saved: {filename}")
            
        except Exception as e:
            logger.error(f"Error saving progress: {e}")
    
    def get_tier_progress(self):
        """Get progress against tier targets."""
        count = len(self.collected_addresses)
        progress = {}
        
        for tier, target in self.target_tiers.items():
            percentage = (count / target) * 100
            progress[tier] = {
                'target': target,
                'current': count,
                'percentage': min(percentage, 100.0),
                'achieved': count >= target
            }
        
        return progress
    
    async def finalize_collection(self):
        """Finalize and export the collection."""
        logger.info("FINAL RESULTS")
        logger.info("=" * 60)
        
        tier_progress = self.get_tier_progress()
        
        for tier, data in tier_progress.items():
            status = "[DONE] ACHIEVED" if data['achieved'] else f"{data['percentage']:.1f}%"
            logger.info(f"{tier.upper():>10}: {data['target']:>8,} | {status}")
        
        logger.info("=" * 60)
        logger.info(f"TOTAL COLLECTED: {len(self.collected_addresses):,} unique addresses")
        
        # Export final results
        self.export_final_results()
    
    def export_final_results(self):
        """Export final results to CSV and JSON."""
        try:
            import pandas as pd
            
            # CSV export
            df = pd.DataFrame({
                'mint_address': list(self.collected_addresses),
                'collected_at': datetime.now().isoformat(),
                'collection_method': 'practical_multi_source'
            })
            
            csv_filename = f"practical_mint_addresses_{len(self.collected_addresses)}.csv"
            df.to_csv(csv_filename, index=False)
            
            # Text export
            txt_filename = csv_filename.replace('.csv', '.txt')
            with open(txt_filename, 'w') as f:
                for addr in self.collected_addresses:
                    f.write(f"{addr}\n")
            
            logger.info(f"Exported: {csv_filename}")
            logger.info(f"Exported: {txt_filename}")
            
            # Summary JSON
            summary = {
                'total_addresses': len(self.collected_addresses),
                'collection_date': datetime.now().isoformat(),
                'tier_results': self.get_tier_progress(),
                'files_created': [csv_filename, txt_filename]
            }
            
            with open('collection_summary.json', 'w') as f:
                json.dump(summary, f, indent=2)
            
            logger.info("Summary: collection_summary.json")
            
        except Exception as e:
            logger.error(f"Error exporting results: {e}")

async def main():
    """Main function."""
    collector = PracticalMintCollector()
    await collector.collect_with_realistic_targets()

if __name__ == "__main__":
    asyncio.run(main())
