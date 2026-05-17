import ReactMarkdown from "react-markdown";

export default function MarkdownContent({ text }: { text: string }) {
  return (
    <div className="text-sm leading-relaxed text-gray-800 space-y-2
      [&_h1]:text-lg [&_h1]:font-bold [&_h1]:text-gray-900
      [&_h2]:text-base [&_h2]:font-bold [&_h2]:text-gray-900
      [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-gray-900
      [&_p]:text-gray-700 [&_p]:mb-1
      [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5
      [&_li]:mb-1
      [&_a]:text-blue-600 [&_a]:underline
      [&_strong]:font-semibold [&_strong]:text-gray-800
      [&_code]:rounded [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_code]:text-pink-600 [&_code]:font-mono
      [&_pre]:bg-gray-900 [&_pre]:text-gray-100 [&_pre]:rounded [&_pre]:p-3 [&_pre]:text-xs [&_pre]:overflow-x-auto [&_pre]:mb-2
      [&_table]:w-full [&_table]:text-xs [&_table]:border-collapse [&_table]:mb-2
      [&_th]:border [&_th]:border-gray-300 [&_th]:bg-gray-50 [&_th]:px-2 [&_th]:py-1 [&_th]:font-medium [&_th]:text-left
      [&_td]:border [&_td]:border-gray-300 [&_td]:px-2 [&_td]:py-1
      [&_hr]:border-gray-200 [&_hr]:my-3
      [&_blockquote]:border-l-4 [&_blockquote]:border-blue-300 [&_blockquote]:pl-3 [&_blockquote]:text-gray-500 [&_blockquote]:italic
    ">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  );
}
