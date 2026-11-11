import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, clearSession } from "./api";
import "./connected.css";

export default function TeacherHome() {
  const go = useNavigate();
  const [classes, setClasses] = useState([]);
  const [selected, setSelected] = useState(null);
  const [className, setClassName] = useState("");
  const [rosterFile, setRosterFile] = useState(null);
  const [students, setStudents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadClasses() {
    try {
      const result = await api("/classrooms");
      setClasses(result.classrooms || []);
      const savedId = Number(localStorage.getItem("gradify_class_id") || 0);
      const preferred = (result.classrooms || []).find(c => c.class_id === savedId) || (result.classrooms || [])[0] || null;
      if (preferred) await chooseClass(preferred);
    } catch (err) { setError(err.message); }
  }

  async function chooseClass(item) {
    setSelected(item);
    localStorage.setItem("gradify_class_id", String(item.class_id));
    try {
      const result = await api(`/classrooms/${item.class_id}/students`);
      setStudents(result.students || []);
      setSelected(current => current ? { ...current, ...item, class_pin: result.class_pin, class_name: result.class_name, student_count: result.total_students } : item);
    } catch (err) { setError(err.message); }
  }

  // Fetch classroom state on mount; updates occur after the asynchronous API response.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { loadClasses(); }, []);

  async function createClass(e) {
    e.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const result = await api("/classrooms", { method: "POST", body: { class_name: className.trim() } });
      setClassName("");
      setMessage(`Created ${result.class_name}. Classroom PIN: ${result.class_pin}`);
      await loadClasses();
      const item = { class_id: result.class_id, class_name: result.class_name, class_pin: result.class_pin, student_count: 0 };
      await chooseClass(item);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function uploadRoster(e) {
    e.preventDefault();
    if (!selected || !rosterFile) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const form = new FormData(); form.append("file", rosterFile);
      const result = await api(`/classrooms/${selected.class_id}/students/upload`, { method: "POST", form });
      setMessage(`Added ${result.total_created} students successfully.`);
      setRosterFile(null);
      e.target.reset();
      await chooseClass(selected);
      await loadClasses();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <main className="teacher-home">
      <header className="home-header">
        <div><span className="eyebrow">GRADIFY · STAFFROOM</span><h1>Your classrooms</h1><p>Choose a class or set up a new one.</p></div>
        <button className="quiet-btn" onClick={() => { clearSession(); go("/"); }}>Sign out</button>
      </header>
      {error && <div className="error-message">{error}</div>}
      {message && <div className="success-message">{message}</div>}
      <div className="home-grid">
        <section className="home-card">
          <h2>My classes</h2>
          {classes.length === 0 ? <p className="muted">No classroom yet. Create your first one.</p> : (
            <div className="class-list">
              {classes.map(item => <button key={item.class_id} className={`class-choice ${selected?.class_id === item.class_id ? "chosen" : ""}`} onClick={() => chooseClass(item)}>
                <span><strong>{item.class_name}</strong><small>{item.student_count} students · Class ID {item.class_id}</small></span><span>→</span>
              </button>)}
            </div>
          )}
          <form className="stack-form" onSubmit={createClass}>
            <label>Create classroom<input value={className} onChange={e => setClassName(e.target.value)} required maxLength={100} placeholder="e.g. CSE-26" /></label>
            <button className="primary-btn" disabled={busy}>Create classroom</button>
          </form>
        </section>
        <section className="home-card">
          <h2>{selected ? selected.class_name : "Class setup"}</h2>
          {selected ? <>
            <div className="pin-display"><span>Shared student PIN</span><strong>{selected.class_pin || "—"}</strong><small>Give students their individual Student ID and this class PIN.</small></div>
            <form className="stack-form" onSubmit={uploadRoster}>
              <label>Upload student roster (CSV)<input type="file" accept=".csv,text/csv" required onChange={e => setRosterFile(e.target.files?.[0] || null)} /></label>
              <small className="muted">Required columns: student_name and roll_number.</small>
              <button className="primary-btn" disabled={busy || !rosterFile}>Upload roster</button>
            </form>
            <div className="student-mini-list"><h3>Students ({students.length})</h3>
              {students.map(s => <div className="student-row" key={s.student_id}><span>{s.student_name}<small>Roll {s.roll_number}</small></span><b>ID {s.student_id}</b></div>)}
            </div>
            <button className="primary-btn enter-room" onClick={() => go("/teacher")}>Enter staffroom →</button>
          </> : <p className="muted">Select a classroom to view its PIN, upload its roster and open the staffroom.</p>}
        </section>
      </div>
      <div className="home-note">Your classroom data is kept separate by its classroom ID.</div>
    </main>
  );
}
