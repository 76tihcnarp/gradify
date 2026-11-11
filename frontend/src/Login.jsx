import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, saveSession } from "./api";
import "./connected.css";

export default function Login() {
  const go = useNavigate();
  const [role, setRole] = useState("teacher");
  const [register, setRegister] = useState(false);
  const [teacherId, setTeacherId] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [studentId, setStudentId] = useState("");
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      if (role === "teacher") {
        if (register) {
          await api("/auth/teacher/register", { method: "POST", body: { teacher_id: teacherId.trim(), password, email: email.trim() || null } });
        }
        const result = await api("/auth/teacher/login", { method: "POST", body: { teacher_id: teacherId.trim(), password } });
        saveSession({ access_token: result.access_token, role: "teacher", profile: { teacher_id: result.teacher_id } });
        go("/teacher/home");
      } else {
        const result = await api("/auth/student/login", { method: "POST", body: { student_id: Number(studentId), class_pin: pin.trim() } });
        saveSession({ access_token: result.access_token, role: "student", class_id: result.student.class_id, profile: result.student });
        go("/student");
      }
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <main className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand"><img src="/brand/gradify-full.png" alt="Gradify" /></div>
        <div className="login-kicker">YOUR CLASSROOM, REIMAGINED</div>
        <p className="login-subtitle">A little space to learn, grow and keep track.</p>
        <div className="role-switch">
          <button type="button" className={role === "teacher" ? "active" : ""} onClick={() => { setRole("teacher"); setError(""); }}>Teacher</button>
          <button type="button" className={role === "student" ? "active" : ""} onClick={() => { setRole("student"); setError(""); }}>Student</button>
        </div>
        {role === "teacher" ? (
          <>
            <label>Teacher ID<input value={teacherId} onChange={e => setTeacherId(e.target.value)} required autoComplete="username" placeholder="Enter your teacher ID" /></label>
            {register && <label>Email (optional)<input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" /></label>}
            <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={register ? 8 : 1} autoComplete={register ? "new-password" : "current-password"} placeholder="Enter password" /></label>
            <button className="primary-btn" disabled={busy}>{busy ? "Please wait…" : register ? "Create account & sign in" : "Sign in"}</button>
            <button type="button" className="text-btn" onClick={() => { setRegister(!register); setError(""); }}>{register ? "Already registered? Sign in" : "New teacher? Create an account"}</button>
          </>
        ) : (
          <>
            <label>Student ID<input inputMode="numeric" value={studentId} onChange={e => setStudentId(e.target.value)} required placeholder="Enter the ID given by your teacher" /></label>
            <label>Class PIN<input value={pin} onChange={e => setPin(e.target.value)} required maxLength={20} placeholder="Enter your classroom PIN" /></label>
            <button className="primary-btn" disabled={busy}>{busy ? "Please wait…" : "Open my locker"}</button>
          </>
        )}
        {error && <div className="error-message" role="alert">{error}</div>}
        <p className="login-foot">Gradify · Student Performance & Progress</p>
      </form>
    </main>
  );
}
