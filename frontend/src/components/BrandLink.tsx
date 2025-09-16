import { Link } from "react-router-dom";
import pennyUrl from "../assets/penny.svg";

export default function BrandLink() {
  return (
    <Link to="/" className="brand-link" aria-label="Go to home">
      <img src={pennyUrl} alt="" aria-hidden="true" />
    </Link>
  );
}
