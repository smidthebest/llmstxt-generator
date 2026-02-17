import ReactMarkdown from "react-markdown";

interface Props {
  content: string;
}

export default function LlmsTxtPreview({ content }: Props) {
  return (
    <div className="bg-white p-6 rounded-lg border overflow-auto max-h-[700px]">
      <article className="prose prose-slate max-w-none prose-headings:font-semibold prose-h1:text-2xl prose-h1:border-b prose-h1:pb-2 prose-h2:text-lg prose-h2:mt-6 prose-blockquote:text-gray-600 prose-blockquote:border-blue-300 prose-a:text-blue-600 prose-li:my-0.5">
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
      </article>
    </div>
  );
}
