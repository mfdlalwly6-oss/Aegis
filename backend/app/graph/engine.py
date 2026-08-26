"""AEGIS Graph Intelligence Engine — NetworkX-based, fed from transaction history.
Detects shared devices, shared IPs, known-fraud hops, and community rings.
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import structlog

from app.models.schemas import GraphSignal, Transaction

logger = structlog.get_logger(__name__)


class GraphEngine:
    def __init__(self):
        self._g = nx.MultiDiGraph()
        self._known_fraud: set[str] = set()
        self._device_accounts: dict[str, set[str]] = {}
        self._ip_accounts: dict[str, set[str]] = {}
        self._account_links: dict[str, set[str]] = {}

    def bootstrap(self, transactions: list[dict]) -> None:
        for tx in reversed(transactions):
            self._add_dict(tx)
        logger.info("graph.bootstrapped", nodes=self._g.number_of_nodes())

    def _add_dict(self, tx: dict) -> None:
        sender = f"acct:{tx['sender_account_id']}"
        benef = f"acct:{tx['beneficiary_account_id']}"
        txn = f"tx:{tx['tx_id']}"
        self._g.add_node(sender, type="account")
        self._g.add_node(benef, type="account")
        self._g.add_node(txn, type="transaction")
        self._g.add_edge(sender, txn, rel="sends")
        self._g.add_edge(txn, benef, rel="to")
        dev = tx.get("device_id")
        ip = tx.get("ip")
        if dev:
            d = f"device:{dev}"
            self._g.add_node(d, type="device")
            self._g.add_edge(sender, d, rel="uses")
            self._device_accounts.setdefault(dev, set()).add(tx["sender_account_id"])
        if ip:
            i = f"ip:{ip}"
            self._g.add_node(i, type="ip")
            self._g.add_edge(sender, i, rel="from")
            self._ip_accounts.setdefault(ip, set()).add(tx["sender_account_id"])
        self._account_links.setdefault(tx["sender_account_id"], set()).add(
            tx["beneficiary_account_id"]
        )

    def add_transaction(self, tx: Transaction) -> None:
        self._add_dict(
            {
                "tx_id": tx.tx_id,
                "sender_account_id": tx.sender_account_id,
                "beneficiary_account_id": tx.beneficiary_account_id,
                "device_id": tx.device.device_id if tx.device else None,
                "ip": str(tx.device.ip) if tx.device and tx.device.ip else None,
            }
        )

    def mark_fraud(self, account_id: str) -> None:
        self._known_fraud.add(f"acct:{account_id}")

    def score(self, tx: Transaction) -> GraphSignal:
        dev = tx.device.device_id if tx.device else None
        ip = str(tx.device.ip) if tx.device and tx.device.ip else None
        shared_dev = (
            len(self._device_accounts.get(dev, set()) - {tx.sender_account_id}) if dev else 0
        )
        shared_ip = len(self._ip_accounts.get(ip, set()) - {tx.sender_account_id}) if ip else 0
        linked = len(self._account_links.get(tx.sender_account_id, set()))

        # hops to known fraud
        u = f"acct:{tx.sender_account_id}"
        hops = None
        for f in self._known_fraud:
            if f not in self._g:
                continue
            try:
                p = nx.shortest_path_length(self._g.to_undirected(as_view=True), u, f)
                hops = p if hops is None else min(hops, p)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

        score = min(1.0, shared_dev * 0.15 + shared_ip * 0.10 + max(0, linked - 5) * 0.04)
        if hops is not None and hops <= 2:
            score = min(1.0, score + 0.30)

        reasons = []
        if shared_dev:
            reasons.append(f"shared_device_{shared_dev}")
        if shared_ip:
            reasons.append(f"shared_ip_{shared_ip}")
        if linked >= 5:
            reasons.append(f"linked_accounts_{linked}")
        if hops is not None and hops <= 2:
            reasons.append(f"within_{hops}_hops_of_fraud")

        return GraphSignal(
            score=round(score, 4),
            reason=", ".join(reasons) if reasons else None,
            shared_device_count=shared_dev,
            shared_ip_count=shared_ip,
            linked_accounts=linked,
            hops_to_known_fraud=hops,
            ring_size=None,
            pagerank_score=None,
        )

    def find_rings(self, min_size: int = 5) -> list[dict[str, Any]]:
        try:
            from networkx.algorithms.community import louvain_communities

            comms = louvain_communities(self._g.to_undirected(as_view=True), seed=42)
        except Exception:
            return []
        return [
            {"community_id": i, "size": len(c), "members": sorted(c)[:20]}
            for i, c in enumerate(comms)
            if len(c) >= min_size
        ]

    @property
    def node_count(self) -> int:
        return self._g.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._g.number_of_edges()

    def insights(self, top_n: int = 10) -> dict[str, Any]:
        """Aggregated graph intelligence for the investigator workbench."""
        shared_devices = sorted(
            (
                {"device_id": d, "accounts": sorted(accs), "account_count": len(accs)}
                for d, accs in self._device_accounts.items()
                if len(accs) > 1
            ),
            key=lambda x: -x["account_count"],
        )[:top_n]
        shared_ips = sorted(
            (
                {"ip": ip, "accounts": sorted(accs), "account_count": len(accs)}
                for ip, accs in self._ip_accounts.items()
                if len(accs) > 1
            ),
            key=lambda x: -x["account_count"],
        )[:top_n]
        top_linked = sorted(
            ({"account_id": a, "beneficiaries": len(b)} for a, b in self._account_links.items()),
            key=lambda x: -x["beneficiaries"],
        )[:top_n]
        return {
            "nodes": self._g.number_of_nodes(),
            "edges": self._g.number_of_edges(),
            "known_fraud_accounts": sorted(self._known_fraud),
            "shared_devices": shared_devices,
            "shared_ips": shared_ips,
            "top_linked_accounts": top_linked,
        }

    def account_context(self, account_id: str) -> dict[str, Any]:
        """Everything the graph knows about one account (investigation pivot)."""
        node = f"acct:{account_id}"
        if node not in self._g:
            return {"account_id": account_id, "in_graph": False}
        devices = sorted({d for d, accs in self._device_accounts.items() if account_id in accs})
        ips = sorted({ip for ip, accs in self._ip_accounts.items() if account_id in accs})
        linked = sorted(self._account_links.get(account_id, set()))
        shared_via_device = sorted(
            {a for d in devices for a in self._device_accounts.get(d, set()) if a != account_id}
        )
        shared_via_ip = sorted(
            {a for ip in ips for a in self._ip_accounts.get(ip, set()) if a != account_id}
        )
        hops = None
        for f in self._known_fraud:
            if f not in self._g:
                continue
            try:
                p = nx.shortest_path_length(self._g.to_undirected(as_view=True), node, f)
                hops = p if hops is None else min(hops, p)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
        return {
            "account_id": account_id,
            "in_graph": True,
            "is_known_fraud": node in self._known_fraud,
            "devices": devices,
            "ips": ips,
            "linked_beneficiaries": linked,
            "accounts_sharing_device": shared_via_device,
            "accounts_sharing_ip": shared_via_ip,
            "hops_to_known_fraud": hops,
        }
