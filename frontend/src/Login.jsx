import { useNavigate } from "react-router-dom";

export default function Login() {
  const go = useNavigate();
  const enter = (role) => {
    // TODO: replace with POST /login, then store the token and role it returns.
    localStorage.setItem("role", role);
    go(role === "teacher" ? "/teacher" : "/student");
  };
  return (
    <div style={{ color: "#fff6dc", font: "16px system-ui", textAlign: "center" }}>
      <h1 style={{ marginBottom: 24 }}>GRADIFY</h1>
      <button onClick={() => enter("teacher")} style={{ margin: 8, padding: "12px 20px" }}>Enter as teacher</button>
      <button onClick={() => enter("student")} style={{ margin: 8, padding: "12px 20px" }}>Enter as student</button>
    </div>
  );
}