from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from .constants import RELATION_SCHEMA, RELATION_MAP, ALL_RELATION_KEYS, RELATION_CHOICES
import uuid

class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=50) # e.g. "Person"
    display = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, default="")
    
    # User ownership - each entity belongs to a user
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='entities', null=True)
    
    # JSON Fields for multiple values
    tags = models.JSONField(default=list, blank=True, null=True)
    urls = models.JSONField(default=list, blank=True, null=True) # Renamed to 'urls' for consistency
    photos = models.JSONField(default=list, blank=True, null=True)
    attachments = models.JSONField(default=list, blank=True, null=True)
    locations = models.JSONField(default=list, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.type:
            self.type = self.__class__.__name__
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.display or 'Entity'} ({self.type})"
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'type']),
            models.Index(fields=['user', 'created_at']),
        ]

class Person(Entity):
    GENDER_CHOICES = (
        ('Unspecified', 'Unspecified'),
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Binary', 'Binary'),
    )

    first_name = models.CharField(max_length=100, null=True)
    last_name = models.CharField(max_length=100, null=True)
    dob = models.DateField(null=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, default='Unspecified', null=True)
    emails = models.JSONField(default=list, null=True)
    phones = models.JSONField(default=list, null=True)
    profession = models.CharField(max_length=255, null=True)

    def save(self, *args, **kwargs):
        if not self.display:
            self.display = f"{self.first_name or ''} {self.last_name or ''}".strip() or "Person"
        super().save(*args, **kwargs)

class Note(Entity):
    date = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.display:
            self.display = (self.description[:50] + '...') if len(self.description) > 50 else (self.description or "Note")
        super().save(*args, **kwargs)

class Location(Entity):
    address1 = models.CharField(max_length=255, null=True, blank=True)
    address2 = models.CharField(max_length=255, null=True, blank=True)
    postal_code = models.CharField(max_length=20, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)

    def save(self, *args, **kwargs):
        # Generate display from address components if not set
        if not self.display:
            parts = []
            if self.address1:
                parts.append(self.address1)
            if self.city:
                parts.append(self.city)
            if self.state:
                parts.append(self.state)
            if self.country:
                parts.append(self.country)
            self.display = ', '.join(parts) if parts else "Location"
        super().save(*args, **kwargs)

class Movie(Entity):
    year = models.IntegerField(null=True, blank=True)
    language = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)

    def save(self, *args, **kwargs):
        # Ensure display is set (can be set manually or use title from description)
        if not self.display:
            self.display = "Untitled Movie"
        super().save(*args, **kwargs)

class Book(Entity):
    year = models.IntegerField(null=True, blank=True)
    language = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    summary = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Ensure display is set (can be set manually or use title from description)
        if not self.display:
            self.display = "Untitled Book"
        super().save(*args, **kwargs)

class Container(Entity):
    # No additional attributes beyond base Entity
    def save(self, *args, **kwargs):
        if not self.display:
            self.display = "Untitled Container"
        super().save(*args, **kwargs)

class Asset(Entity):
    value = models.FloatField(null=True, blank=True)
    acquired_on = models.CharField(max_length=255, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.display:
            self.display = "Untitled Asset"
        super().save(*args, **kwargs)

class Org(Entity):
    KIND_CHOICES = [
        ('School', 'School'),
        ('University', 'University'),
        ('Company', 'Company'),
        ('NonProfit', 'NonProfit'),
        ('Club', 'Club'),
        ('Unspecified', 'Unspecified'),
    ]
    
    name = models.CharField(max_length=255, null=True, blank=True)
    kind = models.CharField(max_length=50, choices=KIND_CHOICES, default='Unspecified', null=True, blank=True)

    def save(self, *args, **kwargs):
        # Use name as display if not set
        if not self.display and self.name:
            self.display = self.name
        elif not self.display:
            self.display = "Untitled Organization"
        super().save(*args, **kwargs)

class EntityRelation(models.Model):
    RELATION_TYPES = RELATION_CHOICES
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_entity = models.ForeignKey(Entity, related_name='relations_from', on_delete=models.CASCADE)
    to_entity = models.ForeignKey(Entity, related_name='relations_to', on_delete=models.CASCADE)
    relation_type = models.CharField(max_length=50, choices=RELATION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('from_entity', 'to_entity', 'relation_type')

    def clean(self):
        # Validate Types
        # For relations with multiple definitions (same key, different entity types),
        # we need to check if ANY of the schemas match
        from .constants import RELATION_SCHEMA
        
        # Find all schemas that match this relation type
        matching_schemas = [
            s for s in RELATION_SCHEMA 
            if s['key'] == self.relation_type or s['reverseKey'] == self.relation_type
        ]
        
        if not matching_schemas:
            return  # Should be handled by choices validation
        
        # Check if any schema matches the actual entity types
        valid = False
        error_messages = []
        
        for schema in matching_schemas:
            # Determine if we're using the forward or reverse direction
            if schema['key'] == self.relation_type:
                expected_from = schema.get('fromEntity')
                expected_to = schema.get('toEntity')
            else:  # reverse direction
                expected_from = schema.get('toEntity')
                expected_to = schema.get('fromEntity')
            
            # Check if this schema matches
            from_matches = (expected_from == '*' or 
                          expected_from == 'ANY' or 
                          self.from_entity.type == expected_from)
            to_matches = (expected_to == '*' or 
                        expected_to == 'ANY' or 
                        self.to_entity.type == expected_to)
            
            if from_matches and to_matches:
                valid = True
                break
            else:
                if not from_matches:
                    error_messages.append(f"must start from {expected_from}, but got {self.from_entity.type}")
                if not to_matches:
                    error_messages.append(f"must end at {expected_to}, but got {self.to_entity.type}")
        
        if not valid and error_messages:
            # Use the first error message
            raise ValidationError(f"Relation '{self.relation_type}' {error_messages[0]}")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        
        # Automatic Reverse Relation Logic
        # For relations with multiple schemas (same key, different entity types),
        # we need to find the specific schema that matches our entity types
        reverse_key = None
        
        # Find the matching schema for this specific relation
        for schema in RELATION_SCHEMA:
            # Check if this is the forward direction
            if schema['key'] == self.relation_type:
                expected_from = schema.get('fromEntity')
                expected_to = schema.get('toEntity')
                
                # Check if this schema matches our entity types
                from_matches = (expected_from == '*' or expected_from == 'ANY' or 
                              self.from_entity.type == expected_from)
                to_matches = (expected_to == '*' or expected_to == 'ANY' or 
                            self.to_entity.type == expected_to)
                
                if from_matches and to_matches:
                    reverse_key = schema['reverseKey']
                    break
            # Check if this is the reverse direction
            elif schema['reverseKey'] == self.relation_type:
                expected_from = schema.get('toEntity')
                expected_to = schema.get('fromEntity')
                
                # Check if this schema matches our entity types
                from_matches = (expected_from == '*' or expected_from == 'ANY' or 
                              self.from_entity.type == expected_from)
                to_matches = (expected_to == '*' or expected_to == 'ANY' or 
                            self.to_entity.type == expected_to)
                
                if from_matches and to_matches:
                    reverse_key = schema['key']
                    break
        
        if reverse_key:
            # check if reverse relation already exists to avoid recursion
            exists = EntityRelation.objects.filter(
                from_entity=self.to_entity,
                to_entity=self.from_entity,
                relation_type=reverse_key
            ).exists()
            
            if not exists:
                # Create reverse relation - this will also validate against the schema
                try:
                    EntityRelation.objects.create(
                        from_entity=self.to_entity,
                        to_entity=self.from_entity,
                        relation_type=reverse_key
                    )
                except ValidationError:
                    # If reverse relation is invalid, just skip it
                    # This can happen with asymmetric relations
                    pass

    def delete(self, *args, **kwargs):
        # Delete reverse relation too for consistency
        # Find the matching schema for this specific relation
        reverse_key = None
        
        for schema in RELATION_SCHEMA:
            # Check if this is the forward direction
            if schema['key'] == self.relation_type:
                expected_from = schema.get('fromEntity')
                expected_to = schema.get('toEntity')
                
                # Check if this schema matches our entity types
                from_matches = (expected_from == '*' or expected_from == 'ANY' or 
                              self.from_entity.type == expected_from)
                to_matches = (expected_to == '*' or expected_to == 'ANY' or 
                            self.to_entity.type == expected_to)
                
                if from_matches and to_matches:
                    reverse_key = schema['reverseKey']
                    break
            # Check if this is the reverse direction
            elif schema['reverseKey'] == self.relation_type:
                expected_from = schema.get('toEntity')
                expected_to = schema.get('fromEntity')
                
                # Check if this schema matches our entity types
                from_matches = (expected_from == '*' or expected_from == 'ANY' or 
                              self.from_entity.type == expected_from)
                to_matches = (expected_to == '*' or expected_to == 'ANY' or 
                            self.to_entity.type == expected_to)
                
                if from_matches and to_matches:
                    reverse_key = schema['key']
                    break

        super().delete(*args, **kwargs)

        if reverse_key:
             EntityRelation.objects.filter(
                from_entity=self.to_entity,
                to_entity=self.from_entity,
                relation_type=reverse_key
            ).delete()

    def __str__(self):
        return f"{self.from_entity} -> {self.relation_type} -> {self.to_entity}"

class Tag(models.Model):
    # Tags are simple strings, e.g. "work", "work/project-a"
    name = models.CharField(max_length=255, primary_key=True)
    count = models.IntegerField(default=0) # Optional: track usage count

    def __str__(self):
        return self.name
