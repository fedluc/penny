import { Link } from "react-router-dom";
import pennyUrl from "../assets/penny.svg";
import "./Home.css";

export default function Home() {
  return (
    <main className="home center-screen">
      <div className="card home-card">
        <img src={pennyUrl} alt="Logo" className="home-logo" />
        <div className="home-buttons">
          <Link to="/add" className="btn btn-primary">Add expenses</Link>
          <Link to="/visualize" className="btn btn-outline">Visualize</Link>
        </div>
      </div>
    </main>
  );
}
