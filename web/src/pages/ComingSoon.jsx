import { TopBar } from "../components/TopBar.jsx";

/* ---------- 流水线中尚未实现的阶段（实体对齐 / 检索 / 问答）的占位页 ---------- */
export function ComingSoon({ route, title, icon, description }) {
  return (
    <>
      <TopBar route={route} />
      <div className="home">
        <div className="soon-panel">
          <div className="card-icon">{icon}</div>
          <h2>{title}</h2>
          <p>{description}</p>
          <span className="soon-badge">待实现</span>
        </div>
      </div>
    </>
  );
}
