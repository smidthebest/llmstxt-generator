import ReactMarkdown from "react-markdown";

interface Props {
  content: string;
}

export default function LlmsTxtPreview({ content }: Props) {
  return (
    <div className="border border-[#1a1a1a] rounded-lg p-6 overflow-auto max-h-[700px]">
      <div className="markdown-body">
        <ReactMarkdown
          components={{
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
}
