import { useEffect, useState } from "react";
import Scene from "./Scene";
import layout from "./locker-layout.json";
import { api, getClassId, getProtectedImage } from "../api";
import "../connected.css";

function ProtectedImage({ path, alt }) {
  const [src, setSrc] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true, objectUrl = "";
    getProtectedImage(path).then(url => { objectUrl = url; if (active) setSrc(url); else URL.revokeObjectURL(url); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path]);
  return src ? <img className="material-preview" src={src} alt={alt} /> : <p className="muted">{error || "Loading image…"}</p>;
}

function readProfile() {
  try { return JSON.parse(localStorage.getItem("gradify_profile") || "{}"); } catch { return {}; }
}

function dateText(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString();
}

export default function Locker() {
  const classId = getClassId();
  const profile = readProfile();
  const [attendance, setAttendance] = useState(null);
  const [assessments, setAssessments] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [progress, setProgress] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const [a,m,p,t,mat] = await Promise.all([
        api("/students/me/attendance"), api("/students/me/assessments"), api("/students/me/predictions"),
        api("/students/me/progress"), api(`/classrooms/${classId}/materials`),
      ]);
      setAttendance(a); setAssessments(m.assessments || []); setPredictions(p.predictions || []);
      setProgress(t); setMaterials(mat.materials || []); setError("");
    } catch (err) { setError(err.message); }
  }
  // Load the signed-in student data after mount / classroom change.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { refresh(); }, [classId]);

  const latest = predictions[0];
  const syllabus = materials.find(m => m.material_type === "syllabus");
  const timetable = materials.find(m => m.material_type === "timetable_photo");
  const icon = latest ? (latest.risk_status === "At Risk" ? "apple-rotten.png" : "apple-green.png") : null;
  const extras = {
    poster: icon && <div className="sr-status-wrap"><img src={`/room/${icon}`} alt={latest.risk_status} /></div>,
  };

  async function toggleTopic(topic) {
    try {
      await api("/students/me/progress", { method: "POST", body: { topic_id: topic.topic_id, is_completed: !topic.is_completed } });
      await refresh();
    } catch (err) { setError(err.message); }
  }

  const panels = {
    poster: <div className="panel-content"><h3>Your latest status</h3>{latest ? <div className={`status-card ${latest.risk_status === "At Risk" ? "risk" : "good"}`}><strong>{latest.risk_status}</strong><span>Predicted {latest.predicted_marks} / {latest.target_maximum_marks} in {latest.target_assessment}</span><small>Prediction score: {latest.regression_score}/20</small></div> : <p className="muted">No prediction has been generated for you yet. Ask your teacher to upload assessment marks.</p>}</div>,
    journal: <div className="panel-content"><h3>Prediction history</h3>{predictions.map(p => <div className="student-row" key={p.prediction_id}><span>{p.target_assessment}<small>{p.mode} · {dateText(p.created_at)} · {p.risk_status}</small></span><b>{p.predicted_marks}/{p.target_maximum_marks}</b></div>)}{!predictions.length && <p className="muted">No predictions yet.</p>}</div>,
    books: <div className="panel-content"><h3>Class syllabus</h3>{syllabus ? <ProtectedImage path={syllabus.file_url} alt="Class syllabus" /> : <p className="muted">Your teacher hasn't uploaded the syllabus yet.</p>}{timetable && <><h3>Timetable</h3><ProtectedImage path={timetable.file_url} alt="Class timetable" /></>}<h3>Topics to complete</h3><div className="topic-checklist">{(progress?.topics || []).map(topic => <label key={topic.topic_id} className="topic-check"><input type="checkbox" checked={Boolean(topic.is_completed)} onChange={() => toggleTopic(topic)} /><span>{topic.topic_name}</span></label>)}</div><p className="muted">{progress?.completed_topics || 0} of {progress?.total_topics || 0} topics completed · {progress?.progress_percentage || 0}%</p></div>,
    bag: <div className="panel-content"><h3>Attendance</h3><div className="stat-grid"><div><small>Attendance</small><strong>{attendance?.attendance_percentage == null ? "—" : `${attendance.attendance_percentage}%`}</strong></div><div><small>Present</small><strong>{attendance?.counts?.present ?? 0}</strong></div><div><small>Absent</small><strong>{attendance?.counts?.absent ?? 0}</strong></div></div><div className="data-list">{(attendance?.attendance || []).slice(0,8).map(a => <div className="student-row" key={a.attendance_id}><span>{dateText(a.attendance_date)}</span><b>{a.status}</b></div>)}</div><h3>Assessment marks</h3>{assessments.map(a => <div className="student-row" key={a.record_id}><span>{a.assessment_name}<small>{dateText(a.assessment_date)} · {a.record_status}</small></span><b>{a.obtained_marks == null ? a.record_status : `${a.obtained_marks}/${a.maximum_marks}`}</b></div>)}{!assessments.length && <p className="muted">No assessment records yet.</p>}</div>,
  };

  return <><div className="student-welcome">{profile.student_name || "Student"} · {profile.class_name || `Class ${classId}`} · ID {profile.student_id || "—"}</div><Scene layout={layout} extras={extras} panels={panels} roomLabel="MY LOCKER" />{error && <div className="student-error">{error}</div>}</>;
}
