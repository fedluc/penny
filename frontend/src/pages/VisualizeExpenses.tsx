import { useEffect, useMemo, useRef, useState } from "react";
import BrandLink from "../components/BrandLink";
import { fetchExpenses, type ExpenseRow } from "../lib/api";
import "./VisualizeExpenses.css";

const PAGE_SIZE = 50;

export default function VisualizeExpenses() {
  const [rows, setRows] = useState<ExpenseRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const abortRef = useRef<AbortController | null>(null);

  async function loadPage(nextOffset: number) {
    setLoading(true);
    setError(null);
    try {
      // Abort any in-flight request
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      const chunk = await fetchExpenses(
        PAGE_SIZE,
        nextOffset,
        undefined,
        abortRef.current.signal
      );
      setRows((prev) => (nextOffset === 0 ? chunk : [...prev, ...chunk]));
      setHasMore(chunk.length === PAGE_SIZE);
      setOffset(nextOffset + chunk.length);
    } catch (e: any) {
      if (e?.name === "AbortError") return;
      setError(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  // initial load
  useEffect(() => {
    loadPage(0);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatted = useMemo(
    () =>
      rows.map((r) => ({
        date: r.date ?? "",
        description: r.description ?? "",
        amount: typeof r.amount === "number" ? r.amount : 0,
        category: r.category ?? "",
        created_at: r.created_at ?? "",
      })),
    [rows]
  );

  return (
    <>
      <BrandLink />
      <main className="page visualize">
        <div className="container">
          <h1 className="section-title" style={{ fontSize: 24 }}>Expenses</h1>
          <p className="muted">
            Fetched from <code>/expenses</code> ({rows.length}{hasMore ? "+" : ""} rows)
          </p>

          <section className="section">
            <div className="card" style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>Date</th>
                    <th>Description</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>Amount</th>
                    <th style={{ whiteSpace: "nowrap" }}>Category</th>
                    <th style={{ whiteSpace: "nowrap" }}>Created&nbsp;At</th>
                  </tr>
                </thead>
                <tbody>
                  {formatted.length === 0 && !loading && !error && (
                    <tr><td colSpan={5} className="muted">No data</td></tr>
                  )}
                  {formatted.map((r, i) => (
                    <tr key={`${r.date}-${r.description}-${r.amount}-${i}`}>
                      <td>{r.date}</td>
                      <td>{r.description}</td>
                      <td style={{ textAlign: "right" }}>
                        {typeof r.amount === "number" ? r.amount.toFixed(2) : ""}
                      </td>
                      <td>{r.category}</td>
                      <td>{r.created_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="section row wrap">
            <button
              className="btn btn-outline"
              onClick={() => loadPage(0)}
              disabled={loading}
              title="Reload from start"
            >
              Refresh
            </button>
            <button
              className="btn btn-primary"
              onClick={() => loadPage(offset)}
              disabled={loading || !hasMore}
              title="Fetch next page"
            >
              {loading ? "Loading…" : hasMore ? "Load more" : "No more results"}
            </button>
            {error && <p className="muted" style={{ color: "salmon" }}>{error}</p>}
          </section>
        </div>
      </main>
    </>
  );
}
