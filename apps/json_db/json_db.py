import json
import sqlite3
from pathlib import Path

def flatten_dict(d, parent_key="", sep="_"):
    """
    Recursively flattens a nested dict.
    Example:
      {"a": {"b": 1}} → {"a_b": 1}
    """
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def unflatten_dict(flat, sep="_"):
    """
    Reconstruct nested dictionaries from flattened keys.
    Example:
      {"a_b": 1} → {"a": {"b": 1}}
    """
    unflat = {}
    for k, v in flat.items():
        keys = k.split(sep)
        d = unflat
        for part in keys[:-1]:
            d = d.setdefault(part, {})
        d[keys[-1]] = v
    return unflat

def json_file_to_sqlite(json_file, sqlite_file, table_name="data"):
    json_file = Path(json_file)
    with json_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return json_to_sqlite(data, sqlite_file, table_name)

def json_to_sqlite(data, sqlite_file, table_name="data"):

    sqlite_file = Path(sqlite_file)

    if isinstance(data, dict):
        data = [data]

    # Flatten all rows
    flat_rows = [flatten_dict(row) for row in data]

    # Collect all possible columns
    columns = sorted({k for row in flat_rows for k in row.keys()})

    conn = sqlite3.connect(sqlite_file)
    cur = conn.cursor()

    # Drop + create table
    cur.execute(f"DROP TABLE IF EXISTS {table_name}")
    col_defs = ", ".join(f'"{col}" TEXT' for col in columns)
    cur.execute(f"CREATE TABLE {table_name} ({col_defs})")

    # Insert rows
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"

    for row in flat_rows:
        row_values = [row.get(col) for col in columns]
        cur.execute(insert_sql, row_values)

    conn.commit()
    conn.close()


def sqlite_to_json(sqlite_file, table_name="data", json_file="output.json", sep="_"):
    sqlite_file = Path(sqlite_file)
    json_file = Path(json_file)

    conn = sqlite3.connect(sqlite_file)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(f"SELECT * FROM {table_name}")
    rows = cur.fetchall()

    # Convert to list of dicts
    flat_rows = [dict(row) for row in rows]

    # Unflatten back to nested structures
    nested_rows = [unflatten_dict(r, sep=sep) for r in flat_rows]

    with json_file.open("w", encoding="utf-8") as f:
        json.dump(nested_rows, f, indent=2, ensure_ascii=False)

    conn.close()


if __name__ == "__main__":
    data = [
  {
    "title": "ANGEL DOWN",
    "author": "Daniel Kraus",
    "summary": "During World War I, five American soldiers sent into No Man’s Land to investigate a mysterious scream discover a literal fallen angel, confronting brutality and unexpected tenderness."
  },
  {
    "title": "AUGUST LANE",
    "author": "Regina Black",
    "summary": "High school sweethearts and former country music partners reunite after a decade of heartbreak, navigating a dark, stormy, but passionate love story."
  },
  {
    "title": "BAT EATER AND OTHER NAMES FOR CORA ZENG",
    "author": "Kylie Lee Baker",
    "summary": "In early-pandemic New York, Cora copes with her sister’s death by cleaning crime scenes, only to uncover eerie patterns that blend folklore horror, buddy comedy and social critique."
  },
  {
    "title": "BUCKEYE",
    "author": "Patrick Ryan",
    "summary": "A sweeping mid-20th-century saga follows two intertwined families in small-town Ohio, capturing an intrinsically American sense of place and time."
  },
  {
    "title": "THE BUFFALO HUNTER HUNTER",
    "author": "Stephen Graham Jones",
    "summary": "A Blackfeet man turned vampire anchors a horror novel that fuses genre thrills with a sharp exploration of Native American experience."
  },
  {
    "title": "BURY OUR BONES IN THE MIDNIGHT SOIL",
    "author": "V.E. Schwab",
    "summary": "This time-hopping lesbian vampire mystery moves between 16th-century Spain, 19th-century London and present-day Boston, mixing romance, suspense and supernatural intrigue."
  },
  {
    "title": "THE COLONY",
    "author": "Annika Norlin",
    "summary": "A group of misfits forms an enigmatic forest commune in Sweden, raising unsettling questions about utopia, community and the tension between individual and collective good."
  },
  {
    "title": "DEATH TAKES ME",
    "author": "Cristina Rivera Garza",
    "summary": "A detective story about a brutal killing spree becomes a feminist, metafictional twist on the mystery genre, laced with literary analysis and social critique."
  },
  {
    "title": "THE DIRECTOR",
    "author": "Daniel Kehlmann",
    "summary": "A novel about filmmaker G.W. Pabst intertwines movie stars and Nazis in a chilling, darkly funny portrait of art, collaboration and moral compromise in fascist Europe."
  },
  {
    "title": "THE DOORMAN",
    "author": "Chris Pavone",
    "summary": "Set in New York City with a looming death at its center, this thriller doubles as a sprawling, state-of-the-city portrait during a strange transitional moment."
  },
  {
    "title": "THE FEELING OF IRON",
    "author": "Giaime Alonge",
    "summary": "Two Holocaust survivors pursue revenge across decades and continents in a richly layered novel that echoes the sweep and moral weight of 19th-century epics."
  },
  {
    "title": "FLESH",
    "author": "David Szalay",
    "summary": "Istvan, a young man from a Hungarian housing project, is drawn into the upper tiers of British society, his restless search for meaning and belonging propelling him up and down the social ladder."
  },
  {
    "title": "A GENTLEMAN’S GENTLEMAN",
    "author": "TJ Alexander",
    "summary": "A trans nobleman in historical London must marry to keep his fortune, leading to a witty, tender romance built on secrets, missteps and emotional payoff."
  },
  {
    "title": "THE GOOD LIAR",
    "author": "Denise Mina",
    "summary": "A famed forensic scientist decides to reveal the true story behind an infamous double murder, exposing class, privilege and conspiracy in a twisty psychological thriller."
  },
  {
    "title": "A GUARDIAN AND A THIEF",
    "author": "Megha Majumdar",
    "summary": "In near-future Kolkata, a desperate thief and a mother whose climate visa has been derailed cross paths in a compassionate novel about fear, poverty and parental sacrifice."
  },
  {
    "title": "HEART THE LOVER",
    "author": "Lily King",
    "summary": "The aftermath of a college love triangle reverberates through the lives of an aspiring writer and two male friends who first meet in a 17th-century literature class."
  },
  {
    "title": "HEARTWOOD",
    "author": "Amity Gaige",
    "summary": "When an experienced hiker disappears on the Appalachian Trail, a game warden and a lonely retired scientist investigate, revealing trail culture and the complexities of mothers and daughters."
  },
  {
    "title": "HOLLOW SPACES",
    "author": "Victor Suthammanont",
    "summary": "Decades after an Asian American lawyer is acquitted of his girlfriend’s murder, his children re-examine the case in a precisely constructed legal thriller about family, race and truth."
  },
  {
    "title": "THE HOUNDING",
    "author": "Xenobe Purvis",
    "summary": "In 18th-century England, rumors that five eccentric sisters transform into dogs at night spark a gothic, suspenseful tale of hysteria, otherness and small-town dread."
  },
  {
    "title": "HOW TO DODGE A CANNONBALL",
    "author": "Dennard Dayle",
    "summary": "A hapless teenage flag-bearer tries to survive the Civil War in a savage, comic satire that skewers anti-Blackness, class exploitation and American myths."
  },
  {
    "title": "ISOLA",
    "author": "Allegra Goodman",
    "summary": "A 16th-century French noblewoman, marooned on a harsh North Atlantic island for loving the wrong man, recounts her ordeal in a calm, ordered voice that reshapes chaos into narrative."
  },
  {
    "title": "KATABASIS",
    "author": "R.F. Kuang",
    "summary": "Two rival Cambridge graduate students venture into the underworld to rescue their Magick professor, mirroring the costs and pressures of academic life in a dark, character-driven fantasy."
  },
  {
    "title": "KILLING STELLA",
    "author": "Marlen Haushofer",
    "summary": "A woman recounts how a teen girl came to live with her family and died tragically, turning a seeming whodunit into a piercing study of domestic tension and shared guilt."
  },
  {
    "title": "KING SORROW",
    "author": "Joe Hill",
    "summary": "A college student blackmailed into stealing rare books accidentally summons a real dragon whose yearly demands for sacrifice spiral into escalating horror."
  },
  {
    "title": "THE LONELINESS OF SONIA AND SUNNY",
    "author": "Kiran Desai",
    "summary": "An Indian couple nudged toward marriage navigates an ‘endlessly unresolved romance,’ caught between love and duty, tradition and modernity, and East and West."
  },
  {
    "title": "LONELY CROWDS",
    "author": "Stephanie Wambugu",
    "summary": "Two Black girls at a New England Catholic school forge an intense friendship that continues into their artistic lives in 1990s New York City, examining identity and ambition."
  },
  {
    "title": "MAGGIE; OR, A MAN AND A WOMAN WALK INTO A BAR",
    "author": "Katie Yee",
    "summary": "After her husband announces he’s leaving and she is diagnosed with cancer, a woman uses dry humor and a ‘user’s manual’ for her ex to navigate divorce, illness and selfhood."
  },
  {
    "title": "NIGHT WATCH",
    "author": "Kevin Young",
    "summary": "This poetry collection meditates on how artists and poets recast history, recovering erased narratives and inviting wounded voices to speak."
  },
  {
    "title": "ON THE CALCULATION OF VOLUME: Book III",
    "author": "Solvej Balle",
    "summary": "In the third volume of a seven-part series, a woman trapped in an endlessly repeating Nov. 18 experiences time as a looping, disorienting meditation on duration and existence."
  },
  {
    "title": "PERFECTION",
    "author": "Vincenzo Latronico",
    "summary": "A creative couple in hip Berlin drifts through a scene of cool expats and curated lifestyles in a sharply satirical portrait of self-conscious cosmopolitanism."
  },
  {
    "title": "PLAYWORLD",
    "author": "Adam Ross",
    "summary": "A successful child actor in early-1980s New York entangles himself in an affair with a married woman, as the novel traces his emotional turmoil and the costs of precocious fame."
  },
  {
    "title": "THE RAREST FRUIT",
    "author": "Gaëlle Bélem",
    "summary": "On the island of Réunion, an enslaved boy, Edmond Albius, discovers how to hand-pollinate vanilla, transforming the global flavor trade in a lush historical novel."
  },
  {
    "title": "THE REMEMBERED SOLDIER",
    "author": "Anjet Daanje",
    "summary": "A World War I veteran with amnesia leaves an asylum in the care of a woman claiming to be his wife, his fractured memory blurring personal identity and historical trauma."
  },
  {
    "title": "SHADOW TICKET",
    "author": "Thomas Pynchon",
    "summary": "In Depression-era America, a bumbling private eye hunts for a missing heiress in a genre-bending noir filled with Pynchon’s trademark comedy, paranoia and linguistic fireworks."
  },
  {
    "title": "SILVER ELITE",
    "author": "Dani Francis",
    "summary": "A psychic resistance fighter is forced into an elite unit tasked with hunting people like her, blending dystopian militarism with romantasy heat and rebellion."
  },
  {
    "title": "THE SISTERS",
    "author": "Jonas Hassen Khemiri",
    "summary": "Three magnetic Swedish sisters, daughters of a Tunisian mother, traverse Stockholm, Tunis and New York in a polyphonic novel narrated by a childhood acquaintance who resembles the author."
  },
  {
    "title": "THE SLIP",
    "author": "Lucas Schaefer",
    "summary": "After a troubled teen disappears in 1998 Austin, clues emerging a decade later reveal a boxer, a phone-sex operator and a community full of secrets in a twisting mystery."
  },
  {
    "title": "THE SOUTH",
    "author": "Tash Aw",
    "summary": "Over one summer on a remote Malaysian farm, a family’s buried expectations and secrets surface, while their queer son’s fraught bond with a rebellious worker’s son comes into focus."
  },
  {
    "title": "STARTLEMENT",
    "author": "Ada Limón",
    "summary": "A selection of new and earlier poems showcases Limón’s warm, conversational voice as she reflects on nature, intimacy and the emotional lives of ordinary people."
  },
  {
    "title": "STONE YARD DEVOTIONAL",
    "author": "Charlotte Wood",
    "summary": "A wildlife conservationist retreats to an Australian convent, where daily life and disruptions alike prompt quiet reflections on forgiveness, regret and how to live gently."
  },
  {
    "title": "SUNRISE ON THE REAPING",
    "author": "Suzanne Collins",
    "summary": "A prequel to ‘The Hunger Games’ follows young Haymitch Abernathy through the 50th Games, revealing how propaganda and authoritarianism warp both spectacle and survivor."
  },
  {
    "title": "THESE SUMMER STORMS",
    "author": "Sarah MacLean",
    "summary": "Returning to her Rhode Island estate after her billionaire father’s death, Alice Storm must compete in manipulative will-based challenges that expose family secrets and spark romance."
  },
  {
    "title": "TO SMITHEREENS",
    "author": "Rosalyn Drexler",
    "summary": "A 1972 cult novel pairs an art critic and a young woman wrestler to explore New York’s art and wrestling subcultures, dissecting relationships and power with surreal humor."
  },
  {
    "title": "THE TOKYO SUITE",
    "author": "Giovana Madalosso",
    "summary": "A nanny flees with her employer’s daughter in a tense Brazilian novel that lays bare class divisions between a wealthy TV executive and the caregiver she relies on."
  },
  {
    "title": "TRIP",
    "author": "Amie Barrodale",
    "summary": "A mother who dies at a conference on death and her autistic teenage son stranded at sea anchor a surreal, emotionally grounded story about connection across life and afterlife."
  },
  {
    "title": "VENETIAN VESPERS",
    "author": "John Banville",
    "summary": "In 1900 Venice, a British climber of the social ladder recounts his American heiress wife’s disappearance, revealing a dark, self-indicting psychological portrait wrapped in mystery."
  },
  {
    "title": "VICTORIAN PSYCHO",
    "author": "Virginia Feito",
    "summary": "A 19th-century governess calmly announces her plan to kill everyone in the house, as the novel traces her traumatic past and chillingly methodical revenge."
  },
  {
    "title": "WE DO NOT PART",
    "author": "Han Kang",
    "summary": "An ailing writer revisits the Jeju massacres of 1947–54, confronting mass violence and the erasure of victims in a lyrical, politically charged novel."
  },
  {
    "title": "WHAT WE CAN KNOW",
    "author": "Ian McEwan",
    "summary": "In 2119, a humanities professor obsessed with a lost poem traces its origins back a century, uncovering a buried scandal and probing the limits of knowledge and memory."
  },
  {
    "title": "A WITCH’S GUIDE TO MAGICAL INNKEEPING",
    "author": "Sangu Mandanna",
    "summary": "Once a prodigy, Sera Swan lost her magic resurrecting her aunt; years later she hunts a spell to restore it, teaming with a charming historian in a cozy paranormal romance."
  },
  {
    "title": "ABUNDANCE",
    "author": "Ezra Klein and Derek Thompson",
    "summary": "Klein and Thompson argue that well-intended regulations have produced paralyzing scarcity, urging a reimagined American liberalism focused on building more and moving faster."
  },
  {
    "title": "THE AGE of CHOICE",
    "author": "Sophia Rosenfeld",
    "summary": "Rosenfeld traces how personal choice evolved from suspect rebellion to a core democratic value, exploring the moral and political implications of a choice-saturated world."
  },
  {
    "title": "ALL CONSUMING",
    "author": "Ruby Tandoh",
    "summary": "Through witty, politically sharp essays, Tandoh examines the chaotic food culture of the 2020s, skewering trends while analyzing how food reflects power, desire and identity."
  },
  {
    "title": "APPLE IN CHINA",
    "author": "Patrick McGee",
    "summary": "McGee argues that Apple’s deep manufacturing dependence on China has created strategic vulnerabilities for the company and the U.S., even as it fueled China’s tech rise."
  },
  {
    "title": "THE ARROGANT APE",
    "author": "Christine Webb",
    "summary": "Webb challenges human exceptionalism by marshalling evidence of animal minds, arguing that experimental biases have overstated the gap between human and nonhuman intelligence."
  },
  {
    "title": "AWAKE",
    "author": "Jen Hatmaker",
    "summary": "After discovering her husband’s affair, an evangelical influencer chronicles the collapse of her marriage and her painful, public path toward rebuilding her life."
  },
  {
    "title": "BALDWIN",
    "author": "Nicholas Boggs",
    "summary": "Boggs offers an intimate biography of James Baldwin that foregrounds Baldwin’s relationships and how they shaped his art, activism and emotional world."
  },
  {
    "title": "BEING JEWISH AFTER THE DESTRUCTION OF GAZA",
    "author": "Peter Beinart",
    "summary": "Addressing a former friend, Beinart wrestles with Israeli politics, Jewish tradition and Oct. 7’s aftermath, seeking a framework for honest, painful debate about Gaza."
  },
  {
    "title": "BLACK MOSES",
    "author": "Caleb Gayle",
    "summary": "Gayle revives the story of Edward McCabe, who sought to build an all-Black state in Oklahoma after Reconstruction, exploring Black self-determination and political imagination."
  },
  {
    "title": "BOOK OF LIVES: A Memoir of Sorts",
    "author": "Margaret Atwood",
    "summary": "Atwood reflects on the experiences, landscapes and oddities that shaped her life and fiction, blending personal narrative with literary and cultural observation."
  },
  {
    "title": "BORN IN FLAMES",
    "author": "Bench Ansfield",
    "summary": "Ansfield shows how 1970s fires in the Bronx and other neighborhoods were often set by landlords, exposing racist housing and insurance systems that incentivized arson."
  },
  {
    "title": "THE BROKEN KING",
    "author": "Michael Thomas",
    "summary": "Thomas examines trauma and mental illness across generations of Black men in his family, from his father and brother to his own life and his sons’ futures."
  },
  {
    "title": "BUCKLEY",
    "author": "Sam Tanenhaus",
    "summary": "Tanenhaus portrays William F. Buckley as a charismatic architect of modern conservatism and media-savvy ‘intellectual entertainer’ who reshaped the American right."
  },
  {
    "title": "THE CALL OF THE HONEYGUIDE",
    "author": "Rob Dunn",
    "summary": "Dunn explores past and present mutualistic relationships between humans and other species, arguing that reviving cooperation with nature can help us live better on Earth."
  },
  {
    "title": "CAPITALISM",
    "author": "Sven Beckert",
    "summary": "Beckert offers a sweeping global history of capitalism’s many origins, tracking how diverse regions and systems converged into today’s interconnected economic order."
  },
  {
    "title": "CARELESS PEOPLE",
    "author": "Sarah Wynn-Williams",
    "summary": "A former Facebook policy director recounts her years inside the company, depicting leaders who shirked responsibility as the platform fueled disinformation and empowered autocrats."
  },
  {
    "title": "CLAIRE McCARDELL",
    "author": "Elizabeth Evitts Dickinson",
    "summary": "Dickinson chronicles fashion designer Claire McCardell, whose functional, independent-minded clothes helped create American sportswear and expanded women’s everyday freedom."
  },
  {
    "title": "THE CONTAINMENT",
    "author": "Michelle Adams",
    "summary": "Adams revisits the failed attempt to integrate Detroit’s schools through regional busing in the 1970s, analyzing the Supreme Court decision’s enduring impact on segregation."
  },
  {
    "title": "CRUMB",
    "author": "Dan Nadel",
    "summary": "Nadel’s biography of R. Crumb examines the controversial cartoonist’s life and work, showing how his underground comics shaped, and were shaped by, countercultural currents."
  },
  {
    "title": "DARK RENAISSANCE",
    "author": "Stephen Greenblatt",
    "summary": "Greenblatt recounts the life of Christopher Marlowe, Shakespeare’s brilliant rival, in a gripping narrative of artistic daring, espionage and deadly politics in Elizabethan England."
  },
  {
    "title": "DAUGHTERS OF THE BAMBOO GROVE",
    "author": "Barbara Demick",
    "summary": "Demick follows twin girls separated under China’s one-child policy—one kidnapped and adopted abroad, one left behind—tracing the emotional and political fallout of their division."
  },
  {
    "title": "EMPIRE OF AI",
    "author": "Karen Hao",
    "summary": "Profiling Sam Altman and OpenAI alongside global ghost workers and resource-intensive data centers, Hao exposes the human and environmental costs behind AI’s rapid ascent."
  },
  {
    "title": "EVERY DAY IS SUNDAY",
    "author": "Ken Belson",
    "summary": "Belson charts how NFL executives and owners transformed pro football into a year-round cultural juggernaut and media spectacle driven by profit and spectacle."
  },
  {
    "title": "THE FATE OF THE DAY",
    "author": "Rick Atkinson",
    "summary": "The second volume in Atkinson’s Revolutionary War trilogy vividly narrates the conflict’s middle years, blending battlefield drama with political and personal detail."
  },
  {
    "title": "A FLOWER TRAVELED IN MY BLOOD",
    "author": "Haley Cohen Gilliland",
    "summary": "Gilliland tells the stories of Argentine women disappeared by the dictatorship and the grandmothers who relentlessly sought their stolen grandchildren, blending history and testimony."
  },
  {
    "title": "GIRL ON GIRL",
    "author": "Sophie Gilbert",
    "summary": "Gilbert dissects early-2000s pop culture and trends, arguing that marketed ‘empowerment’ often masked and monetized women’s self-objectification."
  },
  {
    "title": "THE GODS OF NEW YORK",
    "author": "Jonathan Mahler",
    "summary": "Mahler portrays late-1980s New York as it emerges from crisis into financial powerhouse, tracking figures like Koch, Giuliani and Trump amid AIDS, crack and inequality."
  },
  {
    "title": "I SEEK A KIND PERSON",
    "author": "Julian Borger",
    "summary": "Discovering that his father’s rescue from Nazi Europe came via a heartbreaking newspaper ad, Borger reconstructs the lives of children saved by such pleas and their families."
  },
  {
    "title": "JOHN & PAUL",
    "author": "Ian Leslie",
    "summary": "Leslie explores the creative partnership of Lennon and McCartney, showing how their rivalry, affection and shared genius forged the Beatles’ extraordinary body of work."
  },
  {
    "title": "KING OF KINGS",
    "author": "Scott Anderson",
    "summary": "Anderson revisits the 1979 Iranian Revolution and its aftermath, arguing that it triggered a lasting realignment in the Middle East and exposed U.S. policy failures."
  },
  {
    "title": "THE LAST MANAGER",
    "author": "John W. Miller",
    "summary": "Miller’s biography of Orioles manager Earl Weaver captures his volcanic personality, innovative strategies and lasting impact on baseball."
  },
  {
    "title": "MARK TWAIN",
    "author": "Ron Chernow",
    "summary": "Chernow’s expansive biography follows Samuel Clemens from riverboats and journalism to global fame as Mark Twain, chronicling his brilliance and contradictions."
  },
  {
    "title": "A MARRIAGE AT SEA",
    "author": "Sophie Elmhirst",
    "summary": "Elmhirst recounts a young couple’s round-the-world sailing dream turned nightmare after a whale sinks their boat, examining survival and the strain on their relationship."
  },
  {
    "title": "MEMORIAL DAYS",
    "author": "Geraldine Brooks",
    "summary": "Brooks reflects on her marriage to journalist Tony Horwitz and the searing grief after his sudden death, retreating to an Australian island in search of solace."
  },
  {
    "title": "MOTHER EMANUEL",
    "author": "Kevin Sack",
    "summary": "Sack tells the long history of Charleston’s Emanuel A.M.E. Church and the 2015 massacre there, weaving meticulous reporting with a moving portrait of faith and resilience."
  },
  {
    "title": "MOTHERLAND",
    "author": "Julia Ioffe",
    "summary": "Ioffe interlaces her family’s story with a feminist history of modern Russia, charting the Soviet experiment in women’s emancipation and its unraveling."
  },
  {
    "title": "MOTHER MARY COMES TO ME",
    "author": "Arundhati Roy",
    "summary": "Roy uses her formidable mother, Mary Roy, as the center of a memoir about a difficult parent, artistic formation and the forces that shaped her life and work."
  },
  {
    "title": "1929",
    "author": "Andrew Ross Sorkin",
    "summary": "Sorkin reconstructs the 1929 stock market crash like a novel, drawing on archival sources to show how hubris and misjudgment shattered the U.S. economy."
  },
  {
    "title": "ONE DAY, EVERYONE WILL HAVE ALWAYS BEEN AGAINST THIS",
    "author": "Omar El Akkad",
    "summary": "El Akkad blends memoir and polemic to indict Western indifference to Gaza’s suffering, urging readers to see Palestinians’ pain as their own."
  },
  {
    "title": "THE PEEPSHOW",
    "author": "Kate Summerscale",
    "summary": "Summerscale revisits a lurid multi-victim murder case in 1950s London, using it to examine class, media frenzy and shifting social norms."
  },
  {
    "title": "RAISING HARE",
    "author": "Chloe Dalton",
    "summary": "During the pandemic, Dalton rescues and raises an abandoned baby hare, recounting how the fragile animal reshaped her perspective on care and uncertainty."
  },
  {
    "title": "SHATTERED DREAMS, INFINITE HOPE",
    "author": "Brandon M. Terry",
    "summary": "Terry offers a philosophically rich reassessment of the civil rights movement, embracing its tragic limitations while arguing for a nuanced, hopeful view of social change."
  },
  {
    "title": "THE SPINACH KING",
    "author": "John Seabrook",
    "summary": "Seabrook tells the story of his family’s spinach empire, using its wealth and dysfunction to probe inheritance, addiction and American agribusiness."
  },
  {
    "title": "THERE IS NO PLACE FOR US",
    "author": "Brian Goldstone",
    "summary": "Goldstone follows five working Atlanta families who fall into hidden homelessness, illuminating how low wages and high housing costs push them to the brink."
  },
  {
    "title": "THINGS IN NATURE MERELY GROW",
    "author": "Yiyun Li",
    "summary": "Li confronts the suicides of her two sons in a stark, unsentimental memoir about grief, parental love and the limits of understanding."
  },
  {
    "title": "THE TRAGEDY OF TRUE CRIME",
    "author": "John J. Lennon",
    "summary": "Writing from Sing Sing, Lennon intertwines his own story with those of fellow prisoners, critiquing the true-crime genre and exposing the reality of incarceration."
  },
  {
    "title": "WE THE PEOPLE",
    "author": "Jill Lepore",
    "summary": "Lepore chronicles centuries of attempts to amend the U.S. Constitution, showing how visions of change collide with a system designed to resist alteration."
  },
  {
    "title": "WHAT IS QUEER FOOD?",
    "author": "John Birdsall",
    "summary": "Birdsall surveys queer food culture, from restaurants to recipes and icons, arguing that queerness and food have long shaped each other in powerful ways."
  },
  {
    "title": "WILD THING",
    "author": "Sue Prideaux",
    "summary": "Prideaux reexamines Paul Gauguin’s life and myths, using new sources to depict his radical art and troubling personal choices in nuanced detail."
  },
  {
    "title": "THE ZORG",
    "author": "Siddharth Kara",
    "summary": "Kara recounts the infamous case of a slave ship whose crew drowned enslaved people for insurance money, arguing that the outrage helped galvanize abolition."
  }
]


    #json_to_sqlite(data, "test.db")
    sqlite_to_json("test.db", sep=":")
