import { Routes, Route, Navigate } from "react-router-dom";
import Login from "./Login";
import Staffroom from "./staffroom/Staffroom";
import Locker from "./staffroom/Locker";

// Convenience only. Real security must be enforced by your FastAPI (token + role checks).
function Guard({ role, children }) {
  return localStorage.getItem("role") === role ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/teacher" element={<Guard role="teacher"><Staffroom /></Guard>} />
      <Route path="/student" element={<Guard role="student"><Locker /></Guard>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}