"""Dead-simple XML implementation."""

from typing import List, Dict


class XML:
    """An XML node."""

    def __init__(
            self,
            name: str,
            properties: Dict[str, str] = {},
            children: List['XML'] = [],
            content: str = ''
    ):
        """Create a new XML node."""
        self.name = name
        self.properties = properties
        self.children = children
        self.content = content

    def set(self, key: str, value: str) -> 'XML':
        """Set a property."""
        self.properties[key] = value
        return self

    def append(self, child: 'XML') -> 'XML':
        """Append a child node."""
        self.children.append(child)
        return self

    def write(self, text: str) -> 'XML':
        """Write text to the body of the node."""
        self.content += text
        return self

    def __str__(self) -> str:
        """Dump the XML node as text."""
        return (
            f'<{self.name}' +
            ''.join([
                f' {k}="{self.properties[k]}"'
                for k in self.properties
            ]) +
            '>' +
            ''.join([
                str(child)
                for child in self.children
            ]) +
            self.content +
            f'</{self.name}>'
        )

    def human_readable(self, indent: int = 0) -> str:
        """Dump the XML node as human-readable."""
        return (
            f'{" " * indent}' +
            f'<{self.name}' +
            ''.join([
                f' {k}="{self.properties[k]}"'
                for k in self.properties
            ]) +
            '>\n' +
            ''.join([
                child.human_readable(indent + 2)
                for child in self.children
            ]) +
            (
                f'{" " * (indent + 2)}' +
                self.content +
                '\n'
                if self.content != '' else ''
            ) +
            f'{" " * indent}' +
            f'</{self.name}>\n'
        )
