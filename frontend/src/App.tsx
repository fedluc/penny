// src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/Home";
import VisualizeExpenses from "./pages/VisualizeExpenses";
import AddExpenses from "./pages/AddExpenses";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/visualize" element={<VisualizeExpenses />} />
        <Route path="/add" element={<AddExpenses />} />
        {/* fallback: redirect unknown routes */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
