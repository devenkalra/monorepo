RELATION_SCHEMA = [
    # Person Relations
    {
        'key': "IS_CHILD_OF", 
        'name': 'Child Of', 
        'reverseKey': 'IS_PARENT_OF',
        'reverseName': 'Parent Of',
        'relationAnnotation': '', 
        'fromEntity': 'Person', # Implied by context but explicit here for clarity
        'toEntity': 'Person',
        'toSemantics': 'Person'
    },
    {
        'key': 'IS_FRIEND_OF', 
        'name': 'Friend Of', 
        'reverseKey': 'IS_FRIEND_OF', 
        'reverseName': 'Friend Of',
        'relationAnnotation': '', 
        'fromEntity': 'Person',
        'toEntity': 'Person', 
        'toSemantics': 'Person'
    },
    {
        'key': 'IS_COLLEAGUE_OF', 
        'name': 'Colleague Of', 
        'reverseKey': 'IS_COLLEAGUE_OF',
        'reverseName': 'Colleague Of',
        'relationAnnotation': '', 
        'fromEntity': 'Person',
        'toEntity': 'Person', 
        'toSemantics': 'Person'
    },
    {
        'key': 'IS_SPOUSE_OF', 
        'name': 'Spouse Of', 
        'reverseKey': 'IS_SPOUSE_OF', 
        'reverseName': 'Spouse Of',
        'relationAnnotation': '', 
        'fromEntity': 'Person',
        'toEntity': 'Person', 
        'toSemantics': 'Person'
    },
    {
        'key': 'IS_MANAGER_OF', 
        'name': 'Manager Of', 
        'reverseKey': 'WORKS_FOR_MGR',
        'reverseName': 'Works For',
        'relationAnnotation': '', 
        'fromEntity': 'Person',
        'toEntity': 'Person', 
        'toSemantics': 'Person'
    },
    {
        'key': 'IS_STUDENT_OF', 
        'name': 'Student Of', 
        'reverseKey': 'IS_TEACHER_OF',
        'reverseName': 'Teacher Of', 
        'relationAnnotation': 'Teacher',
        'fromEntity': 'Person',
        'toEntity': 'Person', 
        'toSemantics': 'Teacher'
    },
    {
        'key': 'HAS_STUDENT', 
        'name': 'Has Student', 
        'reverseKey': 'IS_STUDENT_OF',
        'reverseName': 'Student Of', 
        'relationAnnotation': 'Person',
        'fromEntity': 'Person',
        'toEntity': 'Person', 
        'toSemantics': 'Person'
    },
    {
        'key': 'IS_STUDENT_OF', 
        'name': 'Student Of (Org)', 
        'reverseKey': 'HAS_STUDENT',
        'reverseName': 'Has Student', 
        'relationAnnotation': 'Org',
        'fromEntity': 'Person',
        'toEntity': 'Org', 
        'toSemantics': 'Org'
    },
    # Note Relations - Note can relate to any entity type, and any entity can relate to Note
    {
        'key': 'IS_RELATED_TO', 
        'name': 'Related To', 
        'reverseKey': 'IS_RELATED_TO',
        'reverseName': 'Related To', 
        'relationAnnotation': '', 
        'fromEntity': '*',  # Any entity type can use this relation
        'toEntity': '*',  # Can relate to any entity type
        'toSemantics': 'Entity'
    },
    # Location Relations
    {
        'key': 'LIVES_AT',
        'name': 'Lives At',
        'reverseKey': 'HAS_RESIDENT',
        'reverseName': 'Has Resident',
        'relationAnnotation': '',
        'fromEntity': 'Person',
        'toEntity': 'Location',
        'toSemantics': 'Location'
    },
    {
        'key': 'IS_LOCATED_IN',
        'name': 'Located In',
        'reverseKey': 'CONTAINS',
        'reverseName': 'Contains',
        'relationAnnotation': '',
        'fromEntity': 'Location',
        'toEntity': 'Location',
        'toSemantics': 'Location'
    },
    # Movie Relations
    {
        'key': 'HAS_ACTOR',
        'name': 'Actor',
        'reverseKey': 'ACTED_IN',
        'reverseName': 'Acted In',
        'relationAnnotation': '',
        'fromEntity': 'Movie',
        'toEntity': 'Person',
        'toSemantics': 'Person'
    },
    {
        'key': 'HAS_DIRECTOR',
        'name': 'Director',
        'reverseKey': 'DIRECTED',
        'reverseName': 'Directed',
        'relationAnnotation': '',
        'fromEntity': 'Movie',
        'toEntity': 'Person',
        'toSemantics': 'Person'
    },
    {
        'key': 'HAS_MUS_DIRECTOR',
        'name': 'Music Director',
        'reverseKey': 'GAVE_MUSIC_TO',
        'reverseName': 'Gave Music',
        'relationAnnotation': '',
        'fromEntity': 'Movie',
        'toEntity': 'Person',
        'toSemantics': 'Person'
    },
    # Book Relations
    {
        'key': 'INSPIRED',
        'name': 'Inspired',
        'reverseKey': 'IS_BASED_ON',
        'reverseName': 'Based On',
        'relationAnnotation': '',
        'fromEntity': 'Book',
        'toEntity': 'Movie',
        'toSemantics': 'Movie'
    },
    {
        'key': 'HAS_AS_AUTHOR',
        'name': 'Has Author',
        'reverseKey': 'IS_AUTHOR_OF',
        'reverseName': 'Author',
        'relationAnnotation': '',
        'fromEntity': 'Book',
        'toEntity': 'Person',
        'toSemantics': 'Person'
    },
    {
        'key': 'IS_LOCATED_IN',
        'name': 'Located In',
        'reverseKey': 'IS_LOCATION_OF',
        'reverseName': 'Location of',
        'relationAnnotation': '',
        'fromEntity': 'Book',
        'toEntity': 'Location',
        'toSemantics': 'Location'
    },
    # Container Relations
    {
        'key': 'IS_CONTAINED_IN',
        'name': 'Contained In',
        'reverseKey': 'CONTAINS',
        'reverseName': 'Contains',
        'relationAnnotation': 'Container',
        'fromEntity': 'Container',
        'toEntity': 'Container',
        'toSemantics': 'Container'
    },
    {
        'key': 'IS_LOCATED_IN',
        'name': 'Located In',
        'reverseKey': 'CONTAINS',
        'reverseName': 'Contains',
        'relationAnnotation': 'Container',
        'fromEntity': 'Container',
        'toEntity': 'Location',
        'toSemantics': 'Location'
    },
    # Asset Relations
    {
        'key': 'IS_LOCATED_IN',
        'name': 'Contained In',
        'reverseKey': 'CONTAINS',
        'reverseName': 'Contains',
        'relationAnnotation': 'Asset',
        'fromEntity': 'Asset',
        'toEntity': 'Container',
        'toSemantics': 'Container'
    },
    # Org Relations
    {
        'key': 'IS_LOCATED_AT',
        'name': 'Located At',
        'reverseKey': 'HAS',
        'reverseName': 'Has Org At',
        'relationAnnotation': '',
        'fromEntity': 'Org',
        'toEntity': 'Location',
        'toSemantics': 'Location'
    },
    {
        'key': 'HAS_EMPLOYEE',
        'name': 'Has Employee',
        'reverseKey': 'WORKS_AT',
        'reverseName': 'Works At',
        'relationAnnotation': '',
        'fromEntity': 'Org',
        'toEntity': 'Person',
        'toSemantics': 'Person'
    },
    {
        'key': 'HAS_MEMBER',
        'name': 'Has Member',
        'reverseKey': 'IS_MEMBER_OF',
        'reverseName': 'Member Of',
        'relationAnnotation': '',
        'fromEntity': 'Org',
        'toEntity': 'Person',
        'toSemantics': 'Person'
    },
    {
        'key': 'HAS_STUDENT',
        'name': 'Has Student',
        'reverseKey': 'STUDIES_AT',
        'reverseName': 'Student Of',
        'relationAnnotation': 'Org',
        'fromEntity': 'Org',
        'toEntity': 'Person',
        'toSemantics': 'Person'
    }
]

# Helper to look up allowed relations by key
RELATION_MAP = { item['key']: item for item in RELATION_SCHEMA }

# Also map reverse keys so we can validate those too if created directly? 
# or do we treat reverse keys as first-class keys?
# The user provided a list where `reverseKey` is distinct.
# If I create an "IS_PARENT_OF" relation directly, is that allowed?
# The list above defines the "primary" direction. 
# BUT `IS_PARENT_OF` effectively becomes a valid key in the system if the reverse relation is created.
# So we should probably treat all keys (forward and reverse) as valid choices.

ALL_RELATION_KEYS = {}
for item in RELATION_SCHEMA:
    # Forward
    ALL_RELATION_KEYS[item['key']] = {
        'toEntity': item['toEntity'],
        'fromEntity': item.get('fromEntity', 'Person') # Defaulting to Person based on context if missing, but I added it.
    }
    # Reverse - we must construct the reverse rule.
    # If A -> IS_CHILD_OF -> B (Person -> Person),
    # Then B -> IS_PARENT_OF -> A (Person -> Person)
    ALL_RELATION_KEYS[item['reverseKey']] = {
        'toEntity': item.get('fromEntity', 'Person'),
        'fromEntity': item['toEntity']
    }

RELATION_CHOICES = [
    (key, key.replace('_', ' ').title()) for key in ALL_RELATION_KEYS.keys()
]
