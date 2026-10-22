import Scene from "./Scene";
import layout from "./locker-layout.json";

// Two states only: good = green apple, risk = rotten apple.
const ICON = { good: "apple-green", risk: "apple-rotten" };

export default function Locker() {
  // TODO: get this from the student's real prediction ("good" or "risk").
  // For testing, open /student?status=risk or /student?status=good
  const status = new URLSearchParams(window.location.search).get("status");

  const extras = {
    poster: ICON[status] && (
      <div className="sr-status-wrap">
        <img src={`/room/${ICON[status]}.webp`} alt="" />
      </div>
    ),
  };
  return <Scene layout={layout} extras={extras} />;
}