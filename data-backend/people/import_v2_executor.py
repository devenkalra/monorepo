from people.models import (
    Asset,
    Book,
    Container,
    Entity,
    EntityRelation,
    Location,
    Movie,
    Note,
    Org,
    Person,
    Tag,
)
import logging


logger = logging.getLogger(__name__)


class ImportV2ExecutionError(Exception):
    def __init__(self, message, stats=None):
        super().__init__(message)
        self.stats = stats or {}


ENTITY_MODELS = {
    "Person": Person,
    "Note": Note,
    "Location": Location,
    "Movie": Movie,
    "Book": Book,
    "Container": Container,
    "Asset": Asset,
    "Org": Org,
}

CONTROL_KEYS = {
    "id",
    "import_ref",
    "import_op",
    "type",
    "legacy_id",
    "created_at",
    "updated_at",
    "user",
}


def normalize_legacy_snapshot_to_v2(data):
    """Convert a legacy export snapshot with an entities array into v2 create operations.

    The resulting payload preserves the original graph structure but always restores
    entities as new rows, which is safer than trying to reconcile old UUIDs.
    """
    if data.get("import_version") == "2.0":
        return data

    entities = data.get("entities", []) or []
    if not entities:
        logger.info("normalize_legacy_snapshot_to_v2: no unified entities array found")
        return data

    logger.info(
        "normalize_legacy_snapshot_to_v2: export_version=%s entities=%s relations=%s tags=%s",
        data.get("export_version"),
        len(entities),
        len(data.get("relations", []) or []),
        len(data.get("tags", []) or []),
    )

    normalized = {
        "import_version": "2.0",
        "allow_entity_delete_cascade": True,
        "entities": [],
        "relations": [],
        "tags": [],
    }

    relation_keys_seen = set()

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        original_id = entity.get("id")
        if not original_id:
            continue

        entity_op = {
            "import_op": "create",
            "import_ref": str(original_id),
            "legacy_id": str(original_id),
        }
        for key, value in entity.items():
            if key in CONTROL_KEYS:
                continue
            entity_op[key] = value
        if "type" not in entity_op and entity.get("type"):
            entity_op["type"] = entity["type"]
        normalized["entities"].append(entity_op)

    for relation in data.get("relations", []) or []:
        if not isinstance(relation, dict):
            continue
        from_ref = relation.get("from_entity") or relation.get("source_entity")
        to_ref = relation.get("to_entity") or relation.get("target_entity")
        relation_type = relation.get("relation_type")
        if not (from_ref and to_ref and relation_type):
            continue
        relation_key = (str(from_ref), str(to_ref), str(relation_type))
        if relation_key in relation_keys_seen:
            logger.info(
                "normalize_legacy_snapshot_to_v2: skipping duplicate relation %s -> %s (%s)",
                from_ref,
                to_ref,
                relation_type,
            )
            continue
        relation_keys_seen.add(relation_key)
        normalized["relations"].append(
            {
                "import_op": "create",
                "import_ref": str(relation.get("id") or f"{from_ref}:{to_ref}:{relation_type}"),
                "from_import_ref": str(from_ref),
                "to_import_ref": str(to_ref),
                "relation_type": relation_type,
            }
        )

    for tag in data.get("tags", []) or []:
        if not isinstance(tag, dict):
            continue
        if not tag.get("name"):
            continue
        normalized["tags"].append(
            {
                "import_op": "create",
                "name": tag.get("name"),
                "count": tag.get("count", 0),
            }
        )

    logger.info(
        "normalize_legacy_snapshot_to_v2: produced entities=%s relations=%s tags=%s",
        len(normalized["entities"]),
        len(normalized["relations"]),
        len(normalized["tags"]),
    )

    return normalized


def _clear_value_for_field(field):
    internal_type = field.get_internal_type()
    if internal_type == "JSONField":
        return []
    if internal_type in {"BooleanField", "NullBooleanField"}:
        return False
    if field.null:
        return None
    if internal_type in {"CharField", "TextField"}:
        return ""
    return None


def _iter_mutable_entity_fields(model_cls):
    fields = []
    for field in model_cls._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        if getattr(field, "many_to_many", False):
            continue
        if getattr(field, "auto_created", False):
            continue

        name = field.name
        if name in {"id", "type", "user", "created_at", "updated_at"}:
            continue
        fields.append(field)
    return fields


def _resolve_entity_id(user, entity_id_map, item, id_key, ref_key):
    raw_id = item.get(id_key)
    raw_ref = item.get(ref_key)
    if raw_id:
        entity = Entity.objects.filter(id=raw_id, user=user).first()
        if not entity:
            raise ValueError(f"{id_key} {raw_id} does not exist for user")
        return entity.id
    if raw_ref:
        resolved = entity_id_map.get(raw_ref)
        if not resolved:
            raise ValueError(f"{ref_key} {raw_ref} was not resolved")
        return resolved
    raise ValueError(f"One of {id_key} or {ref_key} is required")


def _validate_unique_import_refs(items, kind):
    refs = [item.get("import_ref") for item in (items or []) if item.get("import_ref")]
    duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
    if duplicates:
        raise ImportV2ExecutionError(
            f"Duplicate {kind} import_ref values found: {', '.join(duplicates)}",
            stats={"errors": [f"Duplicate {kind} import_ref values found: {', '.join(duplicates)}"]},
        )


def execute_import_v2(data, user, check_cancelled=None):
    """Execute import v2 operations and return stats."""

    logger.info(
        "execute_import_v2: user=%s import_version=%s entities=%s relations=%s tags=%s",
        getattr(user, "username", None),
        data.get("import_version"),
        len(data.get("entities", []) or []),
        len(data.get("relations", []) or []),
        len(data.get("tags", []) or []),
    )

    def ensure_not_cancelled():
        if check_cancelled and check_cancelled():
            raise Exception("TASK_CANCELLED_BY_USER")

    stats = {
        "entities_created": 0,
        "entities_updated": 0,
        "entities_replaced": 0,
        "entities_deleted": 0,
        "relations_created": 0,
        "relations_skipped": 0,
        "relations_updated": 0,
        "relations_replaced": 0,
        "relations_deleted": 0,
        "tags_created": 0,
        "tags_updated": 0,
        "tags_deleted": 0,
        "errors": [],
        "warnings": [],
    }

    entity_id_map = {}
    relation_ref_map = {}

    # Entity passes
    entity_ops = data.get("entities", []) or []
    relation_ops = data.get("relations", []) or []

    _validate_unique_import_refs(entity_ops, "entity")
    _validate_unique_import_refs(relation_ops, "relation")

    logger.info(
        "execute_import_v2: starting entity pass create/update/delete counts=%s/%s/%s",
        sum(1 for item in entity_ops if (item.get("import_op") or ("create" if item.get("import_ref") else "update")) == "create"),
        sum(1 for item in entity_ops if (item.get("import_op") or ("create" if item.get("import_ref") else "update")) in {"update", "replace"}),
        sum(1 for item in entity_ops if item.get("import_op") == "delete"),
    )

    # Pass 1: create entities
    for item in entity_ops:
        ensure_not_cancelled()
        op = item.get("import_op")
        if not op:
            op = "create" if item.get("import_ref") else "update"
        if op != "create":
            continue

        entity_type = item.get("type")
        model_cls = ENTITY_MODELS.get(entity_type)
        if not model_cls:
            stats["errors"].append(f"Unknown entity type: {entity_type}")
            continue

        import_ref = item.get("import_ref")
        if import_ref in entity_id_map:
            stats["errors"].append(f"Duplicate entity import_ref: {import_ref}")
            continue

        payload = {k: v for k, v in item.items() if k not in CONTROL_KEYS}
        try:
            legacy_id = item.get("legacy_id")
            if legacy_id:
                existing_entity = model_cls.objects.filter(id=legacy_id, user=user).first()
                if existing_entity:
                    for key, value in payload.items():
                        setattr(existing_entity, key, value)
                    existing_entity.save()
                    entity_id_map[import_ref] = existing_entity.id
                    stats["entities_updated"] += 1
                    continue

            entity = model_cls.objects.create(user=user, **payload)
            entity_id_map[import_ref] = entity.id
            stats["entities_created"] += 1
        except Exception as exc:
            stats["errors"].append(f"Entity create ({import_ref}): {exc}")

    # Pass 2: update/replace entities
    for item in entity_ops:
        ensure_not_cancelled()
        op = item.get("import_op")
        if not op:
            op = "create" if item.get("import_ref") else "update"
        if op not in {"update", "replace"}:
            continue

        entity_id = item.get("id")
        if not entity_id:
            stats["errors"].append(f"Entity {op} requires id")
            continue

        entity = Entity.objects.filter(id=entity_id, user=user).first()
        if not entity:
            stats["errors"].append(f"Entity {op} id not found: {entity_id}")
            continue

        model_cls = ENTITY_MODELS.get(entity.type)
        model_obj = model_cls.objects.filter(id=entity.id, user=user).first()
        if not model_obj:
            stats["errors"].append(f"Entity {op} model not found: {entity_id}")
            continue

        if item.get("type") and item.get("type") != model_obj.type:
            stats["errors"].append(
                f"Entity {op} type mismatch for {entity_id}: {item.get('type')} != {model_obj.type}"
            )
            continue

        payload = {k: v for k, v in item.items() if k not in CONTROL_KEYS}

        try:
            if op == "update":
                for key, value in payload.items():
                    setattr(model_obj, key, value)
                model_obj.save()
                stats["entities_updated"] += 1
            else:
                provided_keys = set(payload.keys())
                for field in _iter_mutable_entity_fields(model_cls):
                    field_name = field.name
                    if field_name in provided_keys:
                        setattr(model_obj, field_name, payload[field_name])
                    else:
                        setattr(model_obj, field_name, _clear_value_for_field(field))
                model_obj.save()
                stats["entities_replaced"] += 1
        except Exception as exc:
            stats["errors"].append(f"Entity {op} ({entity_id}): {exc}")

    # Pass 3: create relations
    relation_keys_seen = set()
    for item in relation_ops:
        ensure_not_cancelled()
        op = item.get("import_op")
        if not op:
            op = "create" if item.get("import_ref") else "update"
        if op != "create":
            continue

        import_ref = item.get("import_ref")
        if import_ref in relation_ref_map:
            stats["errors"].append(f"Duplicate relation import_ref: {import_ref}")
            continue

        try:
            from_id = _resolve_entity_id(user, entity_id_map, item, "from_entity", "from_import_ref")
            to_id = _resolve_entity_id(user, entity_id_map, item, "to_entity", "to_import_ref")
            relation_type = item.get("relation_type")
            relation_key = (str(from_id), str(to_id), str(relation_type))
            if relation_key in relation_keys_seen:
                stats["relations_skipped"] += 1
                logger.info(
                    "execute_import_v2: skipped duplicate relation op %s -> %s (%s)",
                    from_id,
                    to_id,
                    relation_type,
                )
                continue
            relation_keys_seen.add(relation_key)

            relation, created = EntityRelation.objects.get_or_create(
                from_entity_id=from_id,
                to_entity_id=to_id,
                relation_type=relation_type,
            )
            relation_ref_map[import_ref] = relation.id
            if created:
                stats["relations_created"] += 1
            else:
                stats["relations_skipped"] += 1
        except Exception as exc:
            stats["errors"].append(f"Relation create ({import_ref}): {exc}")

    # Pass 4: update/replace relations
    for item in relation_ops:
        ensure_not_cancelled()
        op = item.get("import_op")
        if not op:
            op = "create" if item.get("import_ref") else "update"
        if op not in {"update", "replace"}:
            continue

        relation_id = item.get("id")
        if not relation_id:
            stats["errors"].append(f"Relation {op} requires id")
            continue

        relation = EntityRelation.objects.filter(
            id=relation_id,
            from_entity__user=user,
            to_entity__user=user,
        ).first()
        if not relation:
            stats["errors"].append(f"Relation {op} id not found: {relation_id}")
            continue

        try:
            if op == "replace":
                has_source = item.get("from_entity") or item.get("from_import_ref")
                has_target = item.get("to_entity") or item.get("to_import_ref")
                if not (has_source and has_target and item.get("relation_type")):
                    raise ValueError("Relation replace requires relation_type and both endpoints")

            if "relation_type" in item:
                relation.relation_type = item["relation_type"]

            if "from_entity" in item or "from_import_ref" in item:
                relation.from_entity_id = _resolve_entity_id(user, entity_id_map, item, "from_entity", "from_import_ref")

            if "to_entity" in item or "to_import_ref" in item:
                relation.to_entity_id = _resolve_entity_id(user, entity_id_map, item, "to_entity", "to_import_ref")

            relation.save()
            if op == "replace":
                stats["relations_replaced"] += 1
            else:
                stats["relations_updated"] += 1
        except Exception as exc:
            stats["errors"].append(f"Relation {op} ({relation_id}): {exc}")

    # Pass 5: delete relations
    for item in relation_ops:
        ensure_not_cancelled()
        op = item.get("import_op")
        if op != "delete":
            continue

        relation_id = item.get("id")
        relation = EntityRelation.objects.filter(
            id=relation_id,
            from_entity__user=user,
            to_entity__user=user,
        ).first()
        if not relation:
            stats["warnings"].append(f"Relation delete skipped, id not found: {relation_id}")
            continue

        relation.delete()
        stats["relations_deleted"] += 1

    # Pass 6: delete entities (cascade relations)
    for item in entity_ops:
        ensure_not_cancelled()
        op = item.get("import_op")
        if op != "delete":
            continue

        entity_id = item.get("id")
        entity = Entity.objects.filter(id=entity_id, user=user).first()
        if not entity:
            stats["warnings"].append(f"Entity delete skipped, id not found: {entity_id}")
            continue

        entity.delete()
        stats["entities_deleted"] += 1

    # Optional tag operations
    for item in data.get("tags", []) or []:
        ensure_not_cancelled()
        op = item.get("import_op", "create")
        try:
            if op == "delete":
                tag_qs = Tag.objects.filter(user=user)
                if item.get("id"):
                    tag_qs = tag_qs.filter(id=item["id"])
                elif item.get("name"):
                    tag_qs = tag_qs.filter(name=item["name"])
                else:
                    raise ValueError("Tag delete requires id or name")
                deleted = tag_qs.delete()[0]
                if deleted:
                    stats["tags_deleted"] += deleted
            elif op in {"update", "replace"}:
                if not item.get("id"):
                    raise ValueError("Tag update/replace requires id")
                tag = Tag.objects.filter(id=item["id"], user=user).first()
                if not tag:
                    raise ValueError(f"Tag id not found: {item['id']}")
                if "name" in item:
                    tag.name = item["name"]
                if "count" in item:
                    tag.count = item["count"]
                tag.save()
                stats["tags_updated"] += 1
            else:
                # create/default
                name = item.get("name")
                if not name:
                    raise ValueError("Tag create requires name")
                _, created = Tag.objects.get_or_create(user=user, name=name, defaults={"count": item.get("count", 0)})
                if created:
                    stats["tags_created"] += 1
        except Exception as exc:
            stats["errors"].append(f"Tag {op}: {exc}")

    stats["summary"] = {
        "total_created": stats["entities_created"] + stats["relations_created"] + stats["tags_created"],
        "total_updated": stats["entities_updated"] + stats["entities_replaced"] + stats["relations_updated"] + stats["relations_replaced"] + stats["tags_updated"],
        "total_deleted": stats["entities_deleted"] + stats["relations_deleted"] + stats["tags_deleted"],
        "total_errors": len(stats["errors"]),
        "total_warnings": len(stats["warnings"]),
    }

    # Fail whole import (transaction rollback at caller) if any operation-level error occurred.
    if stats["errors"]:
        logger.error("execute_import_v2: failed with stats=%s", stats)
        raise ImportV2ExecutionError(
            f"Import v2 failed with {len(stats['errors'])} error(s)",
            stats=stats,
        )

    logger.info("execute_import_v2: completed with summary=%s", stats.get("summary"))

    return stats
