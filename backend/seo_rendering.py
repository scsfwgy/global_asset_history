"""Route-aware HTML pruning for the classic single-page frontend.

The source document remains the canonical UI definition, while indexable
responses contain only the active route's panel, language, and JavaScript.
This gives crawlers focused server-rendered content without maintaining a
second set of templates.
"""

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit


_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


def _classes(attrs: dict[str, str | None]) -> set[str]:
    return set((attrs.get("class") or "").split())


def _serialize_start_tag(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    rendered = []
    for name, value in attrs:
        if value is None:
            rendered.append(name)
        else:
            rendered.append(f'{name}="{escape(value, quote=True)}"')
    suffix = (" " + " ".join(rendered)) if rendered else ""
    return f"<{tag}{suffix}>"


def _with_attr(
    attrs: list[tuple[str, str | None]], name: str, value: str | None
) -> list[tuple[str, str | None]]:
    updated = [(key, item) for key, item in attrs if key != name]
    if value is not None:
        updated.append((name, value))
    return updated


def _active_class(value: str | None, active: bool) -> str:
    classes = [item for item in (value or "").split() if item != "active"]
    if active:
        classes.append("active")
    return " ".join(classes)


def _is_sponsored_link(href: str) -> bool:
    lower = href.lower()
    return (
        "/referral/register" in lower
        or "invite_code=" in lower
        or "ref=" in urlsplit(href).query.lower()
    )


class _RouteDocumentPruner(HTMLParser):
    def __init__(
        self,
        *,
        primary_tab: str,
        kept_tabs: set[str],
        knowledge_panel_id: str | None,
        knowledge_subtab: str | None,
        knowledge_subtab_heading: str | None,
        active_tab_heading: str | None,
        allowed_local_scripts: set[str],
    ) -> None:
        super().__init__(convert_charrefs=False)
        self.primary_tab = primary_tab
        self.kept_tabs = kept_tabs
        self.knowledge_panel_id = knowledge_panel_id
        self.knowledge_subtab = knowledge_subtab
        self.knowledge_subtab_heading = knowledge_subtab_heading
        self.active_tab_heading = active_tab_heading
        self.allowed_local_scripts = allowed_local_scripts
        self.parts: list[str] = []
        self.output_stack: list[tuple[str, str]] = []
        self.skip_depth = 0
        self.replaced_content_tag: str | None = None
        self.replaced_content_text: str | None = None

    def _should_skip(self, tag: str, attrs: dict[str, str | None]) -> bool:
        classes = _classes(attrs)
        element_id = attrs.get("id") or ""
        if "tab-panel" in classes and element_id.startswith("tab-"):
            return element_id[4:] not in self.kept_tabs
        if "kb-sub-panel" in classes:
            return element_id != self.knowledge_panel_id
        if tag == "script":
            src = attrs.get("src") or ""
            if src.startswith("/js/"):
                script_name = src.split("?", 1)[0].rsplit("/", 1)[-1]
                return script_name not in self.allowed_local_scripts
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        if self.skip_depth:
            if lower_tag not in _VOID_TAGS:
                self.skip_depth += 1
            return

        attrs_dict = dict(attrs)
        if self._should_skip(lower_tag, attrs_dict):
            if lower_tag not in _VOID_TAGS:
                self.skip_depth = 1
            return

        classes = _classes(attrs_dict)
        output_tag = lower_tag
        updated_attrs = list(attrs)

        # The server has already emitted authoritative route metadata. Client
        # SPA helpers must not replace it with a fallback title/canonical.
        if lower_tag == "html":
            updated_attrs = _with_attr(updated_attrs, "data-route-focused", "true")

        # The global product name is branding, not the page's primary heading.
        if lower_tag == "h1":
            output_tag = "div"
            updated_attrs = _with_attr(updated_attrs, "class", "site-brand-name")

        if lower_tag == "a" and "tab-btn" in classes:
            active = attrs_dict.get("data-tab") == self.primary_tab
            updated_attrs = _with_attr(
                updated_attrs, "class", _active_class(attrs_dict.get("class"), active)
            )
            updated_attrs = _with_attr(
                updated_attrs, "aria-current", "page" if active else None
            )
            if active and self.active_tab_heading:
                output_tag = "h1"
                updated_attrs = _with_attr(updated_attrs, "href", None)
                updated_attrs = _with_attr(updated_attrs, "data-i18n", None)
                updated_attrs = _with_attr(updated_attrs, "id", "seo-page-title")
                self.replaced_content_tag = lower_tag
                self.replaced_content_text = self.active_tab_heading

        if lower_tag == "a" and "transfer-tab" in classes and attrs_dict.get("data-kb-tab"):
            active = attrs_dict.get("data-kb-tab") == self.knowledge_subtab
            updated_attrs = _with_attr(
                updated_attrs, "class", _active_class(attrs_dict.get("class"), active)
            )
            updated_attrs = _with_attr(
                updated_attrs, "aria-current", "page" if active else None
            )
            # Knowledge routes use their existing active subtab as the page
            # heading. This keeps the navigation visually unchanged while
            # avoiding a second, injected article-title block above the body.
            if active and self.knowledge_subtab_heading:
                output_tag = "h1"
                updated_attrs = _with_attr(updated_attrs, "href", None)
                updated_attrs = _with_attr(updated_attrs, "data-i18n", None)
                updated_attrs = _with_attr(updated_attrs, "aria-current", None)
                updated_attrs = _with_attr(updated_attrs, "id", "seo-page-title")
                self.replaced_content_tag = lower_tag
                self.replaced_content_text = self.knowledge_subtab_heading

        if "tab-panel" in classes:
            panel_tab = (attrs_dict.get("id") or "")[4:]
            active = panel_tab == self.primary_tab
            updated_attrs = _with_attr(
                updated_attrs, "class", _active_class(attrs_dict.get("class"), active)
            )
            if panel_tab in self.kept_tabs and not active:
                updated_attrs = _with_attr(updated_attrs, "data-seo-donor", "true")

        if "kb-sub-panel" in classes:
            output_tag = "article"
            updated_attrs = _with_attr(
                updated_attrs, "class", _active_class(attrs_dict.get("class"), True)
            )
            updated_attrs = _with_attr(updated_attrs, "style", None)
            updated_attrs = _with_attr(updated_attrs, "aria-labelledby", "seo-page-title")

        href = attrs_dict.get("href") or ""
        if lower_tag == "a" and _is_sponsored_link(href):
            updated_attrs = _with_attr(
                updated_attrs, "rel", "sponsored nofollow noopener noreferrer"
            )

        self.parts.append(_serialize_start_tag(output_tag, updated_attrs))
        if lower_tag not in _VOID_TAGS:
            self.output_stack.append((lower_tag, output_tag))
        if self.replaced_content_tag == lower_tag:
            self.parts.append(escape(self.replaced_content_text or ""))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip_depth:
            return
        self.parts.append(_serialize_start_tag(tag.lower(), attrs)[:-1] + "/>")

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if self.skip_depth:
            self.skip_depth -= 1
            return
        output_tag = lower_tag
        if self.output_stack:
            original, mapped = self.output_stack.pop()
            output_tag = mapped if original == lower_tag else lower_tag
        self.parts.append(f"</{output_tag}>")
        if self.replaced_content_tag == lower_tag:
            self.replaced_content_tag = None
            self.replaced_content_text = None

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and not self.replaced_content_tag:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self.skip_depth and not self.replaced_content_tag:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.skip_depth and not self.replaced_content_tag:
            self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        if not self.skip_depth:
            self.parts.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(f"<![{data}]>")


def prune_route_document(
    html_text: str,
    *,
    primary_tab: str,
    kept_tabs: set[str],
    knowledge_panel_id: str | None,
    knowledge_subtab: str | None,
    knowledge_subtab_heading: str | None,
    active_tab_heading: str | None,
    allowed_local_scripts: set[str],
) -> str:
    """Return a focused, still-interactive document for one public route."""
    parser = _RouteDocumentPruner(
        primary_tab=primary_tab,
        kept_tabs=kept_tabs,
        knowledge_panel_id=knowledge_panel_id,
        knowledge_subtab=knowledge_subtab,
        knowledge_subtab_heading=knowledge_subtab_heading,
        active_tab_heading=active_tab_heading,
        allowed_local_scripts=allowed_local_scripts,
    )
    parser.feed(html_text)
    parser.close()
    return "".join(parser.parts)
