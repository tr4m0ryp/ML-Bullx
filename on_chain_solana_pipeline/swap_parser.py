"""
Swap parser for Solana AMM transactions.

- Extracts price, volume, and token mints from on-chain transaction
  logs produced by Jupiter, Raydium, Orca, and other DEX programs.
- Dispatches parsing to program-specific handlers based on the
  ``programId`` found in inner instructions.
- Provides a helper for decoding base-64 encoded instruction data
  into raw bytes for further analysis.

Author: ML-Bullx Team
Date:   2025-08-01
"""

# ==============================================================================
# Standard library imports
# ==============================================================================
import base64
import logging
import struct
from datetime import datetime
from typing import Any, Dict, List, Optional

# ==============================================================================
# Local imports
# ==============================================================================
from on_chain_solana_pipeline.config.config_loader import PipelineConfig

logger = logging.getLogger(__name__)


# ==============================================================================
# Parser class
# ==============================================================================
class SwapParser:
    """Parses swap transactions from different Solana AMM programs.

    Iterates over the inner instructions of a transaction and delegates
    to program-specific handlers (Jupiter, Raydium, etc.) to extract
    ``SwapTick`` records.

    Attributes:
        config: Pipeline configuration containing program addresses.
    """

    def __init__(self, config: PipelineConfig):
        """Initialise the parser with pipeline configuration.

        Args:
            config: A ``PipelineConfig`` whose ``programs`` field
                contains the program IDs to match against.
        """
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def parse_transaction(self, tx_data: Dict[str, Any]) -> List:
        """Parse a transaction and extract swap ticks.

        Args:
            tx_data: The full parsed transaction dict as returned by
                ``getTransaction`` with ``jsonParsed`` encoding.

        Returns:
            A list of ``SwapTick`` objects extracted from the
            transaction.  Returns an empty list when the transaction
            is missing metadata, failed, or contains no recognisable
            swap instructions.
        """
        from helius_consumer import SwapTick  # Import here to avoid circular import

        if not tx_data or "meta" not in tx_data:
            return []

        # Check if transaction was successful
        if tx_data["meta"]["err"]:
            return []

        swap_ticks = []
        block_time = tx_data.get("blockTime")
        if not block_time:
            return []

        timestamp = datetime.fromtimestamp(block_time)
        signature = tx_data.get("transaction", {}).get("signatures", [""])[0]

        # Parse different program logs
        inner_instructions = tx_data["meta"].get("innerInstructions", [])

        for inner_instruction in inner_instructions:
            for instruction in inner_instruction.get("instructions", []):
                program_id = instruction.get("programId")

                if program_id == self.config.programs.jupiter_v6:
                    tick = await self._parse_jupiter_swap(instruction, timestamp, signature)
                    if tick:
                        swap_ticks.append(tick)

                elif program_id == self.config.programs.raydium_amm:
                    tick = await self._parse_raydium_swap(instruction, timestamp, signature)
                    if tick:
                        swap_ticks.append(tick)

        return swap_ticks

    # ------------------------------------------------------------------
    # Program-specific parsers
    # ------------------------------------------------------------------
    async def _parse_jupiter_swap(self, instruction: Dict[str, Any], timestamp: datetime, signature: str) -> Optional[Any]:
        """Parse a Jupiter v6 aggregator swap instruction.

        This is a simplified stub.  A full implementation would decode
        the instruction data to extract input/output amounts and
        identify the source/destination token accounts.

        Args:
            instruction: A single inner instruction dict.
            timestamp: Block timestamp of the transaction.
            signature: The transaction signature string.

        Returns:
            A ``SwapTick`` on success, or None when parsing is not yet
            implemented or the instruction format is unrecognised.
        """
        try:
            accounts = instruction.get("accounts", [])

            if len(accounts) < 4:
                return None

            # TODO: Implement Jupiter swap parsing.
            # Steps needed:
            # 1. Decode instruction data to get swap amounts
            # 2. Identify source/destination tokens from accounts
            # 3. Calculate price from input/output amounts
            logger.warning("Jupiter swap parsing not yet implemented")
            return None

        except Exception as e:
            logger.debug(f"Error parsing Jupiter swap: {e}")
            return None

    async def _parse_raydium_swap(self, instruction: Dict[str, Any], timestamp: datetime, signature: str) -> Optional[Any]:
        """Parse a Raydium AMM swap instruction.

        Args:
            instruction: A single inner instruction dict.
            timestamp: Block timestamp of the transaction.
            signature: The transaction signature string.

        Returns:
            A ``SwapTick`` on success, or None when parsing is not yet
            implemented or the instruction format is unrecognised.
        """
        try:
            # TODO: Implement Raydium swap parsing.
            logger.warning("Raydium swap parsing not yet implemented")
            return None

        except Exception as e:
            logger.debug(f"Error parsing Raydium swap: {e}")
            return None

    # ------------------------------------------------------------------
    # Price calculation
    # ------------------------------------------------------------------
    def _calculate_price(self, amount_in: int, amount_out: int, decimals_in: int, decimals_out: int) -> float:
        """Calculate a swap price from raw token amounts.

        Args:
            amount_in: Raw input amount (before decimal adjustment).
            amount_out: Raw output amount (before decimal adjustment).
            decimals_in: Decimal places for the input token.
            decimals_out: Decimal places for the output token.

        Returns:
            The price as ``output / input`` after normalising both
            amounts by their respective decimal places.  Returns 0.0
            when the input amount is zero.
        """
        if amount_in == 0:
            return 0.0

        # Normalize amounts by decimals
        normalized_in = amount_in / (10 ** decimals_in)
        normalized_out = amount_out / (10 ** decimals_out)

        return normalized_out / normalized_in if normalized_in > 0 else 0.0


# ==============================================================================
# Utility functions
# ==============================================================================
def decode_instruction_data(data: str) -> bytes:
    """Decode base-64 encoded instruction data into raw bytes.

    Args:
        data: A base-64 encoded string from a transaction instruction.

    Returns:
        The decoded bytes, or an empty ``bytes`` object on failure.
    """
    try:
        return base64.b64decode(data)
    except Exception:
        return b""
