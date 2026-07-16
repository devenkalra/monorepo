import React from 'react';
import { Link } from 'react-router-dom';

export const Breadcrumbs = ({ menuItemId, menuItems, pageTitle, slug }) => {
  if (!menuItemId && (!pageTitle || !slug)) {
    return (
      <div className="breadcrumbs">
        <Link to="/">Home</Link>
      </div>
    );
  }

  // Recursive DFS to find the path to the target menuItemId
  const findPath = (nodes, targetId, path = []) => {
    if (!targetId) return null;
    for (const node of nodes) {
      const currentPath = [...path, node];
      if (node.id === Number(targetId)) {
        return currentPath;
      }
      if (node.children && node.children.length > 0) {
        const found = findPath(node.children, targetId, currentPath);
        if (found) return found;
      }
    }
    return null;
  };

  const trail = menuItems ? findPath(menuItems, menuItemId) : null;
  let finalTrail = trail ? [...trail] : [];

  // If a pageTitle is provided and the active page slug is not already the last item in the trail
  if (pageTitle && slug) {
    const lastNode = finalTrail[finalTrail.length - 1];
    if (!lastNode || lastNode.page_slug !== slug) {
      finalTrail.push({
        id: 'virtual-page',
        title: pageTitle,
        page_slug: slug,
        isVirtual: true
      });
    }
  }

  return (
    <div className="breadcrumbs">
      <Link to="/">Home</Link>
      {finalTrail.map((node, index) => {
        const isLast = index === finalTrail.length - 1;
        const toPath = node.page_slug ? `/p/${node.id}/${node.page_slug}` : (node.external_url || `/p/${node.id}`);

        return (
          <React.Fragment key={node.id}>
            <span className="breadcrumbs-separator">/</span>
            {isLast ? (
              <span className="current">{node.title}</span>
            ) : (
              <Link to={toPath}>{node.title}</Link>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};
