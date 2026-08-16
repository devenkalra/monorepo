import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import {
  expandHeadingAnchors,
  createMarkdownLinkComponent,
  MarkdownIframe,
  rehypeSourceLines,
} from '../utils/markdown';

/**
 * Shared markdown renderer: GFM (tables, strikethrough, task lists),
 * raw HTML, heading [#id] anchors, and optional in-app link navigation.
 */
export function MarkdownBody({ children, navigate, sourceLines = false }) {
  const content = expandHeadingAnchors(children || '');
  const components = {
    iframe: MarkdownIframe,
    ...(navigate ? { a: createMarkdownLinkComponent(navigate) } : {}),
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={sourceLines ? [rehypeRaw, rehypeSourceLines] : [rehypeRaw]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
}
