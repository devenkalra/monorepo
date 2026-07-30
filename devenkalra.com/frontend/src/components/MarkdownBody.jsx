import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { expandHeadingAnchors, createMarkdownLinkComponent } from '../utils/markdown';

/**
 * Shared markdown renderer: GFM (tables, strikethrough, task lists),
 * raw HTML, heading [#id] anchors, and optional in-app link navigation.
 */
export function MarkdownBody({ children, navigate }) {
  const content = expandHeadingAnchors(children || '');
  const components = navigate
    ? { a: createMarkdownLinkComponent(navigate) }
    : undefined;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
}
