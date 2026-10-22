import { useState } from "react";
import Scene from "./Scene";
import layout from "./staffroom-layout.json";

function useBoardStats() {
  const [s] = useState({ students: "—", atRisk: "—", avg: "—" });
  // TODO: fetch("http://localhost:8000/analytics") and map the fields you get back.
  return s;
}

export default function Staffroom() {
  const st = useBoardStats();
  const extras = {
    board: (
      <div className="sr-notes">
        <div className="sr-note"><span>Students</span><b>{st.students}</b></div>
        <div className="sr-note"><span>At risk</span><b>{st.atRisk}</b></div>
        <div className="sr-note"><span>Class avg</span><b>{st.avg}</b></div>
      </div>
    ),
  };
 return <Scene layout={layout} extras={extras} />;
}