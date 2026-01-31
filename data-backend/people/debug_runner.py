import time
from django.test import LiveServerTestCase
from unittest.mock import patch
from .models import Person, Note, EntityRelation

class ShakespeareLiveDebug(LiveServerTestCase):
    """
    Runs a live server with Shakespeare data.
    Pauses execution so you can inspect via API.
    """
    
    def start_patches(self):
        self.neo4j_patcher = patch('people.signals.neo4j_sync')
        self.meili_patcher = patch('people.signals.meili_sync')
        self.mock_neo4j = self.neo4j_patcher.start()
        self.mock_meili = self.meili_patcher.start()
        self.addCleanup(self.neo4j_patcher.stop)
        self.addCleanup(self.meili_patcher.stop)

    def setUp(self):
        self.start_patches()
        
        # Create Shakespeare Data
        self.william = Person.objects.create(first_name="William", last_name="Shakespeare", gender="Male", profession="Playwright")
        self.anne = Person.objects.create(first_name="Anne", last_name="Hathaway", gender="Female")
        self.susanna = Person.objects.create(first_name="Susanna", last_name="Hall", gender="Female")
        self.hamnet = Person.objects.create(first_name="Hamnet", last_name="Shakespeare", gender="Male")
        self.judith = Person.objects.create(first_name="Judith", last_name="Quiney", gender="Female")
        
        self.hamlet = Note.objects.create(description="Hamlet - A Tragedy", tags=["Tragedy", "Play"])
        self.romeo = Note.objects.create(description="Romeo and Juliet", tags=["Tragedy", "Romance"])
        
        # Relations
        EntityRelation.objects.create(from_entity=self.william, to_entity=self.anne, relation_type='IS_SPOUSE_OF')
        
        for child in [self.susanna, self.hamnet, self.judith]:
            EntityRelation.objects.create(from_entity=child, to_entity=self.william, relation_type='IS_CHILD_OF')

    def test_debug_server(self):
        print(f"\n\n!!! DEBUG SERVER RUNNING !!!")
        print(f"Base URL: {self.live_server_url}")
        print(f"Entities: {self.live_server_url}/api/entities/")
        print(f"People:   {self.live_server_url}/api/people/")
        print(f"William:  {self.live_server_url}/api/people/{self.william.id}/?include_relations=true")
        print("\nThe test is PAUSED. You can query the API above.")
        print("Press Ctrl+C to stop (or wait 60 seconds)...")
        
        # Sleep to keep server alive. Using sleep instead of input() to work better in some runners, 
        # but input() is also fine if running interactively. 
        # For safety in this environment, I'll use a finite sleep, but usually input() is preferred.
        try:
            time.sleep(60) 
        except KeyboardInterrupt:
            pass
