## Markdown Cheat Sheet [#markdown-cheat-sheet]

Here is a quick-reference guide for basic and extended Markdown syntax (including GitHub-flavored Markdown used on this site).

## Table of Contents [#table-of-contents]

- [Headings](#headings)
- [Text Formatting](#text-formatting)
- [Lists](#lists)
- [Links & Images](#links-images)
- [Code & Quotes](#code-quotes)
- [Tables](#tables)
- [Horizontal Rules](#horizontal-rules)
- [Footnotes](#footnotes)
- [Definition Lists](#definition-lists)
- [HTML & Escaping](#html-escaping)
- [Miscellaneous](#miscellaneous)
- [Site-Specific Notes](#site-specific-notes)

## Headings [#headings]

```
# Heading 1
## Heading 2
### Heading 3
#### Heading 4
##### Heading 5
###### Heading 6
```

On this site you can set an explicit jump target with `[#id]` after the title:

```
## My Section [#my-section]
```

That renders as a heading you can link to with `[Jump](#my-section)`.

## Text Formatting [#text-formatting]

```
**Bold text**
*Italic text*
***Bold and italic***
__Bold__ and _italic_ (underscore form)
~~Strikethrough~~
==Highlight== (not always supported)
H~2~O and x^2^ (subscript / superscript — limited support)
```

Line breaks:

```
Hard break: end a line with two spaces  
Or use a blank line between paragraphs.
```

## Lists [#lists]

Unordered:

```
- Item 1
- Item 2
  - Nested item
  - Nested item
* Also works with asterisks
+ Or plus signs
```

Ordered:

```
1. First
2. Second
   1. Nested ordered
   2. Nested ordered
3. Third
```

Task lists (GFM):

```
- [ ] Unchecked task
- [x] Checked task
- [X] Also checked
```

## Links & Images [#links-images]

```
[Google](https://google.com)
[Local page path](/p/73/articles)
[Same-page jump](#headings)
[Link with title](https://example.com "Tooltip title")

![Alt text](https://example.com/image.jpg)
![Alt text](https://example.com/image.jpg "Image title")

<!-- Reference-style links -->
[Reference link][ref-id]
[ref-id]: https://example.com
```

Autolinks:

```
https://devenkalra.com
<https://devenkalra.com>
```

## Code & Quotes [#code-quotes]

Inline and fenced code:

````
`inline code`

```
plain code block
```

```python
def hello(name):
    print(f"Hello, {name}")
```
````

Blockquotes:

```
> Single-line quote
>
> > Nested quote
>
> Quote with **formatting** and a [link](#links-images)
```

## Tables [#tables]

```
| Header 1 | Header 2 | Header 3 |
| -------- | -------- | -------- |
| Cell 1   | Cell 2   | Cell 3   |
| Left     | Center   | Right    |
```

Alignment:

```
| Left     | Center   | Right    |
| :------- | :------: | -------: |
| left     | center   | right    |
| aaa      | bbb      | ccc      |
```

Tips:

- Put a blank line before and after the table
- Use real line breaks between rows (not literal `\n` text)
- Cells can contain `**bold**`, `*italic*`, and `` `code` ``

## Horizontal Rules [#horizontal-rules]

```
---
***
___
```

## Footnotes [#footnotes]

```
Here is a statement with a footnote.[^1]

[^1]: Footnote contents go here.
```

(Support depends on the renderer; GFM/common pipelines vary.)

## Definition Lists [#definition-lists]

Some processors support:

```
Term
: Definition of the term

Another term
: First definition
: Second definition
```

If unsupported, use a bullet list or bold labels instead:

```
**Term** — definition of the term
```

## HTML & Escaping [#html-escaping]

Raw HTML (allowed on this site when using markdown + raw HTML):

```
<details>
<summary>Click to expand</summary>

Hidden details go here.

</details>

<br>
<a id="custom-anchor"></a>
```

Escape Markdown special characters with a backslash:

```
\*not italic\*
\# not a heading
\[not a link\](url)
```

## Miscellaneous [#miscellaneous]

Emoji shortcodes (renderer-dependent):

```
:rocket: :white_check_mark: :warning:
```

Comments (HTML comments are ignored in output):

```
<!-- This will not appear on the page -->
```

Math (renderer-dependent; not guaranteed here):

```
Inline: \( x^2 + y^2 = z^2 \)
Block:
$$
\int_0^1 x^2 \, dx
$$
```

Keyboard / sample UI text:

```
Press `Ctrl+S` to save.
Use **Save** then **Publish**.
```

## Site-Specific Notes [#site-specific-notes]

- Prefer GitHub-flavored tables, task lists, and strikethrough — they are supported in page render.
- Use `## Title [#anchor-id]` for stable in-page anchors; TOC links should use `(#anchor-id)`.
- Literal `\n` sequences pasted from JSON/Swagger are converted to real line breaks when you save a page in admin.
- Keep a blank line around headings, lists, code fences, and tables so the preview parses cleanly.
