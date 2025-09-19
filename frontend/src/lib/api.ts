export type Transaction = { date: string; description: string; amount: number };

export type Classified = Transaction & {
  category?: string | null;
  category_id?: number | null;
  confidence?: number | null;
};

// Rows returned by GET /expenses
export type ExpenseRow = {
  id: number;
  date: string;
  description: string;
  amount: number;
  category_id: number | null;
  category?: string | null;
  created_at?: string | null;
};

// --- Helpers ---
const base = import.meta.env.VITE_API_BASE as string;

// --- Classify (unchanged endpoint; shape now includes category_id) ---
export async function classifyTransactions(transactions: Transaction[]) {
  const res = await fetch(`${base}/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions, top_k: 1 }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const json = await res.json();
  return (json?.results ?? []) as Classified[];
}

// --- Persist expenses ---
export async function saveExpenses(expenses: Classified[]): Promise<number[]> {
  const res = await fetch(`${base}/expenses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expenses }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST /expenses failed (${res.status}): ${text || res.statusText}`);
  }
  const json = await res.json();
  return (json?.inserted_ids ?? []) as number[];
}

// --- List expenses ---
export async function fetchExpenses(
  limit = 50,
  offset = 0,
  opts?: { since?: string },
  signal?: AbortSignal
): Promise<ExpenseRow[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (opts?.since) params.set("since", opts.since);
  const res = await fetch(`${base}/expenses?${params}`, { method: "GET", signal });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`GET /expenses failed (${res.status}): ${text || res.statusText}`);
  }
  const json = await res.json();
  return (json?.results ?? []) as ExpenseRow[];
}
