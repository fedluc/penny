import { useState } from "react";
import UploadCsv from "../components/UploadCsv";
import PreviewTable from "../components/PreviewTable";
import ResultsTable from "../components/ResultsTable";
import type { Transaction as Tx } from "../lib/csv";
import { classifyTransactions, saveExpenses, type Classified } from "../lib/api";
import BrandLink from "../components/BrandLink";
import "./AddExpenses.css";

export default function AddExpenses() {
  const [csvText, setCsvText] = useState("");
  const [transactions, setTransactions] = useState<Tx[]>([]);
  const [results, setResults] = useState<Classified[] | null>(null);

  const [loadingClassify, setLoadingClassify] = useState(false);
  const [loadingSave, setLoadingSave] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [savedCount, setSavedCount] = useState<number | null>(null);
  const [parseInfo, setParseInfo] = useState<{ total: number; kept: number } | null>(null);

  async function onClassify() {
    setLoadingClassify(true);
    setLoadingSave(false);
    setError(null);
    setSavedCount(null);
    setResults(null);
    try {
      const out = await classifyTransactions(transactions);
      setResults(out);
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setLoadingClassify(false);
    }
  }

  async function onSave() {
    if (!results || results.length === 0) return;
    setLoadingSave(true);
    setError(null);
    setSavedCount(null);
    try {
      const ids = await saveExpenses(results);
      setSavedCount(ids.length);
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setLoadingSave(false);
    }
  }

  return (
    <>
      <BrandLink />
      <main className="page add">
        <div className="container">
          <h1 className="section-title" style={{ fontSize: 24 }}>Add Expenses</h1>

          <section className="section">
            <h3 className="section-title">1) Paste CSV (headers: date, description, amount)</h3>
            <div className="card">
              <UploadCsv
                value={csvText}
                onValueChange={setCsvText}
                onParsed={(rows, stats) => {
                  setTransactions(rows);
                  setParseInfo(stats);
                  // Reset downstream state when new CSV is parsed
                  setResults(null);
                  setSavedCount(null);
                  setError(null);
                }}
              />
              {parseInfo && (
                <div className="muted" style={{ marginTop: 8 }}>
                  Parsed {parseInfo.kept}/{parseInfo.total} rows
                  {parseInfo.kept === 0 && " — check column names/amount format"}
                </div>
              )}
            </div>
          </section>

          <section className="section">
            <h3 className="section-title">2) Preview</h3>
            <div className="card">
              <PreviewTable rows={transactions} />
            </div>
          </section>

          <section className="section row wrap" style={{ gap: 12 }}>
            <button
              className="btn btn-primary"
              disabled={loadingClassify || transactions.length === 0}
              onClick={onClassify}
              title="Run classification without saving"
            >
              {loadingClassify ? "Classifying…" : "3) Classify"}
            </button>
            {error && <p className="add-error">{error}</p>}
          </section>

          {results && (
            <>
              <section className="section">
                <h3 className="section-title">Results</h3>
                <div className="card">
                  <ResultsTable rows={results} />
                </div>
              </section>

              <section className="section row wrap" style={{ gap: 12 }}>
                <button
                  className="btn btn-primary"
                  disabled={loadingSave || results.length === 0}
                  onClick={onSave}
                  title={results.length > 0 ? "Save classified expenses" : "Classify first"}
                >
                  {loadingSave ? "Saving…" : "4) Save to backend"}
                </button>
                {savedCount !== null && !error && (
                  <p className="muted" style={{ marginTop: 8 }}>
                    Saved {savedCount} expense{savedCount === 1 ? "" : "s"} ✓
                  </p>
                )}
                {error && <p className="add-error">{error}</p>}
              </section>
            </>
          )}

          <footer className="muted" style={{ marginTop: 24 }}>
            API base: {import.meta.env.VITE_API_BASE}
          </footer>
        </div>
      </main>
    </>
  );
}
