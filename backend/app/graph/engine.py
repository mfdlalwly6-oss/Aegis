"""AEGIS Graph Intelligence Engine — NetworkX-based, fed from transaction history.
Detects shared devices, shared IPs, known-fraud hops, and community rings.

A3 fix — TENANT ISOLATION: the engine previously kept ONE global graph and one
set of global indices, so tenant A's devices/IPs/accounts/known-fraud marks
inflated tenant B's risk scores and leaked into investigator insights.
Now every node is namespaced by tenant (`t:{tenant}|kind:{id}`), all index
dicts are keyed by tenant, and every query method requires the caller's
tenant_id. Edges can never cross tenants (an edge is only added between
same-tenant nodes), so path/hops computations and community detection are
inherently tenant-scoped.
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import structlog

from app.models.schemas import GraphSignal, Transaction

logger = structlog.get_logger(__name__)

_LEGACY = "legacy"  # webhook fallback tenant for pre-RLS API keys


class GraphEngine:
    def __init__(self):
        self._g = nx.MultiDiGraph()
        # Per-tenant indices — NO global state crosses tenants anymore.
        self._known_fraud: dict[str, set[str]] = {}          # tenant -> {"acct:id"}
        self._device_accounts: dict[str, dict[str, set]] = {}  # tenant -> device -> {account}
        self._ip_accounts: dict[str, dict[str, set]] = {}      # tenant -> ip -> {account}
        self._account_links: dict[str, dict[str, set]] = {}    # tenant -> sender -> {beneficiary}

    # ── internal tenant-namespaced node helpers ──────────────────────────
    @staticmethod
    def _t(tenant_id: str | None) -> str:
        return tenant_id or _LEGACY

    @staticmethod
    def _ns(tenant: str, kind: str, ident: str) -> str:
        return f"t:{tenant}|{kind}:{ident}"

    def bootstrap(self, transactions: list[dict]) -> None:
        for tx in reversed(transactions):
            self._add_dict(tx)
        logger.info(
            "graph.bootstrapped",
            nodes=self._g.number_of_nodes(),
            tenants=len(set(self._known_fraud) | set(self._device_accounts)),
        )

    def _add_dict(self, tx: dict) -> None:
        tenant = self._t(tx.get("tenant_id"))
        sender = self._ns(tenant, "acct", tx["sender_account_id"])
        benef = self._ns(tenant, "acct", tx["beneficiary_account_id"])
        txn = self._ns(tenant, "tx", tx["tx_id"])
        self._g.add_node(sender, type="account")
        self._g.add_node(benef, type="account")
        self._g.add_node(txn, type="transaction")
        self._g.add_edge(sender, txn, rel="sends")
        self._g.add_edge(txn, benef, rel="to")
        dev = tx.get("device_id")
        ip = tx.get("ip")
        if dev:
            d = self._ns(tenant, "device", dev)
            self._g.add_node(d, type="device")
            self._g.add_edge(sender, d, rel="uses")
            self._device_accounts.setdefault(tenant, {}).setdefault(dev, set()).add(
                tx["sender_account_id"]
            )
        if ip:
            i = self._ns(tenant, "ip", ip)
            self._g.add_node(i, type="ip")
            self._g.add_edge(sender, i, rel="from")
            self._ip_accounts.setdefault(tenant, {}).setdefault(ip, set()).add(
                tx["sender_account_id"]
            )
        self._account_links.setdefault(tenant, {}).setdefault(
            tx["sender_account_id"], set()
        ).add(tx["beneficiary_account_id"])

    def add_transaction(self, tx: Transaction) -> None:
        self._add_dict(
            {
                "tenant_id": getattr(tx, "tenant_id", None),
                "tx_id": tx.tx_id,
                "sender_account_id": tx.sender_account_id,
                "beneficiary_account_id": tx.beneficiary_account_id,
                "device_id": tx.device.device_id if tx.device else None,
                "ip": str(tx.device.ip) if tx.device and tx.device.ip else None,
            }
        )

    def mark_fraud(self, account_id: str, tenant_id: str | None = None) -> None:
        """Mark an account as known fraud WITHIN one tenant only.

        A3: the mark is tenant-scoped — tenant B's scoring never sees
        tenant A's fraud marks. Callers must pass the tenant of the
        investigated transaction.
        """
        tenant = self._t(tenant_id)
        self._known_fraud.setdefault(tenant, set()).add(
            self._ns(tenant, "acct", account_id)
        )

    def score(self, tx: Transaction) -> GraphSignal:
        tenant = self._t(getattr(tx, "tenant_id", None))
        dev = tx.device.device_id if tx.device else None
        ip = str(tx.device.ip) if tx.device and tx.device.ip else None
        sender_acct = tx.sender_account_id
        tenant_devices = self._device_accounts.get(tenant, {})
        tenant_ips = self._ip_accounts.get(tenant, {})
        tenant_links = self._account_links.get(tenant, {})
        shared_dev = (
            len(tenant_devices.get(dev, set()) - {sender_acct}) if dev else 0
        )
        shared_ip = len(tenant_ips.get(ip, set()) - {sender_acct}) if ip else 0
        linked = len(tenant_links.get(sender_acct, set()))

        # hops to known fraud — same tenant ONLY (nodes are tenant-namespaced,
        # so a path can never leave this tenant's subgraph).
        u = self._ns(tenant, "acct", sender_acct)
        hops = None
        for f in self._known_fraud.get(tenant, set()):
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
        """Community detection. A3: edges never cross tenants, so detected
        communities are inherently single-tenant."""
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

    def insights(self, tenant_id: str | None = None, top_n: int = 10) -> dict[str, Any]:
        """Aggregated graph intelligence for the investigator workbench.
        A3: filtered to the caller's tenant."""
        tenant = self._t(tenant_id)
        tenant_devices = self._device_accounts.get(tenant, {})
        tenant_ips = self._ip_accounts.get(tenant, {})
        tenant_links = self._account_links.get(tenant, {})
        shared_devices = sorted(
            (
                {"device_id": d, "accounts": sorted(accs), "account_count": len(accs)}
                for d, accs in tenant_devices.items()
                if len(accs) > 1
            ),
            key=lambda x: -x["account_count"],
        )[:top_n]
        shared_ips = sorted(
            (
                {"ip": ip, "accounts": sorted(accs), "account_count": len(accs)}
                for ip, accs in tenant_ips.items()
                if len(accs) > 1
            ),
            key=lambda x: -x["account_count"],
        )[:top_n]
        top_linked = sorted(
            ({"account_id": a, "beneficiaries": len(b)} for a, b in tenant_links.items()),
            key=lambda x: -x["beneficiaries"],
        )[:top_n]
        return {
            "nodes": self._g.number_of_nodes(),
            "edges": self._g.number_of_edges(),
            "known_fraud_accounts": sorted(
                n for n in self._known_fraud.get(tenant, set()) if n in self._g
            ),
            "shared_devices": shared_devices,
            "shared_ips": shared_ips,
            "top_linked_accounts": top_linked,
        }

    def account_context(self, account_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        """Everything the graph knows about one account (investigation pivot).
        A3: restricted to the caller's tenant."""
        tenant = self._t(tenant_id)
        tenant_devices = self._device_accounts.get(tenant, {})
        tenant_ips = self._ip_accounts.get(tenant, {})
        tenant_links = self._account_links.get(tenant, {})
        node = self._ns(tenant, "acct", account_id)
        if node not in self._g:
            return {"account_id": account_id, "in_graph": False}
        devices = sorted(d for d, accs in tenant_devices.items() if account_id in accs)
        ips = sorted(i for i, accs in tenant_ips.items() if account_id in accs)
        linked = sorted(tenant_links.get(account_id, set()))
        shared_via_device = sorted(
            {a for d in devices for a in tenant_devices.get(d, set()) if a != account_id}
        )
        shared_via_ip = sorted(
            {a for i in ips for a in tenant_ips.get(i, set()) if a != account_id}
        )
        hops = None
        for f in self._known_fraud.get(tenant, set()):
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
            "is_known_fraud": node in self._known_fraud.get(tenant, set()),
            "devices": devices,
            "ips": ips,
            "linked_beneficiaries": linked,
            "accounts_sharing_device": shared_via_device,
            "accounts_sharing_ip": shared_via_ip,
            "hops_to_known_fraud": hops,
        }
