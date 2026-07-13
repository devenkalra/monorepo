# Entity Import Format Specification

## Version
- Spec version: 2.0
- File marker: `import_version: "2.0"`

This format is operation-based and supports create, update, replace, and delete for entities and relations.

## Goals
- Support deterministic upsert and delete behavior.
- Allow creating related objects in one file using temporary references.
- Keep backward compatibility with legacy snapshot imports (`export_version` payloads).

## Identity Rules
- Existing records are identified by `id` (UUID).
- New records are identified by `import_ref`.
- `id` and `import_ref` are mutually exclusive in one operation object.
- If `id` exists, `import_ref` must not be present.
- If `import_ref` exists, `id` must not be present.

## Operation Field
`import_op` values:
- `create`
- `update`
- `replace`
- `delete`

Default behavior when `import_op` is missing:
- If `id` is present: treat as `update`.
- If `import_ref` is present: treat as `create`.

## Entity Operations
### `create`
- Required: `import_ref`, `type`
- Must not contain `id`
- Creates a new entity and maps `import_ref` to the generated UUID.

### `update`
- Required: `id`
- Partial update semantics.
- Only specified fields are updated.
- Unspecified fields remain unchanged.

### `replace`
- Required: `id`
- Replace semantics.
- Specified fields are set.
- Unspecified mutable fields are cleared (null/empty/default according to model constraints).

### `delete`
- Required: `id`
- Deletes the entity.
- Entity delete is cascade-by-design: all relations where the entity is source or target are deleted.

## Relation Operations
### `create`
- Required: `import_ref`, `relation_type`
- Must define both endpoints, each by either UUID or import reference:
  - source endpoint: `from_entity` or `from_import_ref`
  - target endpoint: `to_entity` or `to_import_ref`

### `update`
- Required: `id`
- Partial update semantics for relation fields.

### `replace`
- Required: `id`
- Replace semantics for relation fields.

### `delete`
- Required: `id`
- Deletes that relation.

## Ordering and Execution
Recommended processing order in one transaction:
1. Entity `create`
2. Entity `update` and `replace`
3. Relation `create`
4. Relation `update` and `replace`
5. Relation `delete`
6. Entity `delete` (cascade relations)

## Validation Rules
- Validate payload against `people/import.schema.json` before any DB writes.
- Validation is the first semantic check after JSON parsing.
- Reject invalid payloads with a 400 response including the first schema error path and message.

## Backward Compatibility
- Legacy snapshot import files (with `export_version`) remain accepted.
- New operation-based format uses `import_version: "2.0"`.

## Example (v2)
```json
{
  "import_version": "2.0",
  "allow_entity_delete_cascade": true,
  "entities": [
    {
      "import_op": "create",
      "import_ref": "new-person-1",
      "type": "Person",
      "display": "New Person"
    },
    {
      "import_op": "update",
      "id": "35ea6ad4-b0db-45f6-895d-14a80fe9aafa",
      "display": "Updated Display"
    },
    {
      "import_op": "replace",
      "id": "56b1f094-bb92-473b-ba50-3fc8f4e76567",
      "type": "Person",
      "display": "Replacement"
    },
    {
      "import_op": "delete",
      "id": "a6f1a9fc-f51f-4d7e-8f43-bddae5816826"
    }
  ],
  "relations": [
    {
      "import_op": "create",
      "import_ref": "new-rel-1",
      "from_import_ref": "new-person-1",
      "to_entity": "fa7bfb91-9e94-4af6-bbc3-c81d00d85e67",
      "relation_type": "IS_CHILD_OF"
    },
    {
      "import_op": "delete",
      "id": "b44a00d2-2a3d-4c22-adc7-44b8a80b0d12"
    }
  ]
}
```
