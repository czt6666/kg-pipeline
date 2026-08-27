export function TopBar({ route }) {
  return (
    <header className="topbar">
      <a href="#/" className="brand">◆ KG 工作台</a>
      <nav>
        <a href="#/graph" className={route === "graph" ? "on" : ""}>完整知识图谱</a>
        <a href="#/debug" className={route === "debug" ? "on" : ""}>细节调试</a>
      </nav>
      <div className="spacer" />
    </header>
  );
}
