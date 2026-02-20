"""
Rebuild Neo4j graph from PostgreSQL. Use after restore when Neo4j was not backed up.
All entities and relations are in PostgreSQL; this syncs them to Neo4j.
"""
from django.core.management.base import BaseCommand
from people.models import Entity, EntityRelation
from people.sync import neo4j_sync


class Command(BaseCommand):
    help = 'Rebuild Neo4j from PostgreSQL. Clears Neo4j and syncs all entities and relations.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-clear',
            action='store_true',
            help='Do not clear Neo4j before syncing (default: clear first)',
        )

    def handle(self, *args, **options):
        if not neo4j_sync._driver:
            self.stdout.write(self.style.ERROR('Neo4j not configured or unavailable'))
            return

        if not options.get('no_clear', False):
            self.stdout.write('Clearing Neo4j...')
            try:
                with neo4j_sync._driver.session() as session:
                    session.run('MATCH (n) DETACH DELETE n')
                self.stdout.write(self.style.SUCCESS('  Neo4j cleared'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Could not clear: {e}'))

        entities = Entity.objects.all()
        total = entities.count()
        self.stdout.write(f'Syncing {total} entities to Neo4j...')

        for i, entity in enumerate(entities, 1):
            try:
                neo4j_sync.sync_entity(entity)
                if i % 50 == 0:
                    self.stdout.write(f'  Entities: {i}/{total}...')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error syncing entity {entity.id}: {e}'))

        relations = EntityRelation.objects.all()
        rel_count = relations.count()
        self.stdout.write(f'Syncing {rel_count} relations...')

        for i, rel in enumerate(relations, 1):
            try:
                neo4j_sync.sync_relation(
                    rel.from_entity.id, rel.to_entity.id, rel.relation_type
                )
                if i % 50 == 0:
                    self.stdout.write(f'  Relations: {i}/{rel_count}...')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error syncing relation: {e}'))

        self.stdout.write(self.style.SUCCESS(f'✓ Neo4j synced: {total} entities, {rel_count} relations'))
