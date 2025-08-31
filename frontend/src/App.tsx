import { useState } from "react";
import Papa from "papaparse";
import { classifyTransactions, type Transaction } from "./lib/api";

type Classified = Transaction & { category: string; confidence?: number };

export default function App() {
  const [csvText, setCsvText] = useState("");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [results, setResults] = useState<Classified[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function parseCsv(text: string) {
    const parsed = Papa.parse(text, { header: true, skipEmptyLines: true });
    const items: Transaction[] = (parsed.data as any[]).map((r) => ({
      date: String(r.date ?? r.timestamp ?? "").trim(),
      description: String(r.description ?? r.memo ?? r.text ?? "").trim(),
      amount: Number(r.amount ?? r.value ?? r.price ?? 0),
    }))
    .filter((t) => t.description && !Number.isNaN(t.amount));
    setTransactions(items);
  }

  async function onClassify() {
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const out = await classifyTransactions(transactions);
      setResults(out);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: 24 }}>
      <h1>Expense Categorizer</h1>

      <section style={{ marginTop: 16 }}>
        <h3>1) Paste CSV (headers: date, description, amount)</h3>
        <textarea
          style={{ width: "100%", height: 160 }}
          placeholder={`date,description,amount
2025-06-01,ICA 45.67,-45.67
2025-06-05,DINNER 30.00,-30.00
2025-06-07,UBER RIDE 15.50,-15.50`}
          value={csvText}
          onChange={(e) => setCsvText(e.target.value)}
          onBlur={(e) => parseCsv(e.target.value)}
        />
        <div style={{ marginTop: 8 }}>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const reader = new FileReader();
              reader.onload = () => {
                const text = String(reader.result || "");
                setCsvText(text);
                parseCsv(text);
              };
              reader.readAsText(f);
            }}
          />
        </div>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>2) Preview</h3>
        {transactions.length === 0 ? (
          <em>No rows yet</em>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th align="left">date</th>
                <th align="left">description</th>
                <th align="right">amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((r, i) => (
                <tr key={i}>
                  <td>{r.date}</td>
                  <td>{r.description}</td>
                  <td align="right">{r.amount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <button disabled={loading || transactions.length === 0} onClick={onClassify}>
          {loading ? "Classifying…" : "3) Send to backend"}
        </button>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </section>

      {results && (
        <section style={{ marginTop: 24 }}>
          <h3>Results</h3>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th align="left">date</th>
                <th align="left">description</th>
                <th align="right">amount</th>
                <th align="left">category</th>
                <th align="right">confidence</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i}>
                  <td>{r.date}</td>
                  <td>{r.description}</td>
                  <td align="right">{r.amount}</td>
                  <td>{r.category}</td>
                  <td align="right">
                    {r.confidence != null ? r.confidence.toFixed(2) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <footer style={{ marginTop: 32, opacity: 0.7 }}>
        API base: {import.meta.env.VITE_API_BASE}
      </footer>
    </div>
  );
}
