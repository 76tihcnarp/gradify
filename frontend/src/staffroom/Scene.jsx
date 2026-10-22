import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import "./Staffroom.css";

export default function Scene({ layout, extras = {} }) {
  const [open, setOpen] = useState(null);
  const [nowPlaying, setNowPlaying] = useState(null); // src of the song playing, or null
  const audio = useRef(null);
  const go = useNavigate();
  const p = open && layout.panels?.[open];

  useEffect(() => {
    const k = (e) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", k);
    return () => {
      window.removeEventListener("keydown", k);
      audio.current?.pause(); // stop the song when leaving the page
    };
  }, []);

  const toggleSong = (src) => {
    const a = audio.current ?? (audio.current = new Audio());
    if (nowPlaying === src) {
      a.pause();
      setNowPlaying(null);
      return;
    }
    a.pause();
    a.src = src;
    a.onended = () => setNowPlaying(null);
    a.play().then(() => setNowPlaying(src)).catch(() => setNowPlaying(null));
  };

  return (
    <main className="sr">
      <div
        className="sr-world"
        style={{
          backgroundImage: `url(${layout.background})`,
          backgroundSize: `${(layout.bgZoom ?? 1) * 100}% auto`,
          backgroundPosition: `${layout.bgX ?? 50}% ${layout.bgY ?? 100}%`,
        }}
      >
        {layout.objects.map((o) => {
          const style = {
            left: `${o.left}%`, top: `${o.top}%`, width: `${o.w}%`,
            ...(o.rot ? { transform: `rotate(${o.rot}deg)` } : {}),
          };
          const img = <img src={`/room/${o.img}.${o.ext ?? "png"}`} alt="" draggable="false" />;
          if (!o.live)
            return <div key={o.id} className="sr-obj" style={style}>{img}</div>;
          const isPlaying = o.audio && nowPlaying === o.audio;
          return (
            <button
              key={o.id}
              className={`sr-obj ${isPlaying ? "playing" : ""}`}
              style={style}
              aria-label={o.label}
              onClick={() => (o.audio ? toggleSong(o.audio) : setOpen(o.panel))}
            >
              {img}
              {extras[o.id]}
              <span className="sr-tag">{isPlaying ? "Stop" : o.label}</span>
            </button>
          );
        })}
      </div>

      <button className="sr-out" onClick={() => { localStorage.removeItem("role"); go("/"); }}>
        Sign out
      </button>

      {p && (
        <div className="sr-veil" onMouseDown={(e) => e.target === e.currentTarget && setOpen(null)}>
          <section className="sr-panel" role="dialog" aria-modal="true" aria-label={p.title}>
            <h2>{p.title}</h2>
            <p>{p.blurb}</p>
            <div className="sr-api">{p.api.map((a) => <code key={a}>{a}</code>)}</div>
            <button className="sr-back" onClick={() => setOpen(null)}>Back to the room</button>
          </section>
        </div>
      )}
    </main>
  );
}