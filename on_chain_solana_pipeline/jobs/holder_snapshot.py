"""
Script to snapshot unique holders for mints using getProgramAccounts.
Runs periodically to update holder counts in the database.
"""
import asyncio
import asyncpg
import logging
import sys
import os
from typing import List, Set
from datetime import datetime
from solana.rpc.async_api import AsyncClient
from solana.publickey import PublicKey

from on_chain_solana_pipeline.config.config_loader import load_config

logger = logging.getLogger(__name__)


class HolderSnapshotJob:
    """
    Job to snapshot holder counts for tokens and store in database.
    """
    
    def __init__(self, config_path: str = None):
        self.config = load_config(config_path)
        self.rpc_client: AsyncClient = None
        self.db_pool: asyncpg.Pool = None
    
    async def __aenter__(self):
        self.rpc_client = AsyncClient(self.config.rpc.url)
        self.db_pool = await asyncpg.create_pool(self.config.database.dsn)
        return self
    
    async def __aexit__(self, *exc):
        if self.rpc_client:
            await self.rpc_client.close()
        if self.db_pool:
            await self.db_pool.close()
    
    async def run_snapshot_for_mints(self, mints: List[str]) -> None:
        """Run holder snapshot for a list of mint addresses."""
        logger.info(f"Starting holder snapshot for {len(mints)} mints")
        
        for i, mint in enumerate(mints):
            try:
                logger.info(f"Processing mint {i+1}/{len(mints)}: {mint}")
                holder_count = await self._get_holder_count(mint)
                
                if holder_count is not None:
                    await self._store_snapshot(mint, holder_count)
                    logger.info(f"{mint}: {holder_count} holders")
                else:
                    logger.warning(f"Could not get holder count for {mint}")
                
                # Small delay to avoid overwhelming RPC
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing mint {mint}: {e}")
                continue
    
    async def run_snapshot_from_database(self) -> None:
        """Run snapshot for all mints that have recent swap activity."""
        async with self.db_pool.acquire() as conn:
            # Get mints with recent activity (last 7 days)
            recent_mints = await conn.fetch("""
                SELECT DISTINCT mint 
                FROM swap_ticks 
                WHERE ts >= NOW() - INTERVAL '7 days'
                ORDER BY mint
            """)
            
            mint_addresses = [row['mint'] for row in recent_mints]
            await self.run_snapshot_for_mints(mint_addresses)
    
    async def _get_holder_count(self, mint: str) -> int:
        """Get holder count for a specific mint address."""
        try:
            mint_pubkey = PublicKey(mint)
            
            # Get all token accounts for this mint
            response = await self.rpc_client.get_program_accounts(
                PublicKey(self.config.programs.token_program),
                encoding="jsonParsed",
                filters=[
                    {"dataSize": 165},  # Token account size
                    {"memcmp": {"offset": 0, "bytes": str(mint_pubkey)}}  # Filter by mint
                ]
            )
            
            if response.value is None:
                return 0
            
            # Count unique owners with non-zero balances
            unique_holders: Set[str] = set()
            
            for account in response.value:
                try:
                    parsed = account.account.data.parsed
                    if parsed['type'] == 'account':
                        info = parsed['info']
                        balance = int(info['tokenAmount']['amount'])
                        if balance > 0:
                            unique_holders.add(info['owner'])
                except Exception as e:
                    logger.debug(f"Error parsing account: {e}")
                    continue
            
            return len(unique_holders)
            
        except Exception as e:
            logger.error(f"Error getting holder count for {mint}: {e}")
            return None
    
    async def _store_snapshot(self, mint: str, holder_count: int) -> None:
        """Store holder snapshot in database."""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO holder_snapshots (mint, snapshot_time, holder_count)
                VALUES ($1, NOW(), $2)
                ON CONFLICT (mint, snapshot_time) DO UPDATE 
                SET holder_count = $2
            """, mint, holder_count)


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Holder snapshot job")
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--mints", nargs="+", help="Specific mint addresses to process")
    parser.add_argument("--from-db", action="store_true", help="Process mints from database")
    args = parser.parse_args()
    
    async with HolderSnapshotJob(args.config) as job:
        if args.mints:
            await job.run_snapshot_for_mints(args.mints)
        elif args.from_db:
            await job.run_snapshot_from_database()
        else:
            parser.print_help()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
