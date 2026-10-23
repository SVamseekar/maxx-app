"""PYUSD checkout: tagged amounts, read-only on-chain proof, replay protection."""

import asyncio
import time
from decimal import Decimal

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from maxx.config import settings
from maxx.main import app
from maxx.money import chain, ledger
from tests.conftest import sign_up
from tests.test_checkout import body, row

ME = "0x" + "ab" * 20
CONTRACT = "0x" + "cd" * 20


@pytest.fixture(autouse=True)
def simulator(monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "simulator")
    monkeypatch.setattr(settings, "pyusd_rpc_url", "")


def start(client, method="pyusd"):
    token = client.post("/checkout/propose", json=body(row())).json()["proposal_token"]
    return client.post(
        "/checkout/confirm",
        json={"proposal_token": token, "confirm_total": "125.00", "method": method},
    )


def test_amount_carries_an_order_tag_in_the_last_digits():
    units = chain.tagged_units(Decimal("125.00"), 417)
    assert units == 125_000_417 and chain.display_units(units) == "125.000417"
    assert chain.tagged_units(Decimal("0.99"), 5) == 990_005


def test_config_advertises_pyusd_with_the_simulated_label():
    with TestClient(app) as client:
        crypto = client.get("/money/config").json()["crypto"]
    assert crypto["enabled"] and crypto["asset"] == "PYUSD" and crypto["simulated"] is True


def test_pay_with_pyusd_end_to_end_on_the_simulated_chain():
    with TestClient(app) as client:
        sign_up(client)
        order = start(client).json()
        assert order["method"] == "pyusd" and order["pyusd"]["simulated"] is True
        assert order["pyusd"]["amount"].startswith("125.000")
        # PayPal capture is the wrong tool for a PYUSD order.
        assert client.post(f"/checkout/orders/{order['order_id']}/capture").status_code == 409
        sent = client.post(
            "/checkout/pyusd/simulate-send", json={"order_id": order["order_id"]}
        ).json()
        done = client.post(
            "/checkout/pyusd/verify",
            json={"order_id": order["order_id"], "tx_hash": sent["tx_hash"]},
        )
        assert done.status_code == 200 and done.json()["tx_hash"] == sent["tx_hash"]
        payment = ledger.by_order(order["order_id"])
        assert payment["status"] == "CAPTURED" and str(payment["captured_amount"]) == "125.00"
        receipt = client.get("/money/receipts").json()[0]
        assert receipt["method"] == "pyusd" and receipt["paypal"]["pyusd_tx"] == sent["tx_hash"]
        # Same order again is a harmless repeat; the transaction cannot pay a second order.
        again = start(client).json()
        assert again["order_id"] != order["order_id"]
        reuse = client.post(
            "/checkout/pyusd/verify",
            json={"order_id": again["order_id"], "tx_hash": sent["tx_hash"]},
        )
        assert reuse.status_code == 409  # wrong tag: the amount belongs to the first order


def test_wrong_amount_and_unknown_transaction_are_refused():
    with TestClient(app) as client:
        sign_up(client)
        order = start(client).json()
        missing = client.post(
            "/checkout/pyusd/verify",
            json={"order_id": order["order_id"], "tx_hash": "0x" + "1" * 64},
        )
        assert missing.status_code == 409 and "not on the chain" in missing.json()["detail"]
        bad = client.post(
            "/checkout/pyusd/verify", json={"order_id": order["order_id"], "tx_hash": "nope"}
        )
        assert bad.status_code == 409
        hash_ = chain.SimulatedChain().send(chain.deposit_address(), 125_000_000)  # missing the tag
        short = client.post(
            "/checkout/pyusd/verify", json={"order_id": order["order_id"], "tx_hash": hash_}
        )
        assert short.status_code == 409 and "exactly" in short.json()["detail"]
        assert ledger.by_order(order["order_id"])["status"] == "CREATED"


def test_someone_else_cannot_claim_my_order():
    with TestClient(app) as mine, TestClient(app) as theirs:
        sign_up(mine, "a@example.com")
        sign_up(theirs, "b@example.com")
        order = start(mine).json()
        sent = mine.post(
            "/checkout/pyusd/simulate-send", json={"order_id": order["order_id"]}
        ).json()
        taken = theirs.post(
            "/checkout/pyusd/verify",
            json={"order_id": order["order_id"], "tx_hash": sent["tx_hash"]},
        )
        assert taken.status_code == 404


def test_pyusd_is_off_without_a_chain(monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "sandbox")
    monkeypatch.setattr(settings, "paypal_client_id", "id")
    monkeypatch.setattr(settings, "paypal_client_secret", "secret")
    assert chain.get_chain() is None


# ---- the real JSON-RPC verifier -----------------------------------------------------------------


def receipt(units, to=ME, contract=CONTRACT, status="0x1", block="0x10"):
    topic = lambda a: "0x" + "0" * 24 + a[2:]  # noqa: E731
    return {
        "status": status,
        "blockNumber": block,
        "logs": [
            {
                "address": contract,
                "topics": [chain.TRANSFER_TOPIC, topic("0x" + "11" * 20), topic(to)],
                "data": hex(units),
            }
        ],
    }


def rpc(result, head="0x20"):
    def handler(request: httpx.Request):
        import json

        method = json.loads(request.content)["method"]
        if method == "eth_getBlockByNumber":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"timestamp": hex(int(time.time()))}},
            )
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": result if method != "eth_blockNumber" else head,
            },
        )

    return chain.RpcChain("https://rpc.example", httpx.MockTransport(handler))


@pytest.fixture
def real_chain(monkeypatch):
    monkeypatch.setattr(settings, "pyusd_contract", CONTRACT)
    monkeypatch.setattr(settings, "pyusd_deposit_address", ME)
    monkeypatch.setattr(settings, "pyusd_min_confirmations", 3)
    monkeypatch.setattr(settings, "paypal_mode", "off")


def test_rpc_verifier_accepts_the_exact_confirmed_transfer(real_chain):
    transfer = asyncio.run(rpc(receipt(125_000_417)).transfer("0x" + "9" * 64))
    assert (
        transfer.units == 125_000_417 and transfer.recipient == ME and transfer.confirmations == 17
    )
    chain.check(transfer, 125_000_417)


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"to": "0x" + "ee" * 20}, "different address"),
        ({"contract": "0x" + "ee" * 20}, "did not move PYUSD"),
        ({"status": "0x0"}, "failed"),
    ],
)
def test_rpc_verifier_rejects_wrong_recipient_token_or_failed_tx(real_chain, changes, expected):
    with pytest.raises(chain.ChainError, match=expected):
        transfer = asyncio.run(rpc(receipt(125_000_417, **changes)).transfer("0x" + "9" * 64))
        chain.check(transfer, 125_000_417)


def test_rpc_verifier_waits_for_confirmations(real_chain):
    transfer = asyncio.run(
        rpc(receipt(125_000_417, block="0x1f"), head="0x20").transfer("0x" + "9" * 64)
    )
    with pytest.raises(chain.ChainError, match="confirmations"):
        chain.check(transfer, 125_000_417)


def test_rpc_verifier_reports_a_pending_transaction(real_chain):
    with pytest.raises(chain.ChainError, match="not on the chain"):
        asyncio.run(rpc(None).transfer("0x" + "9" * 64))


def test_a_transaction_claimed_elsewhere_cannot_pay_again():
    from sqlalchemy import insert

    from maxx import schema, storage

    with TestClient(app) as client:
        sign_up(client)
        order = start(client).json()
        sent = client.post(
            "/checkout/pyusd/simulate-send", json={"order_id": order["order_id"]}
        ).json()
        with storage.get_store().engine.begin() as db:  # as if a concurrent request won the race
            db.execute(
                insert(schema.used_transactions).values(
                    tx_hash=sent["tx_hash"][2:], payment_id="other", used_at=1
                )
            )
        late = client.post(
            "/checkout/pyusd/verify",
            json={"order_id": order["order_id"], "tx_hash": sent["tx_hash"]},
        )
        assert late.status_code == 409 and "already used" in late.json()["detail"]
        assert ledger.by_order(order["order_id"])["status"] == "CREATED"


def test_open_orders_for_the_same_amount_never_share_a_tag(monkeypatch):
    with TestClient(app) as mine, TestClient(app) as theirs:
        sign_up(mine, "a@example.com")
        sign_up(theirs, "b@example.com")
        first, second = start(mine).json(), start(theirs).json()
        assert first["pyusd"]["units"] != second["pyusd"]["units"]
        monkeypatch.setattr(chain, "new_tag", lambda: 500)  # worst case: every draw collides
        third = start(mine)  # same offer, same method: the open order is reused, not duplicated
        assert third.json()["order_id"] == first["order_id"]


def test_a_transfer_older_than_the_order_is_refused(monkeypatch):
    with TestClient(app) as client:
        sign_up(client)
        order = start(client).json()
        real = time.time
        monkeypatch.setattr(chain.time, "time", lambda: real() - 3600)
        old = chain.SimulatedChain().send(chain.deposit_address(), int(order["pyusd"]["units"]))
        monkeypatch.setattr(chain.time, "time", real)
        refused = client.post(
            "/checkout/pyusd/verify", json={"order_id": order["order_id"], "tx_hash": old}
        )
        assert refused.status_code == 409 and "before this order" in refused.json()["detail"]
