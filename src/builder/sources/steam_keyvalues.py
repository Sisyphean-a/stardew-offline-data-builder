from __future__ import annotations

from dataclasses import dataclass


class KeyValuesParseError(ValueError):
    pass


@dataclass(frozen=True)
class KeyValuesEntry:
    key: str
    value: str | KeyValuesObject


@dataclass(frozen=True)
class KeyValuesObject:
    entries: tuple[KeyValuesEntry, ...]


def parse_keyvalues(text: str) -> KeyValuesObject:
    return KeyValuesParser(tokenize_keyvalues(text)).parse_document()


def tokenize_keyvalues(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        index = skip_ignored(text, index)
        if index == len(text):
            break
        token, index = read_token(text, index)
        tokens.append(token)
    return tuple(tokens)


def skip_ignored(text: str, index: int) -> int:
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index)
            index = len(text) if newline == -1 else newline + 1
            continue
        return index
    return index


def read_token(text: str, index: int) -> tuple[str, int]:
    character = text[index]
    if character in "{}":
        return character, index + 1
    if character != '"':
        raise KeyValuesParseError(f"意外字符：{character}")
    return read_string(text, index + 1)


def read_string(text: str, index: int) -> tuple[str, int]:
    characters: list[str] = []
    while index < len(text):
        character = text[index]
        if character == '"':
            return "".join(characters), index + 1
        if character == "\\":
            escaped, index = read_escape(text, index)
            characters.append(escaped)
            continue
        if character in "\r\n":
            raise KeyValuesParseError("字符串未闭合")
        characters.append(character)
        index += 1
    raise KeyValuesParseError("字符串未闭合")


def read_escape(text: str, index: int) -> tuple[str, int]:
    escaped_index = index + 1
    if escaped_index == len(text) or text[escaped_index] not in {'"', "\\"}:
        raise KeyValuesParseError("无效转义")
    return text[escaped_index], escaped_index + 1


@dataclass
class KeyValuesParser:
    tokens: tuple[str, ...]
    index: int = 0

    def parse_document(self) -> KeyValuesObject:
        result = self.parse_entries(end_token=None)
        if self.index != len(self.tokens):
            raise KeyValuesParseError("存在未消费 token")
        return result

    def parse_entries(self, end_token: str | None) -> KeyValuesObject:
        entries: list[KeyValuesEntry] = []
        while self.index < len(self.tokens) and self.peek() != end_token:
            entries.append(self.parse_entry())
        if end_token is not None:
            self.expect(end_token)
        return KeyValuesObject(tuple(entries))

    def parse_entry(self) -> KeyValuesEntry:
        key = self.take_string()
        if self.peek() == "{":
            self.index += 1
            return KeyValuesEntry(key, self.parse_entries(end_token="}"))
        return KeyValuesEntry(key, self.take_string())

    def peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take_string(self) -> str:
        token = self.peek()
        if token is None or token in {"{", "}"}:
            raise KeyValuesParseError("期望字符串")
        self.index += 1
        return token

    def expect(self, token: str) -> None:
        if self.peek() != token:
            raise KeyValuesParseError(f"期望 {token}")
        self.index += 1
