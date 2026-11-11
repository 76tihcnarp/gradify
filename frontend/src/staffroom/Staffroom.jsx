import { useEffect, useState } from "react";
import Scene from "./Scene";
import layout from "./staffroom-layout.json";
import { api, getClassId, getProtectedImage } from "../api";
import "../connected.css";

function Notice({ error, message }) {
  if (!error && !message) return null;
  return <div className={error ? "error-message" : "success-message"}>{error || message}</div>;
}

function ProtectedImage({ path, alt }) {
  const [src, setSrc] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true, objectUrl = "";
    getProtectedImage(path).then(url => { objectUrl = url; if (active) setSrc(url); else URL.revokeObjectURL(url); })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path]);
  return src ? <img className="material-preview" src={src} alt={alt} /> : <p className="muted">{error || "Loading image…"}</p>;
}

function MaterialUpload({ classId, type, onUploaded }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault(); if (!file) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const form = new FormData(); form.append("file", file);
      const result = await api(`/classrooms/${classId}/materials?material_type=${type}`, { method: "POST", form });
      setNotice(`${type === "timetable_photo" ? "Timetable" : "Syllabus"} uploaded.`);
      setFile(null); e.target.reset(); onUploaded?.(result);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <form className="inline-upload" onSubmit={submit}>
    <input type="file" accept="image/jpeg,image/png,image/webp" required onChange={e => setFile(e.target.files?.[0] || null)} />
    <button className="small-primary" disabled={busy || !file}>{busy ? "Uploading…" : "Upload image"}</button>
    <Notice error={error} message={notice} />
  </form>;
}

function AttendancePanel({ classId, students }) {
  const [date, setDate] = useState(new Date().toLocaleDateString("en-CA"));
  const [statuses, setStatuses] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const records = students.map(s => ({ student_id: s.student_id, status: statuses[s.student_id] || "present" }));
      const result = await api(`/classrooms/${classId}/attendance`, { method: "POST", body: { attendance_date: date, records } });
      setMessage(`Saved ${result.records_saved} attendance records.`);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="panel-content">
    <h3>Mark today's attendance</h3>
    {students.length === 0 ? <p className="muted">Upload a student roster first.</p> : <form onSubmit={submit}>
      <label>Date<input type="date" value={date} onChange={e => setDate(e.target.value)} required /></label>
      <div className="data-list">{students.map(s => <div className="attendance-row" key={s.student_id}>
        <span>{s.student_name}<small>Roll {s.roll_number} · ID {s.student_id}</small></span>
        <select value={statuses[s.student_id] || "present"} onChange={e => setStatuses(v => ({ ...v, [s.student_id]: e.target.value }))}>
          <option value="present">Present</option><option value="absent">Absent</option><option value="late">Late</option>
        </select>
      </div>)}</div>
      <button className="small-primary" disabled={busy}>{busy ? "Saving…" : "Save attendance"}</button>
    </form>}
    <Notice error={error} message={message} />
  </div>;
}

function AnalyticsPanel({ classId, analytics, atRisk, students }) {
  const [score, setScore] = useState("13");
  const [count, setCount] = useState(null);
  const [error, setError] = useState("");
  async function check(e) {
    e.preventDefault(); setError("");
    try { setCount(await api(`/classrooms/${classId}/analytics/score-count?score=${encodeURIComponent(score)}`)); }
    catch (err) { setError(err.message); }
  }
  return <div className="panel-content">
    <div className="stat-grid">
      <div><small>Total students</small><strong>{analytics?.total_students ?? "—"}</strong></div>
      <div><small>At risk</small><strong>{analytics?.at_risk_count ?? "—"}</strong></div>
      <div><small>Class average</small><strong>{analytics?.average_predicted_score ?? "—"}/20</strong></div>
    </div>
    <p className="muted">Predictions available for {analytics?.students_with_predictions ?? 0} of {analytics?.total_students ?? students.length} students.</p>
    <form className="score-form" onSubmit={check}>
      <label>How many students are predicted to score (out of 20)?<input type="number" min="0" max="20" step="1" value={score} onChange={e => setScore(e.target.value)} /></label>
      <button className="small-primary">Count students</button>
    </form>
    {count && <div className="result-strip"><strong>{count.matching_students}</strong> students predicted around {count.requested_score}/20</div>}
    <Notice error={error} />
    <h3>Students needing support</h3>
    {atRisk.length ? <div className="data-list">{atRisk.map(s => <div className="student-row" key={s.student_id}><span>{s.student_name}<small>Roll {s.roll_number}</small></span><b>{s.regression_score}/20</b></div>)}</div> : <p className="muted">No at-risk students in the latest predictions.</p>}
  </div>;
}

function PredictionPanel({ classId, students }) {
  const [form, setForm] = useState({ student_id: "", g1_marks: "", g1_maximum_marks: "20", g2_marks: "", g2_maximum_marks: "20", target_assessment: "Final Examination", target_maximum_marks: "70", mode: "quick", failures: "0", absences: "0", studytime: "2" });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const change = e => setForm(v => ({ ...v, [e.target.name]: e.target.value }));
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(""); setResult(null);
    try {
      const body = {
        student_id: Number(form.student_id), g1_marks: Number(form.g1_marks), g1_maximum_marks: Number(form.g1_maximum_marks),
        g2_marks: Number(form.g2_marks), g2_maximum_marks: Number(form.g2_maximum_marks),
        target_assessment: form.target_assessment, target_maximum_marks: Number(form.target_maximum_marks),
      };
      if (form.mode === "detailed") Object.assign(body, { failures: Number(form.failures), absences: Number(form.absences), studytime: Number(form.studytime) });
      setResult(await api(`/classrooms/${classId}/predict/${form.mode}`, { method: "POST", body }));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <form className="panel-content" onSubmit={submit}>
    <label>Student<select name="student_id" value={form.student_id} onChange={change} required><option value="">Choose student</option>{students.map(s => <option key={s.student_id} value={s.student_id}>{s.student_name} · Roll {s.roll_number} · ID {s.student_id}</option>)}</select></label>
    <label>Prediction mode<select name="mode" value={form.mode} onChange={change}><option value="quick">Quick</option><option value="detailed">Detailed</option></select></label>
    <div className="form-grid">
      <label>G1 marks<input name="g1_marks" type="number" min="0" step="0.01" value={form.g1_marks} onChange={change} required /></label>
      <label>G1 maximum<input name="g1_maximum_marks" type="number" min="0.01" step="0.01" value={form.g1_maximum_marks} onChange={change} required /></label>
      <label>G2 marks<input name="g2_marks" type="number" min="0" step="0.01" value={form.g2_marks} onChange={change} required /></label>
      <label>G2 maximum<input name="g2_maximum_marks" type="number" min="0.01" step="0.01" value={form.g2_maximum_marks} onChange={change} required /></label>
    </div>
    {form.mode === "detailed" && <div className="form-grid">
      <label>Failures<input name="failures" type="number" min="0" value={form.failures} onChange={change} /></label>
      <label>Absences<input name="absences" type="number" min="0" value={form.absences} onChange={change} /></label>
      <label>Study time (1–4)<input name="studytime" type="number" min="1" max="4" value={form.studytime} onChange={change} /></label>
    </div>}
    <label>Target assessment<input name="target_assessment" value={form.target_assessment} onChange={change} required /></label>
    <label>Target maximum marks<input name="target_maximum_marks" type="number" min="0.01" step="0.01" value={form.target_maximum_marks} onChange={change} required /></label>
    <button className="small-primary" disabled={busy || !students.length}>{busy ? "Predicting…" : "Run & save prediction"}</button>
    {result && <div className="prediction-result"><strong>{result.predicted_marks} / {result.target_maximum_marks}</strong><span>{result.risk_status} · Model score {result.regression_score}/20</span></div>}
    <Notice error={error} />
  </form>;
}

function AssessmentUploadPanel({ classId, onUploaded }) {
  const [file, setFile] = useState(null);
  const [form, setForm] = useState({ g1_assessment_name: "G1", g1_maximum_marks: "30", g2_assessment_name: "G2", g2_maximum_marks: "30", target_assessment: "Final Examination", target_maximum_marks: "70", mode: "quick", assessment_date: new Date().toLocaleDateString("en-CA") });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const change = e => setForm(v => ({ ...v, [e.target.name]: e.target.value }));
  async function submit(e) {
    e.preventDefault(); if (!file) return;
    setBusy(true); setError(""); setResult(null);
    try {
      const data = new FormData(); data.append("file", file);
      Object.entries(form).forEach(([k,v]) => data.append(k,v));
      const response = await api(`/classrooms/${classId}/assessments/upload`, { method: "POST", form: data });
      setResult(response); setFile(null); e.target.reset(); onUploaded?.();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <form className="panel-content" onSubmit={submit}>
    <p className="muted">CSV columns: roll_number, G1, G2. For detailed mode also include failures, absences and studytime. Use A for absent and leave blank for missing.</p>
    <label>Assessment CSV<input type="file" accept=".csv,text/csv" required onChange={e => setFile(e.target.files?.[0] || null)} /></label>
    <div className="form-grid">
      <label>G1 name<input name="g1_assessment_name" value={form.g1_assessment_name} onChange={change} /></label>
      <label>G1 max marks<input name="g1_maximum_marks" type="number" min="0.01" value={form.g1_maximum_marks} onChange={change} required /></label>
      <label>G2 name<input name="g2_assessment_name" value={form.g2_assessment_name} onChange={change} /></label>
      <label>G2 max marks<input name="g2_maximum_marks" type="number" min="0.01" value={form.g2_maximum_marks} onChange={change} required /></label>
      <label>Target assessment<input name="target_assessment" value={form.target_assessment} onChange={change} required /></label>
      <label>Target max marks<input name="target_maximum_marks" type="number" min="0.01" value={form.target_maximum_marks} onChange={change} required /></label>
      <label>Prediction mode<select name="mode" value={form.mode} onChange={change}><option value="quick">Quick</option><option value="detailed">Detailed</option></select></label>
      <label>Assessment date<input name="assessment_date" type="date" value={form.assessment_date} onChange={change} /></label>
    </div>
    <button className="small-primary" disabled={busy || !file}>{busy ? "Uploading…" : "Upload & predict"}</button>
    {result && <div className="success-message">Batch #{result.batch_id}: {result.predictions_created} predictions created, {result.predictions_skipped?.length || 0} skipped.</div>}
    <Notice error={error} />
  </form>;
}

export default function Staffroom() {
  const classId = getClassId();
  const [analytics, setAnalytics] = useState(null);
  const [atRisk, setAtRisk] = useState([]);
  const [students, setStudents] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [topics, setTopics] = useState([]);
  const [progress, setProgress] = useState([]);
  const [batches, setBatches] = useState([]);
  const [error, setError] = useState("");
  const [topicName, setTopicName] = useState("");
  const [topicMessage, setTopicMessage] = useState("");

  async function refresh() {
    if (!classId) return;
    setError("");
    try {
      const [a,r,s,m,t,p,b] = await Promise.all([
        api(`/classrooms/${classId}/analytics`), api(`/classrooms/${classId}/students/at-risk`),
        api(`/classrooms/${classId}/students`), api(`/classrooms/${classId}/materials`),
        api(`/classrooms/${classId}/topics`), api(`/classrooms/${classId}/progress`),
        api(`/classrooms/${classId}/assessment-batches`),
      ]);
      setAnalytics(a); setAtRisk(r.students || []); setStudents(s.students || []);
      setMaterials(m.materials || []); setTopics(t.topics || []); setProgress(p.progress || []); setBatches(b.batches || []);
    } catch (err) { setError(err.message); }
  }
  // Load the selected classroom after mount / classroom switch.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { refresh(); }, [classId]);

  const timetable = materials.find(m => m.material_type === "timetable_photo");
  const syllabus = materials.find(m => m.material_type === "syllabus");

  async function addTopic(e) {
    e.preventDefault(); setTopicMessage("");
    try {
      await api(`/classrooms/${classId}/topics`, { method: "POST", body: { topic_name: topicName.trim(), sort_order: topics.length + 1 } });
      setTopicName(""); setTopicMessage("Topic added."); await refresh();
    } catch (err) { setTopicMessage(err.message); }
  }

  const extras = {
    board: <div className="sr-notes">
      <div className="sr-note"><span>Students</span><b>{analytics?.total_students ?? "—"}</b></div>
      <div className="sr-note"><span>At risk</span><b>{analytics?.at_risk_count ?? "—"}</b></div>
      <div className="sr-note"><span>Class avg</span><b>{analytics?.average_predicted_score ?? "—"}</b></div>
    </div>,
  };

  const panels = {
    board: <><Notice error={error} /><AnalyticsPanel classId={classId} analytics={analytics} atRisk={atRisk} students={students} /><AttendancePanel classId={classId} students={students} /></>,
    timetable: <div className="panel-content"><h3>Class timetable</h3>{timetable ? <ProtectedImage path={timetable.file_url} alt="Class timetable" /> : <p className="muted">No timetable uploaded yet.</p>}<MaterialUpload classId={classId} type="timetable_photo" onUploaded={refresh} /></div>,
    shelf: <div className="panel-content"><h3>Class syllabus</h3>{syllabus ? <ProtectedImage path={syllabus.file_url} alt="Class syllabus" /> : <p className="muted">No syllabus uploaded yet.</p>}<MaterialUpload classId={classId} type="syllabus" onUploaded={refresh} /><h3>Topic checklist</h3><form className="inline-upload" onSubmit={addTopic}><input value={topicName} onChange={e => setTopicName(e.target.value)} placeholder="New topic name" required /><button className="small-primary">Add topic</button></form><Notice message={topicMessage} /><div className="data-list">{topics.map(t => <div className="student-row" key={t.topic_id}><span>{t.sort_order}. {t.topic_name}<small>{t.completed_records || 0} completion records</small></span><b>{t.completed_records ? `${t.completed_records}` : "—"}</b></div>)}</div></div>,
    drafts: <><AssessmentUploadPanel classId={classId} onUploaded={refresh} /><div className="panel-content"><h3>Recent assessment uploads</h3>{batches.slice(0,5).map(b => <div className="student-row" key={b.batch_id}><span>Batch #{b.batch_id}<small>{b.target_assessment} · {b.mode}</small></span><b>{b.predictions_created} predictions</b></div>)}</div></>,
    journal: <PredictionPanel classId={classId} students={students} />,
    pens: <div className="panel-content"><h3>Student topic progress</h3>{students.map(s => {
      const rows = progress.filter(p => p.student_id === s.student_id);
      const completed = rows.filter(p => p.is_completed).length;
      const percent = rows.length ? Math.round(completed / rows.length * 100) : 0;
      return <div className="progress-student" key={s.student_id}><div><strong>{s.student_name}</strong><span>{completed}/{rows.length} topics · {percent}%</span></div><div className="progress-track"><i style={{ width: `${percent}%` }} /></div></div>;
    })}{!students.length && <p className="muted">Upload a roster to view student progress.</p>}</div>,
  };

  if (!classId) return <div className="connected-empty"><h2>No classroom selected</h2><button className="primary-btn" onClick={() => window.location.assign("/teacher/home")}>Choose a classroom</button></div>;
  return <><button className="room-switch" onClick={() => window.location.assign("/teacher/home")}>← Classrooms</button><Scene layout={layout} extras={extras} panels={panels} roomLabel={`STAFFROOM · CLASS ${classId}`} /></>;
}
