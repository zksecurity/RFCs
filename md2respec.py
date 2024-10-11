import argparse
import frontmatter

import latex2mathml.converter
import markdown

# import markdown2
import re
from string import Template

template_path = "template.html"


def convert_markdown_to_html(markdown_file, config):
    """
    Converts a markdown file to HTML, incorporating front matter and custom configuration.

    Args:
      markdown_file: Path to the markdown file.
      config: A dictionary of configuration options.

    Returns:
      A string containing the HTML output.
    """

    try:
        with open(markdown_file, "r") as f:
            post = frontmatter.load(f)
    except FileNotFoundError:
        raise ValueError("Input file not found")

    # Extract front matter
    metadata = {
        "title": post.get("title", "title not present"),
        "abstract": post.get("abstract", "abstract not present"),
        "sotd": post.get("sotd", "sotd not present"),
    }

    # Convert Markdown to HTML
    latex = Latex()
    html = latex.run(post.content)
    html = markdown.markdown(html, extensions=["fenced_code", "tables"])
    # html = markdown2.markdown(post.content, extras=["fenced-code-blocks", "latex"])

    # Apply custom configuration
    if config.get("section_headers", False):
        html = apply_section_headers(html)

    return metadata, html


def apply_section_headers(html):
    """
    Wraps headers in <section> tags to create nested sections.

    Args:
      html: The HTML string to process.

    Returns:
      The modified HTML string with section tags.
    """

    # Simple implementation for demonstration
    # This could be more robust with a proper HTML parser
    lines = html.splitlines()
    new_lines = []
    section_level = 0

    for line in lines:
        if line.startswith("<h"):
            match = re.match(r"<h(\d)>", line)
            if match:
                level = int(match.group(1))  # Extract header level (h1, h2, etc.)
                if level > section_level:
                    new_lines.append("<section>")
                    section_level = level
                elif level < section_level:
                    new_lines.extend(["</section>"] * (section_level - level))
                    section_level = level
        new_lines.append(line)

    new_lines.extend(["</section>"] * section_level)  # Close remaining sections
    return "\n".join(new_lines)


def html_to_respec(metadata, html_content):
    metadata["spec"] = html_content
    with open(template_path, "r") as f:
        template_content = f.read()
    template = Template(template_content)
    return template.substitute(metadata)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path", help="markdown input file")
    parser.add_argument("--output_path", default="spec.html", help="HTML output file")
    args = parser.parse_args()

    # ensure that input path is a .md file
    if not args.input_path.endswith(".md"):
        raise ValueError("Input file must be a markdown file")

    # ensure that output path is a.html file
    if not args.output_path.endswith(".html"):
        raise ValueError("Output file must be an HTML file")

    # Example usage
    config = {"section_headers": True}  # Enable section headers

    metadata, html_inner = convert_markdown_to_html(args.input_path, config)
    html_output = html_to_respec(metadata, html_inner)

    print(html_output)


class Latex:
    _single_dollar_re = re.compile(r"(?<!\$)\$(?!\$)(.*?)\$")
    _double_dollar_re = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)

    # Ways to escape
    _pre_code_block_re = re.compile(r"<pre>(.*?)</pre>", re.DOTALL)  # Wraped in <pre>
    _triple_re = re.compile(r"```(.*?)```", re.DOTALL)  # Wrapped in a code block ```
    _single_re = re.compile(r"(?<!`)(`)(.*?)(?<!`)\1(?!`)")  # Wrapped in a single `

    converter = None
    code_blocks = {}

    def _convert_single_match(self, match):
        return self.converter.convert(match.group(1))

    def _convert_double_match(self, match):
        return self.converter.convert(
            match.group(1).replace(r"\n", ""), display="block"
        )

    def code_placeholder(self, match):
        placeholder = f"<!--CODE_BLOCK_{len(self.code_blocks)}-->"
        self.code_blocks[placeholder] = match.group(0)
        return placeholder

    def run(self, text):
        try:
            import latex2mathml.converter

            self.converter = latex2mathml.converter
        except ImportError:
            raise ImportError(
                'The "latex" extra requires the "latex2mathml" package to be installed.'
            )

        # Escape by replacing with a code block
        text = self._pre_code_block_re.sub(self.code_placeholder, text)
        text = self._single_re.sub(self.code_placeholder, text)
        text = self._triple_re.sub(self.code_placeholder, text)

        text = self._single_dollar_re.sub(self._convert_single_match, text)
        text = self._double_dollar_re.sub(self._convert_double_match, text)

        # Convert placeholder tag back to original code
        for placeholder, code_block in self.code_blocks.items():
            text = text.replace(placeholder, code_block)

        return text


if __name__ == "__main__":
    main()
