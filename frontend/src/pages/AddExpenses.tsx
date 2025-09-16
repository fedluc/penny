import { useState } from "react";
import UploadCsv from "../components/UploadCsv";
import PreviewTable from "../components/PreviewTable";
import ResultsTable from "../components/ResultsTable";
import type { Transaction as Tx } from "../lib/csv";
import { classifyTransactions, type Classified } from "../lib/api";
import "./AddExpenses.css";

export default function AddExpenses() {
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
    <main className="page add">
      <div className="container">
        <h1 className="header">Add Expenses</h1>

        <section className="section">
          <h3 className="section-title">1) Paste CSV (headers: date, description, amount)</h3>
          <UploadCsv
            value={csvText}
            onValueChange={setCsvText}
            onParsed={(rows, stats) => {
              setTransactions(rows);
              setParseInfo(stats);
            }}
          />
          {parseInfo && (
            <div className="parsed muted">
              Parsed {parseInfo.kept}/{parseInfo.total} rows
              {parseInfo.kept === 0 && " — check column names/amount format"}
            </div>
          )}
        </section>

        <section className="section">
          <h3 className="section-title">2) Preview</h3>
          <div className="card">
            <PreviewTable rows={transactions} />
          </div>
        </section>

        <section className="section">
          <button
            className="btn btn-solid"
            disabled={loading || transactions.length === 0}
            onClick={onClassify}
          >
            {loading ? "Classifying…" : "3) Send to backend"}
          </button>
          {error && <p className="error">{error}</p>}
        </section>

        {results && (
          <section className="section">
            <h3 className="section-title">Results</h3>
            <div className="card">
              <ResultsTable rows={results} />
            </div>
          </section>
        )}

        <footer>API base: {import.meta.env.VITE_API_BASE}</footer>
      </div>
    </main>
  );
}
