import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { rehypeSourceLines } from './scrollSync';

export function MarkdownBody({ children, sourceLines = false }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={sourceLines ? [rehypeRaw, rehypeSourceLines] : [rehypeRaw]}
    >
      {children || ''}
    </ReactMarkdown>
  );
}
