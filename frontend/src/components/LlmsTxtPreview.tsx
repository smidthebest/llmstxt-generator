import ReactMarkdown from "react-markdown";

interface Props {
  content: string;
}

export default function LlmsTxtPreview({ content }: Props) {
  return (
    <div className="prose prose-sm max-w-none bg-white p-6 rounded-lg border overflow-auto max-h-[600px]">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
