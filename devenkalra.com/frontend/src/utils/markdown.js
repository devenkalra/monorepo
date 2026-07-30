import { createElement } from 'react';

/**
 * Turn heading suffixes like `## Title [#slug]` into real anchors:
 * `## <a id="slug" href="#slug">Title</a>`
 *
 * CommonMark leaves `[#slug]` as literal text; this is an explicit id/link convention.
 */
export function expandHeadingAnchors(markdown) {
  if (!markdown) return markdown;
  return markdown.replace(
    /^(#{1,6})\s+(.+?)\s+\[#([A-Za-z0-9_-]+)\][ \t]*\r?$/gm,
    (_, hashes, title, id) => `${hashes} <a id="${id}" href="#${id}">${title}</a>`
  );
}

/**
 * Shared ReactMarkdown `components.a` behavior for in-app navigation.
 * Hash links stay on-page; absolute http(s) open in a new tab; other paths use navigate().
 */
export function createMarkdownLinkComponent(navigate) {
  return function MarkdownLink({ href, children, ...props }) {
    if (!href) {
      return createElement('a', props, children);
    }

    if (href.startsWith('#')) {
      return createElement('a', { href, ...props }, children);
    }

    const isExternal =
      href.startsWith('http://') ||
      href.startsWith('https://') ||
      href.startsWith('//') ||
      href.startsWith('mailto:') ||
      href.startsWith('tel:');

    if (isExternal) {
      return createElement(
        'a',
        { href, target: '_blank', rel: 'noopener noreferrer', ...props },
        children
      );
    }

    return createElement(
      'a',
      {
        href,
        onClick: (e) => {
          e.preventDefault();
          if (!navigate) return;
          if (href.startsWith('/')) {
            navigate(href);
            return;
          }
          const currentPath = window.location.pathname;
          const cleanPath = currentPath.endsWith('/') ? currentPath.slice(0, -1) : currentPath;
          const cleanUrl = href.startsWith('./') ? href.slice(2) : href;
          const segments = cleanPath.split('/');
          segments.pop();
          segments.push(cleanUrl);
          navigate(segments.join('/'));
        },
        ...props,
      },
      children
    );
  };
}
