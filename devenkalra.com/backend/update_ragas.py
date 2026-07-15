import os
import sqlite3
import django

# Set up Django environment so we can use Django ORM
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem

def extract_and_update():
    html_path = 'ragas_raw.html'
    if not os.path.exists(html_path):
        print(f"Error: {html_path} not found.")
        return

    print("Reading raw HTML...")
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract style block
    style_start = content.find('<style>')
    style_end = content.find('</style>', style_start) + len('</style>')
    style_block = content[style_start:style_end]

    # Extract raga container
    container_start = content.find('<div class="raga-container">')
    container_end = content.find('<!-- Video Modal -->', container_start)
    if container_end == -1:
        container_end = content.find('<div id="videoModal"', container_start)
    container_block = content[container_start:container_end]

    # Extract video modal
    modal_start = content.find('<div id="videoModal"')
    modal_end = content.find('</div>', content.find('modal-details', modal_start)) + len('</div>')
    # Find the closing tag of the modal outer div
    modal_outer_end = content.find('</div>', modal_end) + len('</div>')
    modal_block = content[modal_start:modal_outer_end]

    # Extract script
    script_start = content.find('<script>', modal_outer_end)
    script_end = content.find('</script>', script_start) + len('</script>')
    script_block = content[script_start:script_end]

    print("Modifying CSS and JS for IFrame scroll compatibility...")
    # 1. Modify CSS positions for absolute aligning within long IFrame
    style_block = style_block.replace('position: fixed;', 'position: absolute;')
    style_block = style_block.replace('position: relative;\n        width: 90%;\n        max-width: 1200px;', 
                                      'position: absolute;\n        left: 50%;\n        transform: translateX(-50%);\n        width: 90%;\n        max-width: 1200px;')

    # 2. Modify JavaScript to position the modal vertically based on click PageY
    script_block = script_block.replace('\r\n', '\n')
    js_target = 'function openVideoModal(videoId, title, movie, year, raga, singers, musicDirector, purity, prahar, level) {\n        const modal = document.getElementById(\'videoModal\');'
    js_replacement = """function openVideoModal(videoId, title, movie, year, raga, singers, musicDirector, purity, prahar, level) {
        // Calculate vertical position of click relative to IFrame top
        let clickY = 300;
        if (window.event && window.event.pageY) {
            clickY = window.event.pageY;
        } else if (event && event.pageY) {
            clickY = event.pageY;
        }
        const modalTop = Math.max(20, clickY - 250);
        
        const modal = document.getElementById('videoModal');
        const modalContent = modal.querySelector('.modal-content');
        modalContent.style.top = modalTop + 'px';
        modalContent.style.marginTop = '0';
"""
    script_block = script_block.replace(js_target, js_replacement)

    # Compile the final standalone HTML content
    # We load our iframe-editorial.css stylesheet first, then append custom ragas styles
    final_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Top 100 Raga-Based Hindi Songs</title>
    <link rel="stylesheet" href="/iframe-editorial.css">
    {style_block}
</head>
<body>
    {container_block}
    {modal_block}
    {script_block}
</body>
</html>
"""

    print("Updating database entry for slug 'indian-music'...")
    try:
        page = Page.objects.get(slug='indian-music')
        page.title = "Top 100 Raga-Based Hindi Songs"
        page.content = final_html
        page.render_as_html = True
        page.save()
        print("Updated Page table successfully!")

        # Update MenuItem title if exists
        menu_items = MenuItem.objects.filter(page=page)
        for item in menu_items:
            item.title = "Top 100 Raga-Based Hindi Songs"
            item.save()
            print(f"Updated MenuItem title to '{item.title}'")

    except Page.DoesNotExist:
        print("Page with slug 'indian-music' not found. Creating a new one...")
        page = Page.objects.create(
            title="Top 100 Raga-Based Hindi Songs",
            slug="indian-music",
            content=final_html,
            render_as_html=True
        )
        print("Created Page successfully!")

    print("Cleaning up raw files...")
    if os.path.exists('ragas_raw.html'):
        os.remove('ragas_raw.html')

    print("Done!")

if __name__ == '__main__':
    extract_and_update()
