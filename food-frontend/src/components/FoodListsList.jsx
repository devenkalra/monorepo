import React from 'react';
import ListsList from './ListsList';

export default function FoodListsList({ apiBase }) {
  return (
    <ListsList
      apiBase={apiBase}
      type="food"
      title="Food Lists"
      createPath="/food-lists/create"
      detailPath="/food-lists"
      countLabel="foods"
    />
  );
}
