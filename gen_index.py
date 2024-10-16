import os
import frontmatter
from jinja2 import Environment, FileSystemLoader
from datetime import datetime  # Import datetime


def generate_rfc_page():
    """
    Generates an HTML page listing RFC documents using Jinja2 templating.
    """

    rfcs = []
    for root, _, files in os.walk("source/"):
        for file in files:
            if file.endswith(".md"):
                filepath = os.path.join(root, file)
                with open(filepath, "r") as f:
                    post = frontmatter.load(f)
                    # Get last modified date of the file
                    last_modified = os.path.getmtime(filepath)
                    rfcs.append(
                        {
                            "title": post.get("title"),
                            "abstract": post.get("abstract"),
                            "sotd": post.get("sotd"),
                            "shortName": post.get("shortName"),
                            "editor": post.get("editor"),
                            "link": filepath.replace("source/", "rfcs/").replace(
                                ".md", ".html"
                            ),
                            "updated": datetime.fromtimestamp(last_modified).strftime(
                                "%B %d, %Y"
                            ),
                        }
                    )

    # Setup Jinja2 environment
    env = Environment(loader=FileSystemLoader("."))
    template = env.get_template("index_template.html")

    # Render the template with the RFC data
    html = template.render(rfcs=rfcs)

    with open("index.html", "w") as f:
        f.write(html)


if __name__ == "__main__":
    generate_rfc_page()
