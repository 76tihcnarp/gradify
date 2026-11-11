import { Routes, Route, Navigate } from "react-router-dom";
import Login from "./Login";
import Staffroom from "./staffroom/Staffroom";
import Locker from "./staffroom/Locker";
import TeacherHome from "./TeacherHome";
import { getRole, getToken } from "./api";

function Guard({ role, children }) {
  return getToken() && getRole() === role ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/teacher/home" element={<Guard role="teacher"><TeacherHome /></Guard>} />
      <Route path="/teacher" element={<Guard role="teacher"><Staffroom /></Guard>} />
      <Route path="/student" element={<Guard role="student"><Locker /></Guard>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
