"""Strict Semantic Version precedence (build metadata does not affect ordering)."""
from functools import total_ordering
import re

PATTERN = re.compile(r'^[vV]?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
                     r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
                     r'(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$')


@total_ordering
class SemVer:
    def __init__(self, value):
        match = PATTERN.fullmatch(str(value).strip())
        if not match:
            raise ValueError('버전은 Semantic Version 형식이어야 합니다.')
        self.core = tuple(map(int, match.groups()[:3]))
        self.pre = tuple((match.group(4) or '').split('.')) if match.group(4) else ()
        if any(s.isdigit() and len(s) > 1 and s[0] == '0' for s in self.pre):
            raise ValueError('사전 릴리스 숫자에는 앞자리 0을 사용할 수 없습니다.')

    def __eq__(self, other):
        return isinstance(other, SemVer) and (self.core, self.pre) == (other.core, other.pre)

    def __lt__(self, other):
        if not isinstance(other, SemVer):
            return NotImplemented
        if self.core != other.core:
            return self.core < other.core
        if not self.pre or not other.pre:
            return bool(self.pre) and not other.pre
        for a, b in zip(self.pre, other.pre):
            if a == b:
                continue
            if a.isdigit() and b.isdigit():
                return int(a) < int(b)
            if a.isdigit() != b.isdigit():
                return a.isdigit()
            return a < b
        return len(self.pre) < len(other.pre)
