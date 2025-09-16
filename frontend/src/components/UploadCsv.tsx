import { parseCsv, type ParseStats } from "../lib/csv"
import type { Transaction as Tx } from "../lib/csv";

type Props = {
  value: string;
  onValueChange: (v: string) => void;
  onParsed: (rows: Tx[], stats: ParseStats) => void;
};

export default function UploadCsv({ value, onValueChange, onParsed }: Props) {
  async function handleText(v: string) {
    onValueChange(v);
    const { rows, stats } = parseCsv(v);
    onParsed(rows, stats);
  }

  return (
    <>
      <textarea
        style={{ width: "100%", height: 160 }}
        placeholder={`date,description,amount
2025-06-01,ICA,-45.67
2025-06-05,DINNER,-30.00
2025-06-07,UBER RIDE,-15.50`}
        value={value}
        onChange={(e) => handleText(e.target.value)}
      />
      <div style={{ marginTop: 8 }}>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const text = await f.text();
            handleText(text);
          }}
        />
      </div>
    </>
  );
}
