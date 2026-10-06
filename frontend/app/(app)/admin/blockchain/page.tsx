"use client";

import { useMemo, useState } from "react";
import { RequireAdmin } from "@/components/require-admin";
import { Badge, Card, DataTable, ErrorNote, type Column } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { api } from "@/lib/api";
import type { MockBlockchainProof, MockVerifyResult } from "@/lib/types";

function ProofVerifyStatus({ verified }: { verified: boolean }) {
  return verified
    ? <Badge tone="gain">MOCK verified</Badge>
    : <Badge tone="loss">MOCK mismatch</Badge>;
}

function BlockchainContent() {
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifyResults, setVerifyResults] = useState<Record<string, MockVerifyResult>>({});

  const proofs = useApi<MockBlockchainProof[]>("/blockchain/proofs");

  const verify = async (proofId: string) => {
    setVerifying(proofId);
    try {
      const result = await api<MockVerifyResult>(`/blockchain/proofs/${proofId}/verify`);
      setVerifyResults((prev) => ({ ...prev, [proofId]: result }));
    } finally {
      setVerifying(null);
    }
  };

  const columns: Column<MockBlockchainProof>[] = [
    {
      key: "reference",
      header: "Reference / event ID",
      render: (row) => <span className="font-mono text-xs">{row.reference_id}</span>,
    },
    {
      key: "event_type",
      header: "Event type",
      render: (row) => <Badge tone="neutral">{row.event_type}</Badge>,
    },
    {
      key: "record_hash",
      header: "Record hash",
      render: (row) => (
        <span className="font-mono text-xs" title={row.record_hash}>
          {row.record_hash.slice(0, 12)}…{row.record_hash.slice(-4)}
        </span>
      ),
    },
    {
      key: "transaction_hash",
      header: "Tx hash",
      render: (row) => (
        <span className="font-mono text-xs" title={row.transaction_hash}>
          {row.transaction_hash.slice(0, 12)}…{row.transaction_hash.slice(-4)}
        </span>
      ),
    },
    {
      key: "block",
      header: "Block #",
      render: (row) => <span className="num text-xs">{row.block_number}</span>,
    },
    {
      key: "network",
      header: "Network",
      render: (row) => <span className="text-xs text-mute">{row.network}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (row) => {
        const tone =
          row.blockchain_status === "anchored" ? "gain"
            : row.blockchain_status === "verification_failed" ? "loss"
            : "neutral";
        return <Badge tone={tone}>{row.blockchain_status}</Badge>;
      },
    },
    {
      key: "verify",
      header: "Verification",
      align: "right",
      render: (row) => {
        const existing = verifyResults[row.proof_id];
        const result = (
          <>
            {existing ? <ProofVerifyStatus verified={existing.verified} /> : null}
            {existing && (
              <span className="text-[11px] text-mute ml-2">
                mock recomputed {existing.recomputed_record_hash.slice(0, 8)}…
              </span>
            )}
          </>
        );
        return (
          <div className="flex items-center justify-end gap-2">
            {result}
            <button
              type="button"
              className="btn-ghost btn-xs"
              disabled={verifying === row.proof_id}
              onClick={() => verify(row.proof_id)}
            >
              {verifying === row.proof_id ? "Verifying…" : "Verify"}
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <Card
      title="Blockchain Audit Integrity"
      subtitle="MOCK proof layer for demonstration"
      action={
        <Badge tone="neutral">MOCK</Badge>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-mute">
          This page shows the MOCK blockchain proof metadata for critical TradeShield
          events. It is NOT a real blockchain, does NOT contain real transactions, and
          does NOT replace PostgreSQL, which remains the system of record.
        </p>

        <div className="rounded-xl border border-edge/70 bg-ink-800/40 p-4">
          <p className="text-sm font-semibold">Mock proof layer</p>
          <p className="mt-1 text-sm text-mute">
            Record hashes, transaction hashes, and block numbers are deterministic-looking
            demo values. Verification re-computes the stored record hash from the proof
            metadata and compares it to the stored value.
          </p>
        </div>

        {proofs.error ? (
          <ErrorNote message={proofs.error.message} onRetry={proofs.reload} />
        ) : proofs.loading ? (
          <div className="text-sm text-mute">Loading proofs…</div>
        ) : proofs.data && proofs.data.length > 0 ? (
          <DataTable
            columns={columns}
            rows={proofs.data}
            loading={proofs.loading}
            rowKey={(row) => row.proof_id}
            emptyTitle="No proof records yet"
            emptyHint="Run a trade or trigger a blocked order, then refresh."
          />
        ) : (
          <div className="text-sm text-mute">No proof records found.</div>
        )}
      </div>
    </Card>
  );
}

export default function BlockchainPage() {
  return (
    <RequireAdmin>
      <BlockchainContent />
    </RequireAdmin>
  );
}
