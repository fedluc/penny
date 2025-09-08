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