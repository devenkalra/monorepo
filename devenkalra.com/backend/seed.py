import os
# pyrefly: ignore [missing-import]
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Page, MenuItem, Project, WorkflowIdea, BookReview, MusicTrack, Recipe

def load_seed_page(slug, default_content):
    """Helper to load page content from seed_data/ if available, otherwise return default."""
    seed_path = os.path.join(os.path.dirname(__file__), 'seed_data', f'{slug}.html')
    if os.path.exists(seed_path):
        try:
            with open(seed_path, 'r', encoding='utf-8') as f:
                return f.read(), True
        except Exception as e:
            print(f"Error reading seed file for {slug}: {e}")
    return default_content, False

def seed_db():
    print("Starting database seeding (non-destructive)...")

    print("Seeding superusers...")
    admin_user, _ = User.objects.get_or_create(username='admin', defaults={
        'email': 'admin@devenkalra.com'
    })
    if _:
        admin_user.set_password('password123')
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.save()

    deven_user, _ = User.objects.get_or_create(username='deven', defaults={
        'email': 'deven@devenkalra.com'
    })
    if _:
        deven_user.set_password('password123')
        deven_user.is_superuser = True
        deven_user.is_staff = True
        deven_user.save()

    print("Seeding content pages...")
    
    # 1. Who Am I
    p_who, _ = Page.objects.update_or_create(
        slug="who-am-i",
        defaults={
            "title": "Who Am I?",
            "content": """# Who Am I?

I am an (early retired) engineering executive being fortunate for having worked on a number of cutting edge and high impact technologies at companies like **Hewlett-Packard**, **Adaptive Media/Vuent**, **Langoo**, **VeriSign**, **Stratify/Iron Mountain**, **AtHoc** and **Google**.

I am interested in many things including photography, writing, woodworking, traveling and more! In this site I share a few of my interests and creations. 

Feel free to browse around!
""",
            "is_protected": False
        }
    )

    # 2. Professional Life
    p_prof, _ = Page.objects.update_or_create(
        slug="professional-life",
        defaults={
            "title": "Professional Life",
            "content": """# Professional Life

An overview of my professional career, engineering leadership roles, and technical contributions over the years.

## Career Timeline

### Google — Engineering Director
*Led engineering teams working on planetary-scale infrastructure and developer tools.*

### AtHoc — VP of Engineering
*Scaled the engineering organization and drove the technology strategy for crisis communication platforms (acquired by BlackBerry).*

### Stratify / Iron Mountain — VP of Engineering
*Managed software development for enterprise e-discovery platforms.*

### VeriSign — Director of Engineering
*Architected registry and security infrastructure.*

### Adaptive Media / Vuent — Founding Engineer
*Developed rich media streaming and graphics rendering technologies.*

### Hewlett-Packard — Member of Technical Staff
*Contributed to operating system kernels and systems performance.*
""",
            "is_protected": False
        }
    )

    # 3. Video Transcripts
    p_transcripts, _ = Page.objects.update_or_create(
        slug="video-transcripts",
        defaults={
            "title": "Video Transcripts",
            "content": """# Video Transcripts

Below you will find fully indexed and searchable transcripts of my talks, lectures, and interviews.

* [2024 Tech Summit: Scalable Engineering Teams](/p/video-transcripts#tech-summit-2024)
* [2022 Interview: Transitioning from Code to Management](/p/video-transcripts#interview-2022)
""",
            "is_protected": False
        }
    )

    # 4. Technical Papers
    p_papers, _ = Page.objects.update_or_create(
        slug="technical-papers",
        defaults={
            "title": "Technical Papers",
            "content": """# Technical Papers

A collection of technical papers, patents, and articles I have written or co-authored during my career.

* **Distributed State Management in Low-Latency Systems (2018)** — *Explores architectural patterns for maintaining high availability in geo-distributed microservices.*
* **Metadata Extraction Frameworks for Large Scale E-Discovery (2010)** — *Discusses indexing structures for petabyte-scale document stores.*
""",
            "is_protected": False
        }
    )

    # 5. Book Summaries
    p_book_summaries_content = """# Book Summaries

My detailed notes, mind maps, and core takeaways from books I read. I update these summaries to solidify my learning and share key ideas.

## Featured Summaries
* **[Rich Dad Poor Dad](./rich-dad-poor-dad)** — *A summary of Robert Kiyosaki's classic book on financial education.*"""

    # Check if we have Die With Zero and Thinking Fast and Slow on disk/database to include them in index
    has_dwz = os.path.exists(os.path.join(os.path.dirname(__file__), 'seed_data', 'die-with-zero.html'))
    has_tfs = os.path.exists(os.path.join(os.path.dirname(__file__), 'seed_data', 'thinking-fast-and-slow.html'))
    
    if has_dwz or Page.objects.filter(slug="die-with-zero").exists():
        p_book_summaries_content += "\n* **[Die With Zero](./die-with-zero)** — *Die with Zero.*"
    if has_tfs or Page.objects.filter(slug="thinking-fast-and-slow").exists():
        p_book_summaries_content += "\n* **[Thinking Fast and Slow](./thinking-fast-and-slow)** — *Die with Zero.*"

    p_book_summaries, _ = Page.objects.update_or_create(
        slug="book-summaries",
        defaults={
            "title": "Book Summaries",
            "content": p_book_summaries_content,
            "is_protected": False
        }
    )

    # 5b. Rich Dad Poor Dad
    p_rich_dad, _ = Page.objects.update_or_create(
        slug="rich-dad-poor-dad",
        defaults={
            "title": "Rich Dad Poor Dad",
            "content": """# Rich Dad Poor Dad - Book Summary

By Robert T. Kiyosaki.

## Core Takeaways
1. **The Rich Don't Work for Money**: The poor and the middle class work for money. The rich have money work for them.
2. **Financial Literacy**: It's not how much money you make. It's how much money you keep.
3. **Mind Your Own Business**: The rich focus on their asset columns while everyone else focuses on their income statements.
4. **The Power of Corporations**: A corporation can do things an individual cannot, like pay expenses before paying taxes.
""",
            "is_protected": False
        }
    )

    # 6. Book Lists and Reviews
    p_book_reviews, _ = Page.objects.update_or_create(
        slug="book-reviews",
        defaults={
            "title": "Book Lists & Reviews",
            "content": """# Book Lists & Reviews

Here is a live database of books I have read, along with my ratings, reviews, and short summaries. You can find technical literature, history, philosophy, and fiction.
""",
            "is_protected": False
        }
    )

    # 7. Indian Music
    p_music, _ = Page.objects.update_or_create(
        slug="indian-music",
        defaults={
            "title": "Indian Music",
            "content": """# Indian Music

My exploration of Hindustani Classical Music. I collect recordings, document raga scales (arohana/avarohana), and write short notes on different bandishes and compositions.
""",
            "is_protected": False
        }
    )

    # 8. Cooking - Snacks
    p_cooking, _ = Page.objects.update_or_create(
        slug="cooking-snacks",
        defaults={
            "title": "Cooking (Snacks)",
            "content": """# Cooking: Snacks & Savories

A collection of recipes for high-quality tea-time snacks, quick bites, and regional Indian delicacies. Woodworking and coding always pair well with a warm cup of masala chai and fresh pakoras!
""",
            "is_protected": False
        }
    )

    # 9. Track Ideas (Protected)
    p_ideas, _ = Page.objects.update_or_create(
        slug="track-ideas",
        defaults={
            "title": "Track Ideas",
            "content": """# Workflow Ideas Board

> [!NOTE]
> This page is password protected as it contains personal logs, pending patents, and early-stage project brainstorming.

Here is a list of active concepts, side projects, and writing topics I am currently tracking.
""",
            "is_protected": True
        }
    )

    # 10. Highschool Photography (Protected)
    p_photo, _ = Page.objects.update_or_create(
        slug="highschool-photography",
        defaults={
            "title": "Highschool Photography",
            "content": """# Ongoing Project: Highschool Photography

> [!NOTE]
> This page is password protected.

A project tracking my photography mentoring, highschool portfolios, and camera equipment tests. I share galleries and technical notes on lenses, exposure, and editing workflows.
""",
            "is_protected": True
        }
    )

    # 11. Video AI Internships (Protected)
    p_video_ai, _ = Page.objects.update_or_create(
        slug="video-ai-internships",
        defaults={
            "title": "Video AI Internships",
            "content": """# Ongoing Project: Video AI Internships

> [!NOTE]
> This page is password protected.

Log of my research and coaching for Video AI internships. Tracks candidate progress, interview prep materials, project suggestions, and coding challenges in deep learning and video processing.
""",
            "is_protected": True
        }
    )

    # 12. Time Keeping Widget
    p_time_keeper, _ = Page.objects.update_or_create(
        slug="time-keeper",
        defaults={
            "title": "Time Keeping Widget",
            "content": """# Time Keeping Widget
This page hosts a high-end timekeeping dashboard featuring a local Clock, a World Clock with multiple timezones, a Stopwatch, and a countdown Timer.

The widgets feature circular progress visualizers that let you see values from far away, complete with sub-dials showing adjustable temporal resolutions.
""",
            "is_protected": False
        }
    )

    # SEED RESTORED CUSTOM PAGES (if files exist on disk)
    knee_html, has_knee = load_seed_page('knee-exercises', '')
    if has_knee:
        p_knee, _ = Page.objects.update_or_create(
            slug="knee-exercises",
            defaults={"title": "Knee Exercises", "content": knee_html, "render_as_html": True, "is_protected": False}
        )
        print("Seeded Knee Exercises page from seed_data.")

    dwz_html, has_dwz_page = load_seed_page('die-with-zero', '')
    if has_dwz_page:
        p_dwz, _ = Page.objects.update_or_create(
            slug="die-with-zero",
            defaults={"title": "Die With Zero", "content": dwz_html, "render_as_html": True, "is_protected": False}
        )
        print("Seeded Die With Zero page from seed_data.")

    tfs_html, has_tfs_page = load_seed_page('thinking-fast-and-slow', '')
    if has_tfs_page:
        p_tfs, _ = Page.objects.update_or_create(
            slug="thinking-fast-and-slow",
            defaults={"title": "Thinking Fast and Slow", "content": tfs_html, "render_as_html": True, "is_protected": False}
        )
        print("Seeded Thinking Fast and Slow page from seed_data.")

    ideas_html, has_ideas_page = load_seed_page('ideas', '')
    if has_ideas_page:
        p_ideas_custom, _ = Page.objects.update_or_create(
            slug="ideas",
            defaults={"title": "Ideas", "content": ideas_html, "render_as_html": True, "is_protected": False}
        )
        print("Seeded Ideas custom page from seed_data.")

    print("Creating navigation menu structure...")
    
    # Root level menu items
    m_who, _ = MenuItem.objects.get_or_create(title="Who Am I?", defaults={'page': p_who, 'order': 1})
    m_prof, _ = MenuItem.objects.get_or_create(title="Professional Life", defaults={'page': p_prof, 'order': 2})
    m_personal, _ = MenuItem.objects.get_or_create(title="Personal Life", defaults={'page': None, 'order': 3})

    # Personal Life submenus
    m_content, _ = MenuItem.objects.get_or_create(title="Content", parent=m_personal, defaults={'page': None, 'order': 1})
    m_workflow, _ = MenuItem.objects.get_or_create(title="Workflow", parent=m_personal, defaults={'page': None, 'order': 2})

    # Content submenus
    MenuItem.objects.get_or_create(title="Video Transcripts", parent=m_content, defaults={'page': p_transcripts, 'order': 1})
    MenuItem.objects.get_or_create(title="Technical Papers", parent=m_content, defaults={'page': p_papers, 'order': 2})
    m_book_sums, _ = MenuItem.objects.get_or_create(title="Book Summaries", parent=m_content, defaults={'page': p_book_summaries, 'order': 3})
    MenuItem.objects.get_or_create(title="Rich Dad Poor Dad", parent=m_book_sums, defaults={'page': p_rich_dad, 'order': 1, 'show_in_menu': False})
    
    # Wire Die With Zero and Thinking Fast and Slow to Book Summaries (hidden) if they exist
    if has_dwz_page or Page.objects.filter(slug="die-with-zero").exists():
        p_dwz_db = Page.objects.get(slug="die-with-zero")
        MenuItem.objects.get_or_create(title="Die With Zero", parent=m_book_sums, defaults={'page': p_dwz_db, 'order': 2, 'show_in_menu': False})
    if has_tfs_page or Page.objects.filter(slug="thinking-fast-and-slow").exists():
        p_tfs_db = Page.objects.get(slug="thinking-fast-and-slow")
        MenuItem.objects.get_or_create(title="Thinking Fast and Slow", parent=m_book_sums, defaults={'page': p_tfs_db, 'order': 3, 'show_in_menu': False})

    MenuItem.objects.get_or_create(title="Book Lists and Reviews", parent=m_content, defaults={'page': p_book_reviews, 'order': 4})
    MenuItem.objects.get_or_create(title="Indian Music", parent=m_content, defaults={'page': p_music, 'order': 5})
    
    m_cooking, _ = MenuItem.objects.get_or_create(title="Cooking", parent=m_content, defaults={'page': None, 'order': 6})
    MenuItem.objects.get_or_create(title="Snacks", parent=m_cooking, defaults={'page': p_cooking, 'order': 1})

    # Wire Exercise & Knee Exercises if they exist
    if has_knee or Page.objects.filter(slug="knee-exercises").exists():
        p_knee_db = Page.objects.get(slug="knee-exercises")
        m_exercise, _ = MenuItem.objects.get_or_create(title="Exercise", parent=m_content, defaults={'order': 7})
        MenuItem.objects.get_or_create(title="Knee Exercises", parent=m_exercise, defaults={'page': p_knee_db, 'order': 1, 'show_in_menu': True})

    # Wire Ideas menu item if it exists
    if has_ideas_page or Page.objects.filter(slug="ideas").exists():
        p_ideas_db = Page.objects.get(slug="ideas")
        m_ideas_cat, _ = MenuItem.objects.get_or_create(title="Ideas", parent=m_content, defaults={'order': 8})
        MenuItem.objects.get_or_create(title="Ideas", parent=m_ideas_cat, defaults={'page': p_ideas_db, 'order': 1, 'show_in_menu': True})

    # Workflow submenus
    MenuItem.objects.get_or_create(title="Track Ideas", parent=m_workflow, defaults={'page': p_ideas, 'order': 1})
    m_ongoing, _ = MenuItem.objects.get_or_create(title="Ongoing Projects", parent=m_workflow, defaults={'page': None, 'order': 2})

    # Ongoing Projects submenus
    MenuItem.objects.get_or_create(title="Highschool Photography", parent=m_ongoing, defaults={'page': p_photo, 'order': 1})
    MenuItem.objects.get_or_create(title="Video AI Internships", parent=m_ongoing, defaults={'page': p_video_ai, 'order': 2})

    # Multi-mapped links
    MenuItem.objects.get_or_create(title="Photography Projects", parent=m_personal, defaults={'page': p_photo, 'order': 3})
    MenuItem.objects.get_or_create(title="AI Tech Internships", parent=m_prof, defaults={'page': p_video_ai, 'order': 1})

    # Custom Apps category under Personal Life
    m_custom_apps, _ = MenuItem.objects.get_or_create(title="Custom Apps", parent=m_personal, defaults={'page': None, 'order': 4})
    MenuItem.objects.get_or_create(title="Time Keeping Widget", parent=m_custom_apps, defaults={'page': p_time_keeper, 'order': 1})

    print("Seeding sample database app records...")
    
    # Projects
    Project.objects.update_or_create(
        title="Highschool Photography Mentorship",
        defaults={
            'category': 'Photography',
            'status': 'in_progress',
            'description': 'Mentoring high school students in basic composition, DSLR operations, and Lightroom post-processing techniques. Planning a local gallery exhibit.',
            'start_date': '2025-09-01',
            'rank': 2
        }
    )
    Project.objects.update_or_create(
        title="Video AI Internship Prep Program",
        defaults={
            'category': 'Video AI Internships',
            'status': 'completed',
            'description': 'Designed and implemented a curriculum focusing on OpenCV, PyTorch, and video analytics pipeline development to prepare university candidates.',
            'start_date': '2025-06-01',
            'end_date': '2025-08-30',
            'rank': 1
        }
    )

    # Workflow Ideas
    WorkflowIdea.objects.get_or_create(title="Woodworking: Build a custom solid walnut key organizer", defaults={
        'description': 'A clean, wall-mounted key hook tray with hidden magnetic attachments. Need to purchase walnut lumber and rare-earth magnets.',
        'priority': 'medium',
        'status': 'backlog'
    })
    WorkflowIdea.objects.get_or_create(title="Indian Music: Curate a Raga Yaman tutorial recording", defaults={
        'description': 'Record a 15-minute introductory Bansuri flute guide covering Aaroh, Avroh, Pakad, and a simple Bandish in Teen Taal.',
        'priority': 'high',
        'status': 'active'
    })
    WorkflowIdea.objects.get_or_create(title="HP Nostalgia Blog: The transition from Unix to Linux in the 90s", defaults={
        'description': 'Write an editorial style retrospection of HP-UX systems development and how Linux reshaped server operating systems.',
        'priority': 'low',
        'status': 'done'
    })

    # Book Reviews
    BookReview.objects.get_or_create(title="Designing Data-Intensive Applications", defaults={
        'author': 'Martin Kleppmann',
        'rating': 5,
        'summary': 'An exceptional architectural guide detailing trade-offs of relational, document, graph databases, streaming systems, and replication mechanics.',
        'review_content': """### Review & Takeaways

This book acts as the bridge between theoretical computer science and practical database engineering. Kleppmann has done an outstanding job of breaking down complex concepts like **linearizability**, **consensus protocols**, and **SSTables/LSM-Trees**.

#### Key Areas Covered
1. **Data Models and Query Languages**: SQL vs. NoSQL (relational, document, graph).
2. **Storage and Retrieval**: B-Trees, LSM-Trees, and indexes.
3. **Distributed Data**: Replication, partitioning, transactions, and consensus.

Highly recommended for senior software engineers, architects, and anyone building distributed backends.""",
        'read_date': '2025-03-15'
    })
    BookReview.objects.get_or_create(title="Gödel, Escher, Bach: An Eternal Golden Braid", defaults={
        'author': 'Douglas R. Hofstadter',
        'rating': 5,
        'summary': 'A Pulitzer Prize-winning classic that explores recursion, formal systems, self-reference, and how cognition arises from formal rules.',
        'review_content': """### Review & Takeaways

GEB is a mind-bending puzzle book that connects the mathematics of Kurt Gödel, the artistic woodcuts of M.C. Escher, and the contrapuntal music of J.S. Bach. 

#### Core Concept: Strange Loops
Hofstadter introduces the idea of a **strange loop** — a hierarchical system where moving upwards or downwards through the levels eventually brings you back to the starting point. He argues that consciousness and the feeling of 'I' are generated by these loops in our neural networks.

An intellectual adventure that rewards slow, careful reading.""",
        'read_date': '2025-01-10'
    })

    # Music Tracks
    MusicTrack.objects.get_or_create(title="Raga Yaman - Alap & Drut Gat in Teental", defaults={
        'artist': 'Pandit Hariprasad Chaurasia (Bansuri)',
        'genre': 'Hindustani Classical',
        'description': 'A beautiful rendition of Raga Yaman, a late evening Kalyan-thaat raga. The piece begins with a slow meditative Alap and progresses to a fast-tempo Gat accompanied by Tabla.',
        'youtube_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    })
    MusicTrack.objects.get_or_create(title="Thumri in Raga Bhairavi", defaults={
        'artist': 'Ustad Rashid Khan (Vocal)',
        'genre': 'Hindustani Classical (Semi-Classical)',
        'description': 'Bhairavi is a morning raga that is traditionally sung at the conclusion of concerts. This Thumri showcases Ustad Rashid Khan\'s masterful control over sargam and emotional expressions.',
        'youtube_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    })

    # Recipes
    Recipe.objects.get_or_create(title="Crispy Onion Pakoras (Pyazi)", defaults={
        'ingredients': """* 2 large red onions, thinly sliced
* 1 cup gram flour (besan)
* 2 tbsp rice flour (for extra crispness)
* 1 tsp chili powder
* 1/2 tsp turmeric powder
* 1/2 tsp ajwain (carom seeds)
* 2 green chilies, finely chopped
* Fresh coriander leaves, chopped
* Salt to taste
* Oil for deep frying""",
        'instructions': """1. **Onion Prep**: In a bowl, toss sliced onions with salt, chopped chilies, and coriander. Let it sit for 10 minutes. The onions will release their natural moisture.
2. **Batter Mix**: Add the ajwain, turmeric, chili powder, gram flour, and rice flour. Mix well with your hands. The flour should coat the onions. Sprinkle 1-2 tablespoons of water only if the mix is too dry. It should NOT be a runny batter.
3. **Frying**: Heat oil in a deep pan. Pinch small, irregular-shaped portions of the mixture and carefully drop them into the hot oil.
4. **Golden Crisp**: Fry on medium heat, turning occasionally, until the pakoras are golden brown and crispy (approx. 4-5 minutes).
5. **Serve**: Drain on paper towels and serve piping hot with green chutney or sweet tamarind chutney, alongside hot Masala Chai.""",
        'prep_time_minutes': 20
    })
    Recipe.objects.get_or_create(title="Perfect Ginger Masala Chai", defaults={
        'ingredients': """* 1 cup water
* 1 cup whole milk
* 2 tsp black tea leaves (Assam CTC preferred)
* 1-inch fresh ginger, crushed
* 2 cardamom pods, crushed
* 2 tsp sugar (adjust to taste)""",
        'instructions': """1. **Boil Aromatics**: In a saucepan, bring water to a boil. Add the crushed ginger and cardamom. Simmer for 2-3 minutes until the water becomes fragrant.
2. **Brew Tea**: Add the tea leaves and sugar. Let it boil for 1-2 minutes until you see a double reddish-brown color.
3. **Add Milk**: Pour in the milk and stir. Bring the chai to a boil.
4. **Simmer & Aerate**: Lower the heat and let it simmer for another minute. Pro tip: Lift the chai slightly with a spoon/ladle and pour it back to aerate it. Bring it back to a boil once more.
5. **Strain & Serve**: Strain into teacups and enjoy alongside crispy pakoras.""",
        'prep_time_minutes': 10
    })

    print("Database seeding completed successfully!")

if __name__ == '__main__':
    seed_db()
