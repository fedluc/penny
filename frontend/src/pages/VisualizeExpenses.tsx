import BrandLink from "../components/BrandLink";
import "./VisualizeExpenses.css";

export default function VisualizeExpenses() {
  return (
    <>
      <BrandLink />
      <main className="page visualize">
        <div className="container">
          <h1 className="section-title" style={{ fontSize: 24 }}>Visualize Expenses</h1>
          <p className="muted">Charts and summaries will appear here.</p>
          <div className="section">
            <div className="card">Chart area</div>
          </div>
        </div>
      </main>
    </>
  );
}
