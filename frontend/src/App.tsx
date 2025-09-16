import { useState } from "react";
import UploadCsv from "./components/UploadCsv";
import PreviewTable from "./components/PreviewTable";
import ResultsTable from "./components/ResultsTable";
import type { Transaction as Tx } from "./lib/csv";
import { classifyTransactions, type Classified } from "./lib/api";

export default function App() {
  const [csvText, setCsvText] = useState("");
  const [transactions, setTransactions] = useState<Tx[]>([]);
  const [results, setResults] = useState<Classified[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [parseInfo, setParseInfo] = useState<{ total: number; kept: number } | null>(null);

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
      <h1>Penny</h1>

      <section style={{ marginTop: 16 }}>
        <h3>1) Paste CSV (headers: date, description, amount)</h3>
        <UploadCsv
          value={csvText}
          onValueChange={setCsvText}
          onParsed={(rows, stats) => {
            setTransactions(rows);
            setParseInfo(stats);
          }}
        />
        {parseInfo && (
          <div style={{ marginTop: 6, fontSize: 13, opacity: 0.8 }}>
            Parsed {parseInfo.kept}/{parseInfo.total} rows
            {parseInfo.kept === 0 && " — check column names/amount format"}
          </div>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>2) Preview</h3>
        <PreviewTable rows={transactions} />
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
          <ResultsTable rows={results} />
        </section>
      )}

      <footer style={{ marginTop: 32, opacity: 0.7 }}>
        API base: {import.meta.env.VITE_API_BASE}
      </footer>
    </div>
  );
}
