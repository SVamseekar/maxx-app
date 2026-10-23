"""PYUSD (PayPal's dollar stablecoin) payment proof, read-only.

Maxx never holds a wallet key. The buyer sends PYUSD from their own wallet to the deposit address
with an exact amount that carries a per-order tag in its last digits (PYUSD has six decimals, so
$125.00 becomes 125.000417 for tag 417). Maxx then reads the transaction receipt from an Ethereum
JSON-RPC node and accepts it only if the token contract, recipient, exact amount and confirmation
depth all match, and the transaction has not been used for another order.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass
from decimal import Decimal

import httpx2 as httpx
from sqlalchemy import select

from maxx import schema, storage
from maxx.config import settings

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DECIMALS = 6
TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
SIMULATED_ADDRESS = "0x51A0000000000000000000000000000000005151"
SIMULATED_CONTRACT = "0x51A0000000000000000000000000000000000001"


class ChainError(Exception):
    """The proof was not accepted. The message is safe to show the buyer."""


@dataclass
class Transfer:
    contract: str
    sender: str
    recipient: str
    units: int
    confirmations: int
    timestamp: int = 0


def tagged_units(amount: Decimal, tag: int) -> int:
    """Smallest-unit amount for a USD price, with the order tag in the last three digits."""
    base = int((amount * 10**DECIMALS).to_integral_value())
    return base - base % 1000 + tag % 1000


def new_tag() -> int:
    return secrets.randbelow(900) + 100


def display_units(units: int) -> str:
    return f"{Decimal(units) / 10**DECIMALS:.6f}"


class RpcChain:
    simulated = False

    def __init__(self, url: str, transport=None):
        self.url, self.transport = url, transport

    async def _rpc(self, method: str, params: list):
        async with httpx.AsyncClient(
            timeout=settings.provider_timeout, transport=self.transport
        ) as http:
            try:
                response = await http.post(
                    self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
                )
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ChainError("The blockchain node is unreachable. Try again shortly.") from exc
        if "error" in body:
            raise ChainError("The blockchain node rejected the lookup.")
        return body.get("result")

    async def transfer(self, tx_hash: str) -> Transfer:
        receipt = await self._rpc("eth_getTransactionReceipt", [tx_hash])
        if not receipt:
            raise ChainError("That transaction is not on the chain yet. Wait a minute and retry.")
        if receipt.get("status") != "0x1":
            raise ChainError("That transaction failed on the chain.")
        contract = settings.pyusd_contract.lower()
        logs = [
            log
            for log in receipt.get("logs", [])
            if log.get("address", "").lower() == contract
            and log.get("topics", [None])[0] == TRANSFER_TOPIC
            and len(log["topics"]) == 3
        ]
        if not logs:
            raise ChainError("That transaction did not move PYUSD.")
        log = logs[0]
        head = int(await self._rpc("eth_blockNumber", []), 16)
        mined = int(receipt["blockNumber"], 16)
        block = await self._rpc("eth_getBlockByNumber", [receipt["blockNumber"], False])
        if not block or "timestamp" not in block:
            raise ChainError("The blockchain node could not date that transaction. Retry shortly.")
        return Transfer(
            contract=log["address"].lower(),
            sender="0x" + log["topics"][1][-40:],
            recipient="0x" + log["topics"][2][-40:],
            units=int(log["data"], 16),
            confirmations=max(0, head - mined + 1),
            timestamp=int(block["timestamp"], 16),
        )


class SimulatedChain:
    """A labelled stand-in: the demo wallet button writes a transfer, the verifier reads it."""

    simulated = True

    def send(self, recipient: str, units: int) -> str:
        tx_hash = "0x" + secrets.token_hex(32)
        document = {
            "contract": SIMULATED_CONTRACT.lower(),
            "sender": "0x" + "5e" * 20,
            "recipient": recipient.lower(),
            "units": units,
            "confirmations": 12,
            "timestamp": int(time.time()),
        }
        with storage.get_store().engine.begin() as db:
            db.execute(
                schema.simulator_objects.insert().values(
                    key=f"chain:{tx_hash}", document=json.dumps(document)
                )
            )
        return tx_hash

    async def transfer(self, tx_hash: str) -> Transfer:
        with storage.get_store().engine.connect() as db:
            row = db.execute(
                select(schema.simulator_objects.c.document).where(
                    schema.simulator_objects.c.key == f"chain:{tx_hash.lower()}"
                )
            ).first()
        if not row:
            raise ChainError("That transaction is not on the chain yet. Wait a minute and retry.")
        return Transfer(**json.loads(row[0]))


def get_chain():
    if settings.paypal_mode == "simulator" and not settings.pyusd_rpc_url:
        return SimulatedChain()
    if settings.pyusd_rpc_url and settings.pyusd_contract and settings.pyusd_deposit_address:
        return RpcChain(settings.pyusd_rpc_url)
    return None


def deposit_address() -> str:
    if settings.pyusd_deposit_address:
        return settings.pyusd_deposit_address
    return SIMULATED_ADDRESS if settings.paypal_mode == "simulator" else ""


def contract_address() -> str:
    return settings.pyusd_contract or (
        SIMULATED_CONTRACT if settings.paypal_mode == "simulator" else ""
    )


def check(transfer: Transfer, expected_units: int, not_before: int = 0) -> None:
    """Accept only the exact payment: token, recipient, amount, depth and age."""
    if transfer.contract != contract_address().lower():
        raise ChainError("That transfer used a different token.")
    if transfer.recipient != deposit_address().lower():
        raise ChainError("That transfer went to a different address.")
    if transfer.units != expected_units:
        raise ChainError(
            f"The amount must be exactly {display_units(expected_units)} PYUSD; "
            f"you sent {display_units(transfer.units)}."
        )
    if transfer.timestamp < not_before:
        raise ChainError("That transfer was sent before this order existed.")
    needed = 1 if isinstance(get_chain(), SimulatedChain) else settings.pyusd_min_confirmations
    if transfer.confirmations < needed:
        raise ChainError(
            f"Waiting for confirmations ({transfer.confirmations} of {needed}). Retry in a minute."
        )
