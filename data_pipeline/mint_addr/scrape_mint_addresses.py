#!/usr/bin/env python3
"""
Solana Mint Address Scraper via Blockchain RPC.

Collects unique Solana token mint addresses from multiple sources:
- Direct blockchain scanning via Solana RPC (Token Program accounts).
- DexScreener API for DEX-listed tokens with creation date filtering.
- Jupiter aggregator token list for broad coverage.
- Incremental checkpointing with resume-on-restart support.

Target: 100,000 unique mint addresses aged 3-12 months.

Author: ML-Bullx Team
Date: 2025-08-01
"""

# ============================================================================
# Standard Library Imports
# ============================================================================
import asyncio
import csv
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

# ============================================================================
# Third-Party Imports
# ============================================================================
import aiohttp
import pandas as pd
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solana.rpc.types import TokenAccountOpts
import solders.pubkey as Pubkey
from solders.signature import Signature

# ============================================================================
# Logging Configuration
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mint_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# Scraper Class
# ============================================================================

class SolanaMintScraper:
    """Scraper for collecting Solana mint addresses via blockchain RPC.

    Connects to Solana RPC endpoints to scan Token Program transactions,
    extracts mint addresses from token creation instructions, and filters
    results by age (3 months to 1 year). Supplements blockchain data with
    DexScreener and Jupiter API results. Supports checkpointing for
    long-running collection sessions.
    """

    def __init__(self, rpc_endpoints: List[str], target_count: int = 100000):
        """Initialize the scraper with RPC endpoints and collection target.

        Args:
            rpc_endpoints: List of Solana RPC endpoint URLs to rotate through.
            target_count: Number of unique mint addresses to collect before
                stopping.
        """
        self.rpc_endpoints = rpc_endpoints
        self.target_count = target_count
        self.mint_addresses: Set[str] = set()
        # Age range: 3 months to 1 year old
        self.min_cutoff_date = datetime.now() - timedelta(days=365)  # 1 year ago (oldest)
        self.max_cutoff_date = datetime.now() - timedelta(days=90)   # 3 months ago (newest)
        self.current_endpoint_index = 0

    async def get_client(self) -> AsyncClient:
        """Create an AsyncClient using the next RPC endpoint in rotation.

        Returns:
            An AsyncClient instance connected to the selected endpoint.
        """
        endpoint = self.rpc_endpoints[self.current_endpoint_index]
        self.current_endpoint_index = (self.current_endpoint_index + 1) % len(self.rpc_endpoints)
        return AsyncClient(endpoint)

    async def get_token_program_accounts(self, client: AsyncClient, before_signature: Optional[str] = None) -> List[Dict]:
        """Fetch recent Token Program transaction signatures from Solana.

        Queries the RPC endpoint for confirmed signatures associated with
        the SPL Token Program, supporting cursor-based pagination.

        Args:
            client: An active Solana RPC async client.
            before_signature: Optional signature to paginate from (fetches
                signatures older than this one).

        Returns:
            A list of signature info objects, or an empty list on failure.
        """
        try:
            token_program_id = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

            opts = {
                "limit": 1000,
                "commitment": Commitment("confirmed")
            }

            if before_signature:
                opts["before"] = before_signature

            response = await client.get_signatures_for_address(
                Pubkey.from_string(token_program_id),
                **opts
            )

            if response.value:
                return response.value
            return []

        except Exception as e:
            logger.error(f"Error getting token program accounts: {e}")
            return []

    async def get_transaction_details(self, client: AsyncClient, signature: str) -> Optional[Dict]:
        """Retrieve full transaction data for a given signature.

        Args:
            client: An active Solana RPC async client.
            signature: The base58-encoded transaction signature to look up.

        Returns:
            The transaction data dictionary, or None if retrieval fails.
        """
        try:
            response = await client.get_transaction(
                Signature.from_string(signature),
                encoding="json",
                commitment=Commitment("confirmed"),
                max_supported_transaction_version=0
            )

            if response.value:
                return response.value
            return None

        except Exception as e:
            logger.debug(f"Error getting transaction details for {signature}: {e}")
            return None

    def extract_mint_addresses_from_transaction(self, transaction_data: Dict) -> Set[str]:
        """Extract mint addresses from a parsed transaction.

        Inspects both the instruction accounts (looking for Token Program
        and Token-2022 Program mint initialization) and the post-transaction
        token balances to identify mint addresses.

        Args:
            transaction_data: The full transaction data dictionary as
                returned by the RPC.

        Returns:
            A set of mint address strings found in the transaction.
        """
        mint_addresses = set()

        try:
            if not transaction_data.get('transaction'):
                return mint_addresses

            # Check account keys for potential mint addresses
            message = transaction_data['transaction'].get('message', {})
            account_keys = message.get('accountKeys', [])

            # Look for token creation instructions
            instructions = message.get('instructions', [])

            for instruction in instructions:
                # Check if this is a token initialization instruction
                program_id_index = instruction.get('programIdIndex')
                if program_id_index is not None and program_id_index < len(account_keys):
                    program_id = account_keys[program_id_index]

                    # Token Program or Token-2022 Program
                    if program_id in ['TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
                                    'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb']:

                        accounts = instruction.get('accounts', [])
                        if accounts and len(accounts) > 0:
                            # First account in mint initialization is usually the mint
                            mint_index = accounts[0]
                            if mint_index < len(account_keys):
                                mint_addresses.add(account_keys[mint_index])

            # Also check post token balances for mint addresses
            meta = transaction_data.get('meta', {})
            post_token_balances = meta.get('postTokenBalances', [])

            for balance in post_token_balances:
                mint = balance.get('mint')
                if mint:
                    mint_addresses.add(mint)

        except Exception as e:
            logger.debug(f"Error extracting mint addresses: {e}")

        return mint_addresses

    def is_transaction_old_enough(self, transaction_data: Dict) -> bool:
        """Check whether a transaction falls within the target age range.

        The target age range is 3 months to 1 year old, as defined by
        min_cutoff_date and max_cutoff_date.

        Args:
            transaction_data: Transaction data dictionary containing a
                'blockTime' field.

        Returns:
            True if the transaction timestamp is within the target range,
            False otherwise.
        """
        try:
            block_time = transaction_data.get('blockTime')
            if block_time:
                tx_datetime = datetime.fromtimestamp(block_time)
                return self.min_cutoff_date <= tx_datetime <= self.max_cutoff_date
        except Exception as e:
            logger.debug(f"Error checking transaction age: {e}")

        return False

    async def scrape_mint_addresses_batch(self, client: AsyncClient, before_signature: Optional[str] = None) -> tuple[Set[str], Optional[str]]:
        """Scrape a single batch of mint addresses from the blockchain.

        Fetches a page of Token Program signatures, retrieves transaction
        details for each, and extracts mint addresses from those that fall
        within the target age range.

        Args:
            client: An active Solana RPC async client.
            before_signature: Optional pagination cursor signature.

        Returns:
            A tuple of (mint_addresses_found, last_signature) where
            last_signature can be used for the next pagination call.
        """
        batch_mints = set()
        last_signature = None

        try:
            signatures = await self.get_token_program_accounts(client, before_signature)

            if not signatures:
                return batch_mints, None

            for sig_info in signatures:
                if len(self.mint_addresses) >= self.target_count:
                    break

                signature = sig_info.signature
                last_signature = signature

                # Check if transaction is in our target age range
                if sig_info.block_time:
                    tx_datetime = datetime.fromtimestamp(sig_info.block_time)
                    if not (self.min_cutoff_date <= tx_datetime <= self.max_cutoff_date):
                        continue  # Skip transactions outside our age range

                # Get transaction details
                tx_data = await self.get_transaction_details(client, signature)

                if tx_data and self.is_transaction_old_enough(tx_data):
                    mints = self.extract_mint_addresses_from_transaction(tx_data)
                    batch_mints.update(mints)

                # Rate limiting
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in batch scraping: {e}")

        return batch_mints, last_signature

    # ========================================================================
    # API-Based Scraping Methods
    # ========================================================================

    async def scrape_from_dexscreener_api(self) -> Set[str]:
        """Scrape mint addresses from the DexScreener API.

        Queries DexScreener for Solana token pairs and filters by creation
        date to include only tokens within the target age range.

        Returns:
            A set of mint address strings collected from DexScreener.
        """
        mint_addresses = set()

        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.dexscreener.com/latest/dex/tokens/solana"

                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()

                        for pair in data.get('pairs', []):
                            created_at = pair.get('pairCreatedAt')
                            if created_at:
                                created_date = datetime.fromtimestamp(created_at / 1000)
                                if self.min_cutoff_date <= created_date <= self.max_cutoff_date:
                                    base_token = pair.get('baseToken', {})
                                    quote_token = pair.get('quoteToken', {})

                                    if base_token.get('address'):
                                        mint_addresses.add(base_token['address'])
                                    if quote_token.get('address'):
                                        mint_addresses.add(quote_token['address'])

                            await asyncio.sleep(0.05)  # Rate limiting

        except Exception as e:
            logger.error(f"Error scraping from DexScreener: {e}")

        return mint_addresses

    async def scrape_from_jupiter_api(self) -> Set[str]:
        """Scrape mint addresses from the Jupiter aggregator token list.

        Fetches the full Jupiter token list and collects addresses up to
        one quarter of the target count. Age filtering is not available
        from this source and must be applied separately.

        Returns:
            A set of mint address strings collected from Jupiter.
        """
        mint_addresses = set()

        try:
            async with aiohttp.ClientSession() as session:
                url = "https://token.jup.ag/all"

                async with session.get(url) as response:
                    if response.status == 200:
                        tokens = await response.json()

                        for token in tokens:
                            address = token.get('address')
                            if address:
                                mint_addresses.add(address)

                                if len(mint_addresses) >= self.target_count // 4:
                                    break

        except Exception as e:
            logger.error(f"Error scraping from Jupiter: {e}")

        return mint_addresses

    # ========================================================================
    # Orchestration
    # ========================================================================

    async def run_scraping(self) -> None:
        """Run the complete multi-source scraping process.

        Executes blockchain RPC scanning in batches first, then supplements
        with DexScreener and Jupiter API data if the target has not yet been
        reached. Saves periodic checkpoints during collection.
        """
        logger.info(f"Starting scraping process. Target: {self.target_count} mint addresses")
        logger.info(f"Age range: {self.min_cutoff_date.strftime('%Y-%m-%d')} to {self.max_cutoff_date.strftime('%Y-%m-%d')}")
        logger.info(f"Collecting tokens between 3 months and 1 year old")

        before_signature = None
        batch_count = 0

        # Method 1: Direct blockchain scraping
        while len(self.mint_addresses) < self.target_count:
            batch_count += 1
            logger.info(f"Processing batch {batch_count}. Current count: {len(self.mint_addresses)}")

            client = await self.get_client()

            try:
                batch_mints, last_sig = await self.scrape_mint_addresses_batch(client, before_signature)

                new_mints = batch_mints - self.mint_addresses
                self.mint_addresses.update(new_mints)

                logger.info(f"Batch {batch_count}: Found {len(new_mints)} new mint addresses")

                if not last_sig:
                    logger.info("No more signatures to process")
                    break

                before_signature = last_sig

                # Progress checkpoint every 10 batches
                if batch_count % 10 == 0:
                    self.save_checkpoint()

            except Exception as e:
                logger.error(f"Error in batch {batch_count}: {e}")
                await asyncio.sleep(5)  # Wait before retrying

            finally:
                await client.close()

            # Rate limiting between batches
            await asyncio.sleep(1)

        # Method 2: API-based scraping to fill gaps
        if len(self.mint_addresses) < self.target_count:
            logger.info("Supplementing with API-based scraping...")

            # DexScreener
            dex_mints = await self.scrape_from_dexscreener_api()
            new_dex_mints = dex_mints - self.mint_addresses
            self.mint_addresses.update(new_dex_mints)
            logger.info(f"Added {len(new_dex_mints)} addresses from DexScreener")

            # Jupiter
            if len(self.mint_addresses) < self.target_count:
                jupiter_mints = await self.scrape_from_jupiter_api()
                new_jupiter_mints = jupiter_mints - self.mint_addresses
                self.mint_addresses.update(new_jupiter_mints)
                logger.info(f"Added {len(new_jupiter_mints)} addresses from Jupiter")

        logger.info(f"Scraping completed. Total unique mint addresses: {len(self.mint_addresses)}")

    # ========================================================================
    # Checkpoint and Export
    # ========================================================================

    def save_checkpoint(self) -> None:
        """Save current collection progress to a JSON checkpoint file.

        Writes the full set of collected mint addresses along with a count
        and timestamp to disk for resume-on-restart support.
        """
        checkpoint_file = "mint_addresses_checkpoint.json"

        try:
            with open(checkpoint_file, 'w') as f:
                json.dump({
                    'mint_addresses': list(self.mint_addresses),
                    'count': len(self.mint_addresses),
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)

            logger.info(f"Checkpoint saved with {len(self.mint_addresses)} addresses")

        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")

    def load_checkpoint(self) -> bool:
        """Load collection progress from a previous checkpoint file.

        Returns:
            True if a checkpoint was successfully loaded, False otherwise.
        """
        checkpoint_file = "mint_addresses_checkpoint.json"

        try:
            if os.path.exists(checkpoint_file):
                with open(checkpoint_file, 'r') as f:
                    data = json.load(f)

                self.mint_addresses = set(data.get('mint_addresses', []))
                logger.info(f"Loaded checkpoint with {len(self.mint_addresses)} addresses")
                return True

        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}")

        return False

    def export_to_csv(self, filename: str = "solana_mint_addresses.csv") -> None:
        """Export collected mint addresses to CSV and plain text files.

        Creates a CSV file with columns for mint address, collection
        timestamp, and index. Also writes a companion text file with one
        address per line.

        Args:
            filename: Output CSV filename. A corresponding .txt file is
                created alongside it.
        """
        try:
            mint_list = list(self.mint_addresses)

            df = pd.DataFrame({
                'mint_address': mint_list,
                'collected_at': datetime.now().isoformat(),
                'index': range(len(mint_list))
            })

            # Save to CSV
            output_path = os.path.join(os.path.dirname(__file__), filename)
            df.to_csv(output_path, index=False)

            logger.info(f"Exported {len(mint_list)} mint addresses to {output_path}")

            # Also save a simple txt file with just addresses
            txt_filename = filename.replace('.csv', '.txt')
            txt_path = os.path.join(os.path.dirname(__file__), txt_filename)

            with open(txt_path, 'w') as f:
                for mint in mint_list:
                    f.write(f"{mint}\n")

            logger.info(f"Also saved addresses to {txt_path}")

        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")


# ============================================================================
# Script Entry Point
# ============================================================================

async def main():
    """Run the full Solana mint address scraping pipeline.

    Initializes the scraper with multiple RPC endpoints, loads any existing
    checkpoint, executes the scraping process, and exports results. Handles
    keyboard interrupts gracefully by saving progress before exiting.
    """
    # RPC endpoints (use multiple for better reliability and rate limiting)
    rpc_endpoints = [
        "https://api.mainnet-beta.solana.com",
        "https://solana-api.projectserum.com",
        "https://api.solana.fm",
        # Add more RPC endpoints as needed
        # "https://your-custom-rpc-endpoint.com",
    ]

    # Initialize scraper
    scraper = SolanaMintScraper(rpc_endpoints, target_count=100000)

    # Load any existing checkpoint
    scraper.load_checkpoint()

    try:
        # Run scraping
        await scraper.run_scraping()

        # Export results
        scraper.export_to_csv("solana_mint_addresses_3months_old.csv")

        # Final statistics
        logger.info(f"Scraping completed successfully!")
        logger.info(f"Total unique mint addresses collected: {len(scraper.mint_addresses)}")
        logger.info(f"Target was: {scraper.target_count}")

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        scraper.save_checkpoint()
        scraper.export_to_csv("solana_mint_addresses_partial.csv")

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        scraper.save_checkpoint()


if __name__ == "__main__":
    asyncio.run(main())
