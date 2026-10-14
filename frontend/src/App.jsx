
import { useState } from "react";
import "./App.css";

const navigation = [
  { icon: "⌂", label: "Staffroom" },
  { icon: "▤", label: "Predictions" },
  { icon: "◷", label: "Attendance" },
  { icon: "▥", label: "Syllabus" },
  { icon: "✓", label: "Tasks & Progress" },
];

const initialStats = [
  { label: "Total Students", value: "395", icon: "♙", tone: "blue" },
  { label: "Class Pass Rate", value: "67.1%", icon: "↗", tone: "green" },
  { label: "At-Risk Students", value: "130", icon: "!", tone: "orange" },
  { label: "Average Grade", value: "10.4/20", icon: "✳", tone: "purple" },
];

const students = [
  { id: 1, name: "Student 1", grade: 6, status: "At Risk" },
  { id: 2, name: "Student 2", grade: 8, status: "At Risk" },
  { id: 3, name: "Student 3", grade: 14, status: "On Track" },
  { id: 4, name: "Student 4", grade: 16, status: "On Track" },
];

const grades = [
  { label: "Period 1", value: 10.05 },
  { label: "Period 2", value: 10.17 },
  { label: "Period 3", value: 11.4 },
  { label: "Period 4", value: 11.26 },
];

function App() {
  const [activePage, setActivePage] = useState("Staffroom");
  const [search, setSearch] = useState("");

  const filteredStudents = students.filter((student) =>
    student.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">G</div>
          <div>
            <h1>GRADIFY</h1>
            <span>TEACHER WORKSPACE</span>
          </div>
        </div>

        <div className="side-label">YOUR WORKSPACE</div>

        <nav className="navigation">
          {navigation.map((item) => (
            <button
              key={item.label}
              className={`nav-item ${
                activePage === item.label ? "active" : ""
              }`}
              onClick={() => setActivePage(item.label)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
              {item.label === "Predictions" && (
                <span className="nav-count">!</span>
              )}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <span className="note-icon">✦</span>
            <h3>A little reminder</h3>
            <p>Every student has potential. Your guidance helps them find it.</p>
          </div>
          <div className="teacher-profile">
            <div className="avatar">T</div>
            <div>
              <strong>Teacher Workspace</strong>
              <span>Class educator</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb-slash">/</span>
            <strong>{activePage}</strong>
          </div>
          <div className="topbar-right">
            <span className="live-dot" />
            <span className="demo-label">Dashboard preview</span>
            <div className="avatar small-avatar">T</div>
          </div>
        </header>

        <div className="page-content">
          <section className="welcome-row">
            <div>
              <p className="eyebrow">YOUR VIRTUAL STAFFROOM</p>
              <h2>
                Good day, <span>Teacher.</span>
              </h2>
              <p className="welcome-description">
                Your classroom at a glance. Let's help every student move
                forward.
              </p>
            </div>
            <div className="date-card">
              <span className="date-icon">▦</span>
              <div>
                <strong>Academic overview</strong>
                <span>Student performance & progress</span>
              </div>
            </div>
          </section>

          <section className="notice-banner">
            <div className="notice-symbol">✦</div>
            <div>
              <strong>Your staffroom is ready.</strong>
              <p>
                Explore the classroom overview, predictions, and student
                progress from one place.
              </p>
            </div>
            <span className="notice-decoration">GRADIFY</span>
          </section>

          {activePage === "Staffroom" ? (
            <>
              <section className="section-heading">
                <div>
                  <h3>Classroom overview</h3>
                  <p>A snapshot of your students' academic performance.</p>
                </div>
                <span className="section-tag">SAMPLE DATA</span>
              </section>

              <section className="stats-grid">
                {initialStats.map((stat) => (
                  <article className="stat-card" key={stat.label}>
                    <div className={`stat-icon ${stat.tone}`}>{stat.icon}</div>
                    <p>{stat.label}</p>
                    <div className="stat-bottom">
                      <strong>{stat.value}</strong>
                      <span className="stat-decoration">✳</span>
                    </div>
                  </article>
                ))}
              </section>

              <section className="dashboard-grid">
                <article className="panel performance-panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Study time & performance</h3>
                      <p>Average final grade by study-time level</p>
                    </div>
                    <span className="mini-icon">↗</span>
                  </div>

                  <div className="chart">
                    {grades.map((grade) => (
                      <div className="chart-column" key={grade.label}>
                        <strong>{grade.value.toFixed(1)}</strong>
                        <div className="bar-track">
                          <div
                            className="bar-fill"
                            style={{ height: `${(grade.value / 20) * 100}%` }}
                          />
                        </div>
                        <span>{grade.label}</span>
                      </div>
                    ))}
                  </div>
                  <div className="chart-footnote">
                    <span className="legend-dot" />
                    Average grade out of 20
                  </div>
                </article>

                <article className="panel focus-panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Teacher's focus</h3>
                      <p>Where your attention can help most</p>
                    </div>
                    <span className="mini-icon">◎</span>
                  </div>

                  <div className="focus-item">
                    <div className="focus-icon orange">!</div>
                    <div className="focus-copy">
                      <strong>Students needing support</strong>
                      <span>Review their recent performance</span>
                    </div>
                    <span className="focus-arrow">→</span>
                  </div>
                  <div className="focus-item">
                    <div className="focus-icon green">✓</div>
                    <div className="focus-copy">
                      <strong>Learning progress</strong>
                      <span>Check completed syllabus topics</span>
                    </div>
                    <span className="focus-arrow">→</span>
                  </div>
                  <div className="focus-item">
                    <div className="focus-icon purple">▤</div>
                    <div className="focus-copy">
                      <strong>Performance predictions</strong>
                      <span>Review estimated student scores</span>
                    </div>
                    <span className="focus-arrow">→</span>
                  </div>
                </article>
              </section>

              <section className="panel student-panel">
                <div className="panel-heading student-panel-heading">
                  <div>
                    <h3>Student watchlist</h3>
                    <p>A sample of student records for the dashboard preview.</p>
                  </div>
                  <label className="search-box">
                    <span>⌕</span>
                    <input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search students"
                      aria-label="Search students"
                    />
                  </label>
                </div>

                <div className="student-table-wrap">
                  <table className="student-table">
                    <thead>
                      <tr>
                        <th>STUDENT</th>
                        <th>RECORDED GRADE</th>
                        <th>STATUS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredStudents.map((student) => (
                        <tr key={student.id}>
                          <td>
                            <div className="student-name">
                              <div className="student-avatar">
                                {student.name.slice(-1)}
                              </div>
                              <span>{student.name}</span>
                            </div>
                          </td>
                          <td>{student.grade}/20</td>
                          <td>
                            <span
                              className={`status-pill ${
                                student.status === "At Risk"
                                  ? "at-risk"
                                  : "on-track"
                              }`}
                            >
                              <span className="status-dot" />
                              {student.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                      {filteredStudents.length === 0 && (
                        <tr>
                          <td colSpan="3" className="empty-state">
                            No matching sample students found.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="table-disclaimer">
                  These watchlist rows are placeholders, not live student
                  records.
                </p>
              </section>
            </>
          ) : (
            <section className="panel page-placeholder">
              <div className="placeholder-icon">✦</div>
              <p className="eyebrow">GRADIFY WORKSPACE</p>
              <h3>{activePage}</h3>
              <p>
                This workspace is ready for its next step. We'll make this
                section functional and connect it to your FastAPI backend.
              </p>
              <button
                className="back-button"
                onClick={() => setActivePage("Staffroom")}
              >
                ← Back to Staffroom
              </button>
            </section>
          )}

          <footer className="footer">
            <span>GRADIFY · Teacher workspace</span>
            <span>Supporting progress, one student at a time.</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default App;
