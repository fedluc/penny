import { useState } from "react";
import Papa from "papaparse";
// Alias to avoid name collision with DOM's Transaction type
import { classifyTransactions, type Transaction as Tx, type Classified } from "./lib/api";

// robust amount parser (handles SEK, commas, currency symbols)
function normalizeAmount(v: any): number | null {
  if (typeof v === "number" && !Number.isNaN(v)) return v;
  let s = String(v ?? "").trim();
  if (!s) return null;
  s = s.replace(/(sek|kr|\$|€|£)/gi, "");
  s = s.replace(/[\s\u00A0\u202F]/g, "");
  const hasComma = s.includes(",");
  const hasDot = s.includes(".");
  if (hasComma && !hasDot) {
    s = s.replace(/\./g, "");
    s = s.replace(",", ".");
  } else {
    s = s.replace(/,/g, "");
  }
  const n = Number(s);
  return Number.isNaN(n) ? null : n;
}

export default function App() {
  const [csvText, setCsvText] = useState("");
  const [transactions, setTransactions] = useState<Tx[]>([]);
  const [results, setResults] = useState<Classified[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [parseInfo, setParseInfo] = useState<{ total: number; kept: number } | null>(null);

  function parseCsv(text: string) {
    const parsed = Papa.parse(text, {
      header: true,
      skipEmptyLines: true,
      transformHeader: (h) => h.toLowerCase().trim(),
    });

    const rows = (parsed.data as any[]).map((r) => {
      const date =
        r.date || r["transaction date"] || r["booking date"] || r.timestamp || r.datum;
      const description =
        r.description || r.memo || r.text || r.payee || r.merchant || r.narrative || r.beskrivning;
      const amountRaw =
        r.amount ?? r["amount (sek)"] ?? r.debit ?? r.credit ?? r.belopp ?? r["belopp (sek)"];
      const amount = normalizeAmount(amountRaw);
      return {
        date: date ? String(date).trim() : "",
        description: String(description || "").trim(),
        amount,
      };
    });

    const cleaned = rows.filter(
      (t) => t.description && typeof t.amount === "number" && !Number.isNaN(t.amount)
    ) as Tx[];

    setTransactions(cleaned);
    setParseInfo({ total: (parsed.data as any[]).length, kept: cleaned.length });
  }

  function onPasteAreaChange(v: string) {
    setCsvText(v);
    parseCsv(v);
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
      <h1> Penny </h1>

      <section style={{ marginTop: 16 }}>
        <h3>1) Paste CSV (headers: date, description, amount)</h3>
        <textarea
          style={{ width: "100%", height: 160 }}
          placeholder={`date,description,amount
2025-06-01,ICA 45.67,-45.67
2025-06-05,DINNER 30.00,-30.00
2025-06-07,UBER RIDE 15.50,-15.50`}
          value={csvText}
          onChange={(e) => onPasteAreaChange(e.target.value)}
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
        {parseInfo && (
          <div style={{ marginTop: 6, fontSize: 13, opacity: 0.8 }}>
            Parsed {parseInfo.kept}/{parseInfo.total} rows
            {parseInfo.kept === 0 && " — check column names/amount format"}
          </div>
        )}
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
                <tr key={`${r.date}-${r.description}-${r.amount}-${i}`}>
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
                <tr key={`${r.date}-${r.description}-${r.amount}-res-${i}`}>
                  <td>{r.date}</td>
                  <td>{r.description}</td>
                  <td align="right">{r.amount}</td>
                  <td>{r.category}</td>
                  <td align="right">{r.confidence != null ? r.confidence.toFixed(2) : "—"}</td>
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