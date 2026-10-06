"use client";

import { useMemo, useState, type FormEvent } from "react";
import { RequireAdmin } from "@/components/require-admin";
import { useToast } from "@/components/toast";
import { Badge, Card, DataTable, ErrorNote, Field, Modal, type Column, type Tone } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime } from "@/lib/format";
import type { Indicator, Paged } from "@/lib/types";

const CATEGORIES = ["malware", "phishing", "c2", "botnet", "fraud", "spam", "recon", "other"];
const TYPES = ["ip", "domain", "url", "file_hash"] as const;

const EMPTY_FORM = {
  indicator_type: "ip" as (typeof TYPES)[number],
  value: "",
  threat_category: "c2",
  confidence: 85,
  source_name: "",
  expires_at: "",
  notes: "",
};

function confidenceTone(confidence: number): Tone {
  if (confidence >= 80) return "critical";
  if (confidence >= 60) return "warn";
  return "neutral";
}

function screeningState(row: Indicator): { label: string; tone: Tone } {
  if (!row.is_active) return { label: "Disabled", tone: "neutral" };
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now())
    return { label: "Expired", tone: "warn" };
  return { label: "Screening", tone: "gain" };
}

function ThreatsContent() {
  const { push } = useToast();
  const [kind, setKind] = useState("");
  const [active, setActive] = useState("");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Indicator | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editForm, setEditForm] = useState({
    threat_category: "c2",
    confidence: 85,
    is_active: true,
    expires_at: "",
    notes: "",
  });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiError | null>(null);

  const path = useMemo(() => {
    const params = new URLSearchParams({ limit: "200" });
    if (kind) params.set("type", kind);
    if (active) params.set("active", active);
    if (search.trim()) params.set("q", search.trim());
    return `/security/indicators?${params.toString()}`;
  }, [kind, active, search]);

  const indicators = useApi<Paged<Indicator>>(path);

  function openCreate() {
    setForm(EMPTY_FORM);
    setFailure(null);
    setCreating(true);
  }

  function openEdit(row: Indicator) {
    setFailure(null);
    setEditForm({
      threat_category: row.threat_category,
      confidence: row.confidence,
      is_active: row.is_active,
      expires_at: row.expires_at ? row.expires_at.slice(0, 16) : "",
      notes: row.notes ?? "",
    });
    setEditing(row);
  }

  async function createIndicator(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      const body: Record<string, unknown> = {
        indicator_type: form.indicator_type,
        value: form.value.trim(),
        threat_category: form.threat_category,
        confidence: Number(form.confidence),
      };
      if (form.source_name.trim()) body.source_name = form.source_name.trim();
      if (form.notes.trim()) body.notes = form.notes.trim();
      if (form.expires_at) body.expires_at = new Date(form.expires_at).toISOString();
      await api<Indicator>("/security/indicators", { method: "POST", body });
      push("success", "Threat indicator created.");
      setCreating(false);
      indicators.reload();
    } catch (error) {
      const apiError = error instanceof ApiError ? error : new ApiError(0, "UNKNOWN", "Create failed.");
      setFailure(apiError);
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setBusy(true);
    setFailure(null);
    try {
      const body: Record<string, unknown> = {
        threat_category: editForm.threat_category,
        confidence: Number(editForm.confidence),
        is_active: editForm.is_active,
        notes: editForm.notes.trim() || null,
        expires_at: editForm.expires_at ? new Date(editForm.expires_at).toISOString() : null,
      };
      await api<Indicator>(`/security/indicators/${editing.indicator_id}`, {
        method: "PATCH",
        body,
      });
      push("success", `Indicator ${editForm.is_active ? "updated" : "disabled"}.`);
      setEditing(null);
      indicators.reload();
    } catch (error) {
      const apiError = error instanceof ApiError ? error : new ApiError(0, "UNKNOWN", "Update failed.");
      setFailure(apiError);
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(row: Indicator) {
    try {
      await api<Indicator>(`/security/indicators/${row.indicator_id}`, {
        method: "PATCH",
        body: { is_active: !row.is_active },
      });
      push("success", row.is_active ? "Indicator disabled." : "Indicator re-enabled.");
      indicators.reload();
    } catch (error) {
      push("error", error instanceof ApiError ? error.message : "Update failed.");
    }
  }

  const columns: Column<Indicator>[] = [
    {
      key: "type",
      header: "Type",
      render: (row) => <Badge tone="brand">{row.indicator_type}</Badge>,
    },
    {
      key: "value",
      header: "Value",
      render: (row) => (
        <span className="num text-xs" title={row.value}>
          {row.value.length > 34 ? `${row.value.slice(0, 34)}...` : row.value}
        </span>
      ),
    },
    {
      key: "category",
      header: "Category",
      render: (row) => <span className="text-xs text-mute">{row.threat_category}</span>,
    },
    {
      key: "confidence",
      header: "Confidence",
      render: (row) => (
        <div className="flex items-center gap-2">
          <Badge tone={confidenceTone(row.confidence)}>{row.confidence}</Badge>
          <div className="h-1.5 w-16 rounded-full bg-ink-800">
            <div
              className="h-1.5 rounded-full"
              style={{
                width: `${row.confidence}%`,
                background:
                  row.confidence >= 80 ? "#ff5d6c" : row.confidence >= 60 ? "#ffb020" : "#3b4667",
              }}
            />
          </div>
        </div>
      ),
    },
    {
      key: "source",
      header: "Source",
      render: (row) => (
        <div>
          <p className="text-xs">{row.source_name}</p>
          <p className="text-[11px] text-mute">reliability {row.reliability}/5</p>
        </div>
      ),
    },
    {
      key: "state",
      header: "State",
      render: (row) => {
        const state = screeningState(row);
        return (
          <Badge tone={state.tone}>
            {state.label}
            {state.label === "Screening" ? "" : ""}
          </Badge>
        );
      },
    },
    {
      key: "last_seen",
      header: "Last seen",
      render: (row) => <span className="num text-xs text-mute">{dateTime(row.last_seen)}</span>,
    },
    {
      key: "actions",
      header: "Manage",
      align: "right",
      render: (row) => (
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost btn-xs" onClick={() => openEdit(row)}>
            Edit
          </button>
          <button type="button" className="btn-ghost btn-xs" onClick={() => toggleActive(row)}>
            {row.is_active ? "Disable" : "Enable"}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <Card
        title="Threat indicators"
        subtitle="Confidence ? 80 blocks an order * 60-79 flags it * < 60 is allowed"
        action={
          <button type="button" className="btn-primary btn-xs" onClick={openCreate}>
            Add indicator
          </button>
        }
      >
        <div className="flex flex-col gap-3 border-b border-edge/70 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            <div className="w-40">
              <select
                className="input"
                value={kind}
                onChange={(event) => setKind(event.target.value)}
                aria-label="Indicator type"
              >
                <option value="">All types</option>
                {TYPES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
            <div className="w-40">
              <select
                className="input"
                value={active}
                onChange={(event) => setActive(event.target.value)}
                aria-label="Indicator state"
              >
                <option value="">Any state</option>
                <option value="true">Active only</option>
                <option value="false">Disabled only</option>
              </select>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-full sm:w-72">
              <input
                className="input"
                placeholder="Search value, category or source..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <Badge tone="neutral">{indicators.data?.total ?? 0} indicators</Badge>
          </div>
        </div>

        {indicators.error ? (
          <div className="p-5">
            <ErrorNote message={indicators.error.message} onRetry={indicators.reload} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={indicators.data?.items ?? null}
            loading={indicators.loading}
            rowKey={(row) => row.indicator_id}
            emptyTitle="No indicators match"
            emptyHint="Adjust the filters or add a new indicator."
          />
        )}
      </Card>

      <Modal
        open={creating}
        title="Add threat indicator"
        subtitle="Values are normalised by type (lower-cased domains, URLs and hashes)"
        onClose={() => setCreating(false)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button
              type="submit"
              form="create-indicator"
              className="btn-primary"
              disabled={busy || !form.value.trim()}
            >
              {busy ? "Saving..." : "Create indicator"}
            </button>
          </>
        }
      >
        <form id="create-indicator" className="space-y-4" onSubmit={createIndicator}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Type">
              <select
                className="input"
                value={form.indicator_type}
                onChange={(event) =>
                  setForm({ ...form, indicator_type: event.target.value as (typeof TYPES)[number] })
                }
              >
                {TYPES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Category">
              <select
                className="input"
                value={form.threat_category}
                onChange={(event) => setForm({ ...form, threat_category: event.target.value })}
              >
                {CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field label="Value" hint="IP address, domain, URL or 64-character SHA-256 digest">
            <input
              className="input num"
              required
              value={form.value}
              onChange={(event) => setForm({ ...form, value: event.target.value })}
              placeholder="198.51.100.66"
            />
          </Field>

          <Field label={`Confidence -- ${form.confidence}`} hint="80+ blocks orders, 60-79 flags them">
            <input
              type="range"
              min={0}
              max={100}
              className="w-full accent-[#4f7cff]"
              value={form.confidence}
              onChange={(event) => setForm({ ...form, confidence: Number(event.target.value) })}
            />
          </Field>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Threat source" hint="Leave blank to use 'Manual Entry'">
              <input
                className="input"
                value={form.source_name}
                onChange={(event) => setForm({ ...form, source_name: event.target.value })}
                placeholder="Campus SOC Feed"
              />
            </Field>
            <Field label="Expires at" hint="Optional -- expired indicators stop screening">
              <input
                type="datetime-local"
                className="input"
                value={form.expires_at}
                onChange={(event) => setForm({ ...form, expires_at: event.target.value })}
              />
            </Field>
          </div>

          <Field label="Notes">
            <input
              className="input"
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
              placeholder="Context for the analysts"
            />
          </Field>

          {failure && <ErrorNote message={failure.message} />}
        </form>
      </Modal>

      <Modal
        open={editing !== null}
        title={editing ? `Edit ${editing.indicator_type}` : ""}
        subtitle={editing ? editing.value : ""}
        onClose={() => setEditing(null)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button
              type="submit"
              form="edit-indicator"
              className="btn-primary"
              disabled={busy}
            >
              {busy ? "Saving..." : "Save changes"}
            </button>
          </>
        }
      >
        <form id="edit-indicator" className="space-y-4" onSubmit={saveEdit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Category">
              <select
                className="input"
                value={editForm.threat_category}
                onChange={(event) => setEditForm({ ...editForm, threat_category: event.target.value })}
              >
                {CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Expires at">
              <input
                type="datetime-local"
                className="input"
                value={editForm.expires_at}
                onChange={(event) => setEditForm({ ...editForm, expires_at: event.target.value })}
              />
            </Field>
          </div>

          <Field label={`Confidence -- ${editForm.confidence}`}>
            <input
              type="range"
              min={0}
              max={100}
              className="w-full accent-[#4f7cff]"
              value={editForm.confidence}
              onChange={(event) => setEditForm({ ...editForm, confidence: Number(event.target.value) })}
            />
          </Field>

          <Field label="Active" hint="Disabled indicators are ignored by the screening trigger">
            <select
              className="input"
              value={editForm.is_active ? "true" : "false"}
              onChange={(event) => setEditForm({ ...editForm, is_active: event.target.value === "true" })}
            >
              <option value="true">Active -- screened</option>
              <option value="false">Disabled -- ignored</option>
            </select>
          </Field>

          <Field label="Notes">
            <input
              className="input"
              value={editForm.notes}
              onChange={(event) => setEditForm({ ...editForm, notes: event.target.value })}
            />
          </Field>

          {failure && <ErrorNote message={failure.message} />}
        </form>
      </Modal>
    </div>
  );
}

export default function ThreatIndicatorsPage() {
  return (
    <RequireAdmin>
      <ThreatsContent />
    </RequireAdmin>
  );
}
