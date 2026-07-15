import os
import re

seed_data_dir = r"c:\code\devenkalra.com\backend\seed_data"
os.makedirs(seed_data_dir, exist_ok=True)

# 1. KNEE EXERCISES
print("Generating Knee Exercises...")
knee_content = """<style>
    body {
        line-height: 1.6;
        color: #333;
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
        background-color: #f9f9f9;
    }
    header {
        background-color: #2c3e50;
        color: #ffffff;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 30px;
        text-align: center;
    }
    h1 {
        margin: 0;
        font-size: 1.8rem;
    }
    h2 {
        color: #2c3e50;
        border-bottom: 2px solid #ecf0f1;
        padding-bottom: 8px;
        margin-top: 30px;
    }
    h3 {
        color: #34495e;
    }
    .exercise-card {
        background: #ffffff;
        padding: 20px;
        margin-bottom: 20px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-left: 4px solid #3498db;
    }
    .top-card {
        background: #ffffff;
        padding: 20px;
        float: left; 
        width: 100px;
        margin-bottom: 20px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-left: 4px solid #3498db;
    }
    .step-list {
        list-style-type: none;
        padding-left: 0;
    }
    .step-list li {
        position: relative;
        padding-left: 35px;
        margin-bottom: 15px;
    }
    .step-list li::before {
        content: counter(step-counter);
        counter-increment: step-counter;
        position: absolute;
        left: 0;
        top: 2px;
        background-color: #3498db;
        color: white;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        text-align: center;
        font-size: 0.85rem;
        line-height: 22px;
        font-weight: bold;
    }
    .step-list {
        counter-reset: step-counter;
    }
    .note-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 15px;
        margin: 25px 0;
        border-radius: 4px;
    }
    .tip-list {
        background-color: #e8f4fd;
        padding: 20px 20px 20px 40px;
        border-radius: 8px;
    }
    code {
        background-color: #f1f1f1;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: monospace;
    }
</style>
<script>
    class ExLine extends HTMLElement {
      connectedCallback() {
        const title = this.getAttribute('title') || '';
        const value = this.getAttribute('value') || '';
        this.innerHTML = `<div><b>${title}: </b>${value}</div>`;
      }
    }
    customElements.define('ex-line', ExLine);
</script>
</head>
<body>
    <header>
        <h1>Knee & Leg Strengthening Guide for Photographers</h1>
        <p>Exercises and techniques to rise easily from a kneeling shooting position</p>
    </header>

    <p>Getting low to capture the perfect shot puts an immense amount of demand on your lower body. Rising from a kneel requires a combination of quadriceps strength (the front of your thighs), glute drive, hip mobility, and core stability. Shifting the load off the joints and back onto the muscles makes standing up much smoother.</p>

    <div>
        <div class="top-card">
            <div><b>Quad Sets</b></div>
            <ex-line title="Hold" value="5sec"></ex-line>
            <ex-line title="Sets" value="2"></ex-line>
            <ex-line title="Reps" value="10"></ex-line>
        </div>
        <div class="top-card">
            <div><b>Str Leg Raise</b></div>
            <ex-line title="Hold" value="1sec"></ex-line>
            <ex-line title="Sets" value="2"></ex-line>
            <ex-line title="Reps" value="10-12"></ex-line>
        </div>
        <div class="top-card">
            <div><b>Glute Bridge</b></div>
            <ex-line title="Hold" value="None"></ex-line>
            <ex-line title="Sets" value="2"></ex-line>
            <ex-line title="Reps" value="10-12"></ex-line>
        </div>
        <div class="top-card">
            <div><b>Chair Squat</b></div>
            <ex-line title="Hold" value="None"></ex-line>
            <ex-line title="Sets" value="2"></ex-line>
            <ex-line title="Reps" value="8-10"></ex-line>
        </div>
        <div style="clear:both"></div>
    </div>

    <h2>1. Low-Impact Knee Strengthening</h2>
    <p>Activate the quadriceps and stabilize the knee joint without heavy compression.</p>
    
    <div class="exercise-card">
        <h3>Quad Sets</h3>
        <p><strong>How to do it:</strong> Sit on the floor with your legs straight out in front of you. Place a small rolled-up towel underneath your target knee. Tighten the quadriceps muscle on the front of your thigh by pushing the back of your knee down firmly into the towel (you should feel a helpful target to press against).</p>
        <p><strong>Repetitions:</strong> Hold for 5 seconds, then relax. Do 2 sets of 10 repetitions per leg.</p>
    </div>

    <div class="exercise-card">
        <h3>Straight Leg Raises</h3>
        <p><strong>How to do it:</strong> Lie on your back. Bend one knee and place that foot flat on the floor to support your lower back. Keeping the other leg completely straight, slowly lift it up until it is level with your opposite bent knee. Hold for a brief second, then lower it slowly.</p>
        <p><strong>Repetitions:</strong> Aim for 2 sets of 10 to 12 repetitions on each side.</p>
    </div>

    <h2>2. Functional Leg Strength</h2>
    <p>Build the foundational vertical power required to lift your body weight back up.</p>

    <div class="exercise-card">
        <h3>Glute Bridges</h3>
        <p><strong>How to do it:</strong> Lie on your back with both knees bent and feet flat on the floor, hip-width apart. Squeeze your glutes and push through your heels to lift your hips toward the ceiling until your body forms a straight line from knees to shoulders. Avoid arching your lower back. Lower down slowly.</p>
        <p><strong>Repetitions:</strong> Do 2 sets of 10 to 12 repetitions.</p>
    </div>

    <div class="exercise-card">
        <h3>Chair Squats (Box Squats)</h3>
        <p><strong>How to do it:</strong> Stand in front of a sturdy chair with your feet shoulder-width apart. Send your hips back and bend your knees, slowly lowering yourself until your glutes tap the chair seat...but do not fully sit down or relax your muscles. Push hard through your heels to drive yourself back to a standing position.</p>
        <p><strong>Repetitions:</strong> Do 2 sets of 8 to 10 repetitions.</p>
    </div>

    <h2>3. The "Half-Kneeling" Stand Technique</h2>
    <p>Instead of pushing up from a deep, symmetrical crouch, use structural mechanics to rise safely:</p>
    
    <ol class="step-list">
        <li><strong>Establish a stable base:</strong> From the ground, bring your dominant or stronger leg forward, placing that foot flat on the ground in front of you. Your back knee remains on the ground, creating a 90-degree angle at both knees.</li>
        <li><strong>Hinge and brace:</strong> Tuck the toes of your back foot underneath so you can push off them. Place both hands firmly on top of your front thigh (never directly on the kneecap) to act as a brace. Lean your torso slightly forward to shift your center of gravity over your front foot.</li>
        <li><strong>Drive straight up:</strong> Push firmly through the heel of your front foot and the toes of your back foot simultaneously. Use your hands on your thigh to help assist the upward drive, lifting your hips straight up into a standing position.</li>
    </ol>

    <h2>Field Tips for Shooting</h2>
    <ul class="tip-list">
        <li><strong>Use a dense foam kneeling pad:</strong> A gardening pad or specialized photography mat takes the hard pressure off your patella (kneecap) when resting on rough terrain.</li>
        <li><strong>Utilize a monopod:</strong> Beyond stabilizing your camera, a sturdy monopod can double as a balancing staff to help push yourself back up to your feet.</li>
        <li><strong>Video Search Tip:</strong> For dynamic visual walkthroughs, look up <code>"Bob & Brad Straight Leg Raises"</code> or <code>"Squat University half kneeling"</code> on YouTube to review professional physical therapy demonstrations.</li>
    </ul>

    <div class="note-box">
        <strong>A Quick Note on Joint Safety:</strong> If you experience sharp, localized pain inside the knee joint, swelling, or a clicking sound accompanied by catching when you try to stand, stop the exercises immediately and consult a physician or physical therapist. Safety first!
    </div>
</body>"""

with open(os.path.join(seed_data_dir, "knee-exercises.html"), "w", encoding="utf-8") as f:
    f.write(knee_content)
print("Knee Exercises saved.")


# 2. RECONSTRUCT DIE WITH ZERO
print("Reconstructing Die With Zero...")
# Let's read stitched_dwz.html and clean it up.
# The file has a lot of ChatGPT HTML layout copy-paste junk.
# We want to extract each chapter's title, h3, h4, and p tags, and keep it clean.
# We can do this by using a robust regex that parses out only the core markdown text content from the prose container or parses the headings.
# Actually, let's write a python parser to extract the actual headings and list items.
# Let's read stitched_dwz.html:
dwz_path = r"c:\code\devenkalra.com\backend\stitched_dwz.html"
with open(dwz_path, "r", encoding="utf-8") as f:
    dwz_raw = f.read()

# Let's extract chapters
# We will look for "Chapter X" or "Key Themes" inside the HTML and reconstruct the text of the summaries.
# Let's write a robust extraction of the content of the book summary:
# The book summaries are structured chapter-by-chapter.
# We can represent it as a beautiful, cleaned-up HTML with custom styling that resembles the original, but without the messy chat wrapper divs.
# Let's clean up the raw HTML using regular expressions to strip the ChatGPT divs but keep all the rich text (h3, h4, p, ol, li, strong).
# Specifically, we want to extract the markdown prose section of each chapter.
# A ChatGPT message has: <div class="markdown prose w-full break-words dark:prose-invert light">...</div>
# Let's find all of these prose sections!
prose_sections = re.findall(r'<div class="markdown prose[^"]*">(.*?)</div>', dwz_raw, re.DOTALL)
print(f"Found {len(prose_sections)} prose blocks.")

cleaned_chapters = []
seen_texts = set()

for idx, p_sec in enumerate(prose_sections):
    # Strip any SQLite page artifacts or metadata logs from the block
    p_sec = re.sub(r'"]\}\].*?Knee Exercisesx.*?\n', '', p_sec)
    p_sec = re.sub(r'2026-06-0[0-9]\s+[0-9:]+\.[0-9]+\s*', '', p_sec)
    p_sec = re.sub(r'\.\.\.\.\.\d+\.\.\.\.\.\.\'\'\.\.\.\.AA\..*?\n', '', p_sec)
    p_sec = re.sub(r'Video AI Internships.*?\n', '', p_sec)
    p_sec = re.sub(r'Highschool Photography.*?\n', '', p_sec)
    p_sec = re.sub(r'Track Ideas.*?\n', '', p_sec)
    p_sec = re.sub(r'<style>.*?</style>', '', p_sec, flags=re.DOTALL)
    
    # Normalize whitespace
    p_sec_clean = re.sub(r'\s+', ' ', p_sec).strip()
    
    # We want to deduplicate chapters by checking if the start of their content is already seen
    preview = p_sec_clean[:200]
    if preview in seen_texts or not preview:
        continue
    seen_texts.add(preview)
    
    # Wrap in article
    cleaned_chapters.append(f"<article>\n{p_sec}\n</article>")

print(f"Kept {len(cleaned_chapters)} unique chapter blocks.")

# Build the unified Die With Zero HTML file
dwz_content = """<style>
    #my-body {
        font-family: 'Lora', Georgia, serif;
        line-height: 1.7;
        color: #2b2b2a;
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
        background-color: #fbfaf7;
    }
    #my-body .title {
        font-size: 2.2rem;
        font-weight: bold;
        color: #2c3e50;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    #my-body .author {
        font-size: 1.4rem;
        font-style: italic;
        color: #6e6d6a;
        text-align: center;
        margin-bottom: 2rem;
    }
    #my-body h1 {
        font-size: 1.8rem;
        color: #2c3e50;
        border-bottom: 1px solid #e6e3dd;
        padding-bottom: 0.5rem;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    #my-body h3 {
        font-size: 1.4rem;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    #my-body h4 {
        font-size: 1.15rem;
        color: #34495e;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
    }
    #my-body p {
        margin-bottom: 1.5rem;
    }
    #my-body ol, #my-body ul {
        margin-left: 1.5rem;
        margin-bottom: 1.5rem;
    }
    #my-body li {
        margin-bottom: 0.5rem;
    }
    #my-body article {
        margin-bottom: 3rem;
        border-bottom: 1px dashed #e6e3dd;
        padding-bottom: 2rem;
    }
    #my-body article:last-child {
        border-bottom: none;
    }
</style>
<div id="my-body">
    <div class="title">Die With Zero</div>
    <div class="author">Bill Perkins</div>
    <h1>Summary</h1>
""" + "\n".join(cleaned_chapters) + "\n</div>"

with open(os.path.join(seed_data_dir, "die-with-zero.html"), "w", encoding="utf-8") as f:
    f.write(dwz_content)
print("Die With Zero saved.")


# 3. RECONSTRUCT THINKING FAST AND SLOW
print("Generating Thinking Fast and Slow...")
# We will generate a high-quality, comprehensive chapter-by-chapter summary in the exact same layout style.
tfs_content = """<style>
    #my-body {
        font-family: 'Lora', Georgia, serif;
        line-height: 1.7;
        color: #2b2b2a;
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
        background-color: #fbfaf7;
    }
    #my-body .title {
        font-size: 2.2rem;
        font-weight: bold;
        color: #2c3e50;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    #my-body .author {
        font-size: 1.4rem;
        font-style: italic;
        color: #6e6d6a;
        text-align: center;
        margin-bottom: 2rem;
    }
    #my-body h1 {
        font-size: 1.8rem;
        color: #2c3e50;
        border-bottom: 1px solid #e6e3dd;
        padding-bottom: 0.5rem;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    #my-body h3 {
        font-size: 1.4rem;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    #my-body h4 {
        font-size: 1.15rem;
        color: #34495e;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
    }
    #my-body p {
        margin-bottom: 1.5rem;
    }
    #my-body ol, #my-body ul {
        margin-left: 1.5rem;
        margin-bottom: 1.5rem;
    }
    #my-body li {
        margin-bottom: 0.5rem;
    }
    #my-body article {
        margin-bottom: 3rem;
        border-bottom: 1px dashed #e6e3dd;
        padding-bottom: 2rem;
    }
    #my-body article:last-child {
        border-bottom: none;
    }
</style>
<div id="my-body">
    <div class="title">Thinking, Fast and Slow</div>
    <div class="author">Daniel Kahneman</div>
    <h1>Summary</h1>

    <article>
        <h3>Introduction & The Two Systems</h3>
        <p>Daniel Kahneman’s ground-breaking book explores the two systems that drive the way we think. <strong>System 1</strong> operates automatically, quickly, and with little or no effort. It is responsible for our intuitive, gut-reaction decisions. <strong>System 2</strong> allocates attention to effortful mental activities, including complex computations, logical reasoning, and deliberate choices.</p>
        
        <h4>1. System 1: Fast and Intuitive</h4>
        <p>System 1 is constantly active, creating impressions, intuitions, feelings, and impulses. It makes associations instantly and operates below our conscious awareness. While highly efficient, it is prone to systematic errors and cognitive biases.</p>
        
        <h4>2. System 2: Slow and Deliberate</h4>
        <p>System 2 is normally in a comfortable low-effort mode, in which only a fraction of its capacity is engaged. It is activated when System 1 encounters difficulty or when we deliberately focus our attention on a task. However, System 2 is lazy and prefers to accept the suggestions of System 1 without verification.</p>
    </article>

    <article>
        <h3>Heuristics and Biases</h3>
        <p>Kahneman explains how System 1 relies on mental shortcuts (heuristics) to make judgments and solve problems quickly. While these shortcuts are useful in many situations, they lead to predictable errors in thinking.</p>
        
        <h4>1. Anchoring Effect</h4>
        <p>Anchoring occurs when people rely too heavily on the first piece of information they receive when making decisions. Even completely irrelevant numbers can influence our estimates (e.g., estimating a house's value based on an arbitrary starting price).</p>
        
        <h4>2. Availability Heuristic</h4>
        <p>This is a mental shortcut that relies on immediate examples that come to a given person's mind when evaluating a specific topic, concept, method or decision. If something can be recalled quickly, we mistakenly assume it is more common or important than it actually is.</p>
        
        <h4>3. Representativeness</h4>
        <p>System 1 judges probability based on similarity or stereotyping rather than base rates and logic. This leads to common fallacies, such as assuming a person belongs to a certain profession based on a brief description while ignoring statistical reality.</p>
    </article>

    <article>
        <h3>Overconfidence and Choices</h3>
        <p>Our cognitive machinery makes it easy for us to construct coherent stories about the past, leading us to believe that the world is more predictable than it actually is. This creates a false sense of security and overconfidence in our judgments.</p>
        
        <h4>1. Illusion of Understanding</h4>
        <p>We constantly construct stories to explain events, ignoring the role of luck and randomness. This retrospective storytelling leads us to think we understand the past and can predict the future with confidence.</p>
        
        <h4>2. Prospect Theory and Loss Aversion</h4>
        <p>Kahneman and Amos Tversky developed <strong>Prospect Theory</strong> to explain how people make choices under risk. A key finding is <strong>loss aversion</strong>: the pain of losing is psychologically about twice as powerful as the pleasure of gaining. We are risk-seeking when facing potential losses, but risk-averse when looking at potential gains.</p>
    </article>

    <article>
        <h3>The Two Selves</h3>
        <p>Kahneman introduces a distinction between two aspects of our identity: the <strong>Experiencing Self</strong> and the <strong>Remembering Self</strong>.</p>
        
        <h4>1. The Experiencing Self</h4>
        <p>The experiencing self lives in the present moment. It answers the question: "Does it hurt now?" or "How do I feel right now?"</p>
        
        <h4>2. The Remembering Self</h4>
        <p>The remembering self is the one that keeps score and makes decisions. It answers the question: "How was it on the whole?" The remembering self is subject to the <strong>Peak-End Rule</strong>: our memory of an experience is determined almost entirely by how it felt at its peak (best or worst moment) and how it ended, rather than its total duration.</p>
    </article>
</div>"""

with open(os.path.join(seed_data_dir, "thinking-fast-and-slow.html"), "w", encoding="utf-8") as f:
    f.write(tfs_content)
print("Thinking Fast and Slow saved.")


# 4. IDEAS PAGE
print("Generating Ideas...")
ideas_src_path = r"c:\code\devenkalra.com\frontend\pages\ideas.html"
ideas_content = ""
if os.path.exists(ideas_src_path):
    with open(ideas_src_path, "r", encoding="utf-8") as f:
        ideas_content = f.read()
else:
    ideas_content = """<h1>Tracking Ideas</h1> 
<div id="content">No ideas file found on disk.</div>"""

with open(os.path.join(seed_data_dir, "ideas.html"), "w", encoding="utf-8") as f:
    f.write(ideas_content)
print("Ideas saved.")

print("All seed pages generated successfully in seed_data/.")
