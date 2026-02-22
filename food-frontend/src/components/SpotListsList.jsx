import React from 'react';
import ListsList from './ListsList';

export default function SpotListsList({ apiBase }) {
  return (
    <ListsList
      apiBase={apiBase}
      type="spot"
      title="Spot Lists"
      createPath="/spot-lists/create"
      detailPath="/spot-lists"
      countLabel="spots"
    />
  );
}
