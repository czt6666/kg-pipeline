import { useEffect, useState } from "react";
import { hashRoute } from "./utils/api.js";
import { Home } from "./pages/Home.jsx";
import { GraphExplorer } from "./pages/GraphExplorer.jsx";
import { DebugView } from "./pages/DebugView.jsx";

export function App() {
  const [route, setRoute] = useState(hashRoute());
  useEffect(() => {
    const onHash = () => setRoute(hashRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  if (route === "graph") return <GraphExplorer />;
  if (route === "debug") return <DebugView />;
  return <Home />;
}
