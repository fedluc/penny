import { Link } from "react-router-dom";
import pennyUrl from "../assets/penny.svg";
import "./Home.css";

export default function Home() {
  return (
    <main className="center-screen home">
      <div className="card home-card">
        <img src={pennyUrl} alt="Logo" className="home-logo" />
        <div className="home-buttons">
          <Link to="/visualize" className="btn btn-outline">Visualize</Link>
          <Link to="/add" className="btn btn-solid">Add expenses</Link>
        </div>
      </div>
    </main>
  );
}
