"""
Periodic holder-count snapshot job for tracked SPL tokens.

- Queries unique token holders via the Solana ``getProgramAccounts``
  RPC method, filtering by mint and counting owners with non-zero
  balances.
- Stores snapshots in the ``holder_snapshots`` table with
  conflict-safe upserts.
- Supports two modes of operation:
    * Explicit mint list (``--mints``).
    * Automatic discovery from the database: snapshots all mints with
      swap activity in the last seven days (``--from-db``).
- Designed to be run on a cron schedule to maintain an up-to-date
  time series of holder counts per token.

Author: ML-Bullx Team
Date:   2025-08-01
"""

# ==============================================================================
# Standard library imports
# ==============================================================================
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import List, Set

# ==============================================================================
# Third-party imports
# ==============================================================================
import asyncpg
from solana.rpc.async_api import AsyncClient
from solana.publickey import PublicKey

# ==============================================================================
# Local imports
# ==============================================================================
from on_chain_solana_pipeline.config.config_loader import load_config

logger = logging.getLogger(__name__)


# ==============================================================================
# Snapshot job
# ==============================================================================
class HolderSnapshotJob:
    """Snapshots holder counts for SPL tokens and persists them to the database.

    Opens a Solana RPC connection and a PostgreSQL pool on context
    entry.  The ``run_snapshot_for_mints`` and
    ``run_snapshot_from_database`` methods drive the actual work.

    Attributes:
        config: Pipeline configuration (RPC URLs, DB DSN, program IDs).
        rpc_client: Solana async RPC client.
        db_pool: asyncpg connection pool.
    """

    def __init__(self, config_path: str = None):
        """Initialise the job with optional configuration path.

        Args:
            config_path: Path to a YAML config file.  When None the
                default config location is used.
        """
        self.config = load_config(config_path)
        self.rpc_client: AsyncClient = None
        self.db_pool: asyncpg.Pool = None

    async def __aenter__(self):
        """Create the RPC client and database connection pool."""
        self.rpc_client = AsyncClient(self.config.rpc.url)
        self.db_pool = await asyncpg.create_pool(self.config.database.dsn)
        return self

    async def __aexit__(self, *exc):
        """Close the RPC client and database pool."""
        if self.rpc_client:
            await self.rpc_client.close()
        if self.db_pool:
            await self.db_pool.close()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    async def run_snapshot_for_mints(self, mints: List[str]) -> None:
        """Run holder snapshots for an explicit list of mint addresses.

        Args:
            mints: List of SPL token mint address strings.
        """
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
        """Run snapshots for all mints with recent swap activity.

        Queries the ``swap_ticks`` table for distinct mints active in
        the last seven days and snapshots each one.
        """
        async with self.db_pool.acquire() as conn:
            recent_mints = await conn.fetch("""
                SELECT DISTINCT mint
                FROM swap_ticks
                WHERE ts >= NOW() - INTERVAL '7 days'
                ORDER BY mint
            """)

            mint_addresses = [row['mint'] for row in recent_mints]
            await self.run_snapshot_for_mints(mint_addresses)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _get_holder_count(self, mint: str) -> int:
        """Get the unique holder count for a specific mint address.

        Sends a ``getProgramAccounts`` request filtered by the token
        mint and counts unique owner addresses with non-zero balances.

        Args:
            mint: The SPL token mint address.

        Returns:
            The number of unique holders, or None on failure.
        """
        try:
            mint_pubkey = PublicKey(mint)

            response = await self.rpc_client.get_program_accounts(
                PublicKey(self.config.programs.token_program),
                encoding="jsonParsed",
                filters=[
                    {"dataSize": 165},  # Token account size
                    {"memcmp": {"offset": 0, "bytes": str(mint_pubkey)}}
                ]
            )

            if response.value is None:
                return 0

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
        """Persist a holder count snapshot to the database.

        Uses ``ON CONFLICT ... DO UPDATE`` to overwrite an existing
        snapshot for the same mint and timestamp.

        Args:
            mint: The SPL token mint address.
            holder_count: The number of unique holders.
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO holder_snapshots (mint, snapshot_time, holder_count)
                VALUES ($1, NOW(), $2)
                ON CONFLICT (mint, snapshot_time) DO UPDATE
                SET holder_count = $2
            """, mint, holder_count)


# ==============================================================================
# CLI entry point
# ==============================================================================
async def main():
    """Parse arguments and run the holder snapshot job."""
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
