import os
import django
import django.utils.timezone as timezone

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import BlogCategory, BlogTag, BlogPost, Comment

def seed_blog():
    print("Starting Blog Module seeding (non-destructive)...")

    # 1. Create Categories
    categories_data = [
        {"name": "Woodworking", "slug": "woodworking"},
        {"name": "Photography", "slug": "photography"},
        {"name": "Indian Music", "slug": "indian-music"},
        {"name": "Book Reviews", "slug": "book-reviews"},
        {"name": "Technology", "slug": "technology"},
    ]
    categories = {}
    for cat in categories_data:
        obj, created = BlogCategory.objects.get_or_create(
            slug=cat["slug"],
            defaults={"name": cat["name"]}
        )
        categories[cat["slug"]] = obj
        if created:
            print(f"Created category: {obj.name}")

    # 2. Create Tags
    tags_data = [
        {"name": "Woodworking", "slug": "woodworking"},
        {"name": "Walnut", "slug": "walnut"},
        {"name": "Photography", "slug": "photography"},
        {"name": "Lightroom", "slug": "lightroom"},
        {"name": "Indian Music", "slug": "indian-music"},
        {"name": "Bansuri", "slug": "bansuri"},
        {"name": "Classical", "slug": "classical"},
        {"name": "Books", "slug": "books"},
        {"name": "Philosophy", "slug": "philosophy"},
        {"name": "Personal Finance", "slug": "personal-finance"},
        {"name": "Django", "slug": "django"},
        {"name": "React", "slug": "react"},
    ]
    tags = {}
    for tag in tags_data:
        obj, created = BlogTag.objects.get_or_create(
            slug=tag["slug"],
            defaults={"name": tag["name"]}
        )
        tags[tag["slug"]] = obj
        if created:
            print(f"Created tag: {obj.name}")

    # 3. Create Blog Posts
    posts_data = [
        {
            "title": "The Art of Woodworking: Building a Solid Walnut Key Organizer",
            "slug": "art-of-woodworking-walnut-key-organizer",
            "summary": "Step-by-step walkthrough of designing and building a minimal, wall-mounted walnut key rack with hidden rare-earth magnets.",
            "content": """# The Art of Woodworking: Building a Solid Walnut Key Organizer

Woodworking has always been a therapeutic outlet for me. There is something deeply satisfying about taking a raw piece of hardwood timber and milling it down into a functional, beautiful object for the home. In this post, I'll walk you through my latest workshop project: a wall-mounted **solid walnut key organizer** with hidden magnetic slots.

## The Design Concept

The goal was extreme minimalism. I didn't want any visible metal hooks or slots. Instead, I wanted the keys to magically snap to the underside of the wood block. 

To achieve this, we use **Neodymium rare-earth magnets** embedded from behind, leaving only 1.5mm of wood thickness between the magnet and the bottom surface.

### Tools and Materials:
* A select piece of 8/4 American Black Walnut
* 10mm x 5mm Neodymium disc magnets (grade N52)
* Forstner bit (10mm)
* Router table and chamfer bit
* Danish oil for finishing
* Double-sided mounting tape or keyhole brackets for wall-mount

---

## Step-by-Step Build

### 1. Milling the Wood
First, we mill the walnut block to final dimensions: 12 inches long, 2 inches deep, and 1.25 inches thick. I used a jointer and planer to ensure all faces were perfectly square and smooth.

### 2. Drilling the Magnet Pockets
This is the most critical step. On the back face, mark the layout of the key hanging positions (spaced 2 inches apart). Using a drill press with a depth stop, carefully drill holes using the Forstner bit.
> [!IMPORTANT]
> Leave exactly 1.5mm of material at the bottom. If you drill too deep, you will blow through the face. If you drill too shallow, the magnetic pull will be too weak.

### 3. Inserting the Magnets
Add a drop of epoxy into each hole, press the Neodymium magnets in, and let them cure. Ensure the polarities are consistent so they don't fight each other during installation!

### 4. Edge Profiles & Sanding
I ran a slight 45-degree chamfer along all edges on the router table to soften the lines. Sanded the block progressively from 120-grit to 320-grit until it felt like silk.

### 5. Applying the Finish
I applied three coats of **Danish oil**, buffing with steel wool between coats. Danish oil brings out the rich, dark chocolate tones of the walnut and highlights the beautiful cathedral grain patterns.

![Finished Walnut Key Organizer](https://images.unsplash.com/photo-1533090161767-e6ffed986c88?auto=format&fit=crop&w=1200&q=80)

## The Final Result
The keyrings snap securely to the underside of the organizer. It has a tiny lip at the top that acts as a tray for mail and sunglasses. A simple, elegant weekend project!
""",
            "cover_image": "https://images.unsplash.com/photo-1533090161767-e6ffed986c88?auto=format&fit=crop&w=1200&q=80",
            "render_as_html": False,
            "category_slug": "woodworking",
            "tag_slugs": ["woodworking", "walnut"],
            "is_published": True,
            "publish_offset_days": -10,
        },
        {
            "title": "Chasing the Light: Essential Tips for Golden Hour Photography",
            "slug": "chasing-light-golden-hour-photography",
            "summary": "Unlock the secrets of shooting landscape and portrait photography during the hour after sunrise and before sunset.",
            "content": """# Chasing the Light: Essential Tips for Golden Hour Photography

Ask any photographer, amateur or professional, and they'll tell you: **light is everything**. But not all light is created equal. The magic happens during the golden hour—the brief window shortly after sunrise and just before sunset when the sun is low in the sky, producing soft, warm, diffused light.

Here are my key tips and technical setups for making the most of this fleeting magic.

## 1. Plan Ahead (The Golden Hour is Fleeting)
The name is slightly misleading. Depending on your latitude and the season, the "golden hour" might only last 20 to 30 minutes. Use apps like *The Photographer's Ephemeris* or *PhotoPills* to track the exact angles of sunrise/sunset and plan your location scouting beforehand.

## 2. Technical Settings for Landscapes
* **Aperture**: Shoot in the sweet spot of your lens, typically between `f/8` and `f/11`, for sharp details from foreground to background.
* **White Balance**: Avoid Auto White Balance (AWB) which tends to neutralize the warm colors. Switch to **Cloudy** or **Shade** presets, or manually dial it to around `6000K-6500K` to preserve the rich gold and orange tones.
* **Exposure**: Use exposure compensation or manual mode. Spot-meter on the sky highlights to prevent blowing them out. You can easily pull details out of shadows in post-processing if you shoot in RAW.

## 3. Backlighting & Silhouettes
Position yourself so your subject is directly between your camera and the sun. This creates a beautiful glow around the edges (rim lighting) or, if you underexpose, a dramatic silhouette.

![Sunset Photography Example](https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=1200&q=80)

## 4. Post-Processing in Lightroom
In Lightroom, I like to use selective radial filters to boost the warm tones locally where the sunbeams fall. Be subtle with the saturation slider—instead, use the **Vibrance** tool and split-tone the highlights with warm yellow/orange and the shadows with a cool teal or blue.

What's your favorite golden hour location? Let me know in the comments below!
""",
            "cover_image": "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=1200&q=80",
            "render_as_html": False,
            "category_slug": "photography",
            "tag_slugs": ["photography", "lightroom"],
            "is_published": True,
            "publish_offset_days": -5,
        },
        {
            "title": "An Introduction to Raga Yaman: The Evening Melodics",
            "slug": "introduction-raga-yaman-evening-melodies",
            "summary": "Explore the structural framework, scales, and emotional depth of Hindustani Classical Music's entry-level evening raga.",
            "content": """# An Introduction to Raga Yaman: The Evening Melodies

In Hindustani Classical Music, **Raga Yaman** is considered one of the most foundational ragas. Typically taught first to beginners due to its clear structure and linear scale, it is also a favorite of seasoned maestros because of its limitless scope for improvisation and emotional depth.

Let's dive into the anatomy and aesthetics of this beautiful evening melody.

## Structural Anatomy
Yaman is a Kalyan-thaat raga. Unlike major scales, it utilizes a sharp (Teevra) Fourth note (`Ma`) while all other notes are natural (Shuddha).

* **Arohana (Ascending scale)**: `Ni - Re - Ga - Ma# - Dha - Ni - Sa'` (Often, the root note `Sa` is avoided in ascension to emphasize the beauty of `Ni` and `Re`).
* **Avarohana (Descending scale)**: `Sa' - Ni - Dha - Pa - Ma# - Ga - Re - Sa`
* **Vadi (Primary note)**: `Ga` (The third scale degree)
* **Samvadi (Secondary note)**: `Ni` (The seventh scale degree)

---

## Mood and Aesthetics
Traditionally performed during the first quarter of the night (approx. 6 PM to 9 PM) as dusk transitions into darkness, Yaman evokes a mood of peace, prayer, and deep romantic devotion (Shringar and Bhakti rasa).

Its beauty lies in the sliding transition (Meend) from `Re` to `Ni` and back, and the suspenseful resolution on `Sa` from `Ni`.

## Recommended Listening
To truly appreciate Yaman, listen to:
1. **Pandit Hariprasad Chaurasia** on the Bansuri flute. His slow Alap in Yaman is masterfully calm.
2. **Ustad Amir Khan's** vocal vilambit (slow-tempo) bandish.
3. **Ustad Vilayat Khan** on Sitar.

Here is a short clip showing the scale breakdown:
```text
SrgmPdnS'  --> S R G M# P D N S'
```

In the next post, I will share some notation sheets (sargams) for a simple bandish in Teen Taal.
""",
            "cover_image": "https://images.unsplash.com/photo-1511192336575-5a79af67a629?auto=format&fit=crop&w=1200&q=80",
            "render_as_html": False,
            "category_slug": "indian-music",
            "tag_slugs": ["indian-music", "bansuri", "classical"],
            "is_published": True,
            "publish_offset_days": -2,
        },
        {
            "title": "Why You Should Read 'Die With Zero' Right Now (HTML Review)",
            "slug": "why-you-should-read-die-with-zero",
            "summary": "A review of Bill Perkins' thought-provoking philosophy on optimization of life energy, money, and experiences.",
            "content": """<div class="blog-html-content">
  <h1 style="color: var(--color-primary, #e2e8f0); font-family: 'Outfit', sans-serif;">Rethinking Money: A Review of 'Die With Zero'</h1>
  
  <p style="font-size: 1.1rem; line-height: 1.7; color: #a0aec0;">
    Most personal finance books teach you how to save, invest, and accumulate as much money as possible. Bill Perkins' <strong>Die With Zero</strong> takes the exact opposite approach. He asks a critical question: <em>What is the point of dying with millions of dollars in the bank?</em>
  </p>

  <div style="background: rgba(255, 255, 255, 0.03); border-left: 4px solid #f6ad55; padding: 1rem; margin: 1.5rem 0; border-radius: 4px;">
    <strong style="color: #f6ad55;">Core Thesis:</strong> If you die with money left over, you have effectively wasted the life energy it took to earn that money. The goal is to optimize your life, not your bank account.
  </div>

  <h3 style="color: #edf2f7; margin-top: 2rem;">Key Concepts:</h3>
  
  <ul style="color: #cbd5e0; line-height: 1.6; padding-left: 1.5rem;">
    <li style="margin-bottom: 0.5rem;">
      <strong>Rule 1: Optimize your life.</strong> Spend your money on experiences while you have the health and youth to enjoy them.
    </li>
    <li style="margin-bottom: 0.5rem;">
      <strong>Rule 2: Invest in experiences early.</strong> Memories pay dividends! The earlier you have an experience, the longer you can enjoy the "memory dividend" of that event throughout your life.
    </li>
    <li style="margin-bottom: 0.5rem;">
      <strong>Rule 3: Know your peak health.</strong> Health declines with age. A dollar spent on travel at 30 yields infinitely more utility than a dollar spent on travel at 75.
    </li>
  </ul>

  <h3 style="color: #edf2f7; margin-top: 2rem;">When to give to children/charity?</h3>
  <p style="color: #a0aec0; line-height: 1.7;">
    Perkins argues that waiting until you die to pass on inheritance is highly inefficient. Your kids will likely be in their 50s or 60s when you die and will have already passed their peak utility for that money. Give it to them when they are in their 20s or 30s, when it will make the biggest difference in their lives.
  </p>

  <div style="margin-top: 2rem; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 1.5rem; color: #718096; font-style: italic;">
    This blog post demonstrates HTML rendering support on devenkalra.com. Feel free to leave a comment below!
  </div>
</div>
""",
            "cover_image": "https://images.unsplash.com/photo-1592478411213-6153e4ebc07d?auto=format&fit=crop&w=1200&q=80",
            "render_as_html": True,
            "category_slug": "book-reviews",
            "tag_slugs": ["books", "personal-finance", "philosophy"],
            "is_published": True,
            "publish_offset_days": -1,
        },
        {
            "title": "Draft Post: Exploring Django 5.0 Viewsets",
            "slug": "exploring-django-5-viewsets",
            "summary": "An unpublished drafting session testing how Django 5.0 viewsets improve API design and code readability.",
            "content": """# Exploring Django 5.0 Viewsets

This is an unpublished post. It should only be visible to authenticated administrators when querying the backend API.

If you are seeing this on the public catalog, something is wrong with the queryset filtering!

* Draft posts are used for articles in progress.
* Once ready, the author can publish them via Django Admin using bulk actions or setting `is_published=True`.
""",
            "cover_image": None,
            "render_as_html": False,
            "category_slug": "technology",
            "tag_slugs": ["django", "react"],
            "is_published": False,
            "publish_offset_days": 1,
        }
    ]

    for post in posts_data:
        publish_time = timezone.now() + timezone.timedelta(days=post["publish_offset_days"])
        
        obj, created = BlogPost.objects.update_or_create(
            slug=post["slug"],
            defaults={
                "title": post["title"],
                "content": post["content"],
                "summary": post["summary"],
                "cover_image": post["cover_image"],
                "render_as_html": post["render_as_html"],
                "category": categories[post["category_slug"]],
                "is_published": post["is_published"],
                "publish_date": publish_time
            }
        )
        
        # Link tags
        for tag_slug in post["tag_slugs"]:
            obj.tags.add(tags[tag_slug])
            
        if created:
            print(f"Created post: {obj.title}")
        else:
            print(f"Updated post: {obj.title}")

        # Seed comments on the post
        if obj.is_published:
            # 1. Seed approved comment
            Comment.objects.get_or_create(
                post=obj,
                author_name="Alice Smith",
                author_email="alice@example.com",
                content="This is such an informative and beautifully written post! Looking forward to your next one.",
                defaults={"is_approved": True}
            )
            # 2. Seed approved comment 2
            Comment.objects.get_or_create(
                post=obj,
                author_name="Bob Jones",
                author_email="bob@example.com",
                content="Thanks for sharing these insights. The details are super clear and practical.",
                defaults={"is_approved": True}
            )
            # 3. Seed pending comment (needs moderation)
            Comment.objects.get_or_create(
                post=obj,
                author_name="Charlie Brown",
                author_email="charlie@example.com",
                content="Great post! I have a question: where can I buy the specific tools you mentioned?",
                defaults={"is_approved": False}
            )

    print("Blog Module seeding completed successfully!")

if __name__ == '__main__':
    seed_blog()
