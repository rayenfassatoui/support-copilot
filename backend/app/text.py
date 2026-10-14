from html.parser import HTMLParser


class HTMLText(HTMLParser):
    def __init__(self, limit: int):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.length = 0
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head", "noscript"}:
            self.ignored += 1
        elif not self.ignored and tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "section"}:
            self.handle_data("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head", "noscript"}:
            self.ignored = max(0, self.ignored - 1)
        elif not self.ignored and tag in {"p", "div", "li", "tr", "section"}:
            self.handle_data("\n")

    def handle_data(self, data):
        if not self.ignored:
            self.length += len(data)
            if self.length > self.limit:
                raise OverflowError("extracted_text_too_large")
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())
