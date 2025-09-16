export type Transaction = { date: string; description: string; amount: number };

export type Classified = Transaction & {
  category: string;
  confidence?: number;
};

export async function classifyTransactions(transactions: Transaction[]) {
  const base = import.meta.env.VITE_API_BASE as string;
  const res = await fetch(`${base}/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions, top_k: 1 }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return (await res.json()).results as Classified[];
}

export type ServerClassified = {
  date: string | null;
  description: string | null;
  amount: number | null;
  category: string | null;
  category_id: number | null;
  confidence: number | null;
  hash?: string | null;
  created_at?: string | null;
};

export async function fetchTransactions(limit = 50, offset = 0): Promise<ServerClassified[]> {
  const base = import.meta.env.VITE_API_BASE as string;
  const url = `${base}/transactions?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`;
  const res = await fetch(url, { method: "GET" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`GET /transactions failed (${res.status}): ${text || res.statusText}`);
  }
  const json = await res.json();
  const results = Array.isArray(json?.results) ? json.results : [];
  return results as ServerClassified[];
}