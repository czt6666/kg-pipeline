import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Shared renderer for every markdown surface in the app (chat replies, reasoning trace,
// evidence facts) -- one component so `.md` typography in styles.css only has to be
// tuned once. remark-gfm adds tables/strikethrough, which the trace formatter uses for
// query/evidence tables.
export function Markdown({ children, className = "" }) {
  if (!children) return null;
  return (
    <div className={"md " + className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}
