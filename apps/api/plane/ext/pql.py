# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A subset of Plane Query Language (PQL), compiled to a Django Q over work items."""

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from plane.db.models import Issue, IssueAssignee, IssueLabel
from plane.ext.models import WorkItemStep


class PQLError(ValueError):
    """The query can't be parsed or uses something outside the subset; the message says what."""


@dataclass
class Context:
    user_id: uuid.UUID
    workspace_slug: str


TOKEN = re.compile(
    r"""\s*(?:
        (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
      | (?P<number>-?\d+)
      | (?P<op>!=|<=|>=|=|<|>|~)
      | (?P<punct>[(),])
      | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
    )""",
    re.VERBOSE,
)

KEYWORDS = {"AND", "OR", "NOT", "IN", "IS", "NULL", "TRUE", "FALSE"}

STATE_GROUPS = ("backlog", "unstarted", "started", "completed", "cancelled")
PRIORITIES = ("urgent", "high", "medium", "low", "none")

# functions that stand for a value or a list of values
LIST_FUNCTIONS = {
    "openStates": ["backlog", "unstarted", "started"],
    "closedStates": ["completed", "cancelled"],
    "activeStates": ["unstarted", "started"],
}
DAY_FUNCTIONS = {"daysAgo": -1, "daysFromNow": 1}

COMPARE = {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}
MAX_DEPTH = 50  # nested ( and NOT; deeper is refused before Python's recursion limit


def tokenize(text):
    tokens, pos = [], 0
    text = text.rstrip()
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if not match:
            raise PQLError(f"unexpected character {text[pos:].strip()[:1]!r} at position {pos}")
        kind = match.lastgroup
        value = match.group(kind)
        if kind == "word" and value.upper() in KEYWORDS:
            kind, value = "keyword", value.upper()
        elif kind == "string":
            value = re.sub(r"\\(.)", r"\1", value[1:-1])
        tokens.append((kind, value))
        pos = match.end()
    return tokens


# fields: PQL name -> (kind, ORM lookup or relation model)
SCALAR = {
    "priority": "priority",
    "stateGroup": "state__group",
    "state": "state_id",
    "createdBy": "created_by_id",
    "project": "project_id",
    "parent": "parent_id",
}
UUID_FIELDS = {"state", "createdBy", "project", "parent", "stepActor"}
TEXT = {"title": "name"}
DATES = {"dueDate": "target_date", "startDate": "start_date", "createdAt": "created_at", "updatedAt": "updated_at"}
DATETIMES = {"createdAt", "updatedAt"}
# multi-valued: matched through an Exists on the link table, so NOT and != stay exact
LINKS = {"assignee": (IssueAssignee, "assignee_id"), "label": (IssueLabel, "label_id")}
# matched on the item's current step (see FORK.md, Steps)
STEP = {"stepActor"}
FIELDS = set(SCALAR) | set(TEXT) | set(DATES) | set(LINKS) | STEP


def on_current_step(**filters):
    """Items whose current step (first pending or failed, in path order) matches filters."""
    tied = {"sort_order": OuterRef("sort_order")}
    earlier = WorkItemStep.objects.filter(issue_id=OuterRef("issue_id"), status__in=WorkItemStep.OPEN).filter(
        Q(sort_order__lt=OuterRef("sort_order"))
        | Q(**tied, created_at__lt=OuterRef("created_at"))
        | Q(**tied, created_at=OuterRef("created_at"), id__lt=OuterRef("id"))
    )
    steps = WorkItemStep.objects.filter(issue_id=OuterRef("pk"), status__in=WorkItemStep.OPEN, **filters)
    return Q(Exists(steps.exclude(Exists(earlier))))


class Parser:
    def __init__(self, text, context):
        self.tokens = tokenize(text)
        self.pos = 0
        self.depth = 0
        self.context = context

    # token helpers
    def peek(self, offset=0):
        index = self.pos + offset
        return self.tokens[index] if index < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        if token[0] is None:
            raise PQLError("the query ends too early")
        self.pos += 1
        return token

    def accept(self, kind, value=None):
        token = self.peek()
        if token[0] == kind and (value is None or token[1] == value):
            self.pos += 1
            return True
        return False

    def expect(self, kind, value):
        if not self.accept(kind, value):
            got = self.peek()[1]
            raise PQLError(f"expected {value!r}" + (f", got {got!r}" if got is not None else " at the end"))

    # grammar: or > and > not > primary
    def parse(self):
        if not self.tokens:
            raise PQLError("the query is empty")
        q = self.parse_or()
        if self.peek()[0] is not None:
            raise PQLError(f"unexpected {self.peek()[1]!r}")
        return q

    def parse_or(self):
        q = self.parse_and()
        while self.accept("keyword", "OR"):
            q = q | self.parse_and()
        return q

    def parse_and(self):
        q = self.parse_not()
        while self.accept("keyword", "AND"):
            q = q & self.parse_not()
        return q

    def parse_not(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise PQLError(f"the query nests ( or NOT more than {MAX_DEPTH} deep")
        try:
            if self.accept("keyword", "NOT"):
                return ~self.parse_not()
            return self.parse_primary()
        finally:
            self.depth -= 1

    def parse_primary(self):
        if self.accept("punct", "("):
            q = self.parse_or()
            self.expect("punct", ")")
            return q
        kind, name = self.take()
        if kind != "word":
            raise PQLError(f"expected a field or function, got {name!r}")
        if self.peek() == ("punct", "("):
            return self.predicate(name)
        if name not in FIELDS:
            raise PQLError(f"unsupported field {name!r}; supported: {', '.join(sorted(FIELDS))}")
        return self.comparison(name)

    def comparison(self, field):
        if self.accept("keyword", "IS"):
            negate = self.accept("keyword", "NOT")
            self.expect("keyword", "NULL")
            if negate and field in STEP:  # a current step with an actor, not "no current step without one"
                return on_current_step(actor__isnull=False)
            q = self.is_null(field)
            return ~q if negate else q
        if self.accept("keyword", "NOT"):
            self.expect("keyword", "IN")
            return ~self.match(field, self.values(field))
        if self.accept("keyword", "IN"):
            return self.match(field, self.values(field))
        kind, op = self.take()
        if kind != "op":
            raise PQLError(f"expected an operator after {field!r}, got {op!r}")
        if op == "~":
            if field not in TEXT:
                raise PQLError(f"'~' works on {', '.join(TEXT)} only, not {field!r}")
            return Q(**{f"{TEXT[field]}__icontains": self.text_value()})
        if op in COMPARE:
            if field not in DATES:
                raise PQLError(f"{op!r} works on date fields only ({', '.join(DATES)}), not {field!r}")
            return Q(**{f"{self.date_lookup(field)}__{COMPARE[op]}": self.date_value()})
        if field in DATES:
            q = Q(**{self.date_lookup(field): self.date_value()})
        else:
            q = self.match(field, self.value_or_list(field))
        return ~q if op == "!=" else q

    # values
    def values(self, field):
        """A parenthesised list, or a function that stands for one."""
        if self.accept("punct", "("):
            items = [self.value(field)]
            while self.accept("punct", ","):
                items.append(self.value(field))
            self.expect("punct", ")")
            return [v for item in items for v in (item if isinstance(item, list) else [item])]
        value = self.value(field)
        return value if isinstance(value, list) else [value]

    def value_or_list(self, field):
        value = self.value(field)
        return value if isinstance(value, list) else [value]

    def value(self, field):
        kind, value = self.take()
        if kind == "string":
            return self.check(field, value)
        if kind == "word" and self.peek() == ("punct", "("):
            self.expect("punct", "(")
            self.expect("punct", ")")
            if value == "currentUser":
                if field not in ("assignee", "createdBy", "stepActor"):
                    raise PQLError(f"currentUser() fits assignee, createdBy or stepActor, not {field!r}")
                return str(self.context.user_id)
            if value in LIST_FUNCTIONS:
                if field != "stateGroup":
                    raise PQLError(f"{value}() fits stateGroup only, not {field!r}")
                return list(LIST_FUNCTIONS[value])
            raise PQLError(f"unsupported function {value}()")
        raise PQLError(f"expected a quoted value for {field!r}, got {value!r}")

    def text_value(self):
        kind, value = self.take()
        if kind != "string":
            raise PQLError(f"expected a quoted text, got {value!r}")
        return value

    def check(self, field, value):
        if field in UUID_FIELDS or field in LINKS:
            try:
                return str(uuid.UUID(value))
            except ValueError:
                raise PQLError(f"{field} takes a UUID, not {value!r}") from None
        if field == "stateGroup" and value not in STATE_GROUPS:
            raise PQLError(f"stateGroup is one of {', '.join(STATE_GROUPS)}, not {value!r}")
        if field == "priority" and value not in PRIORITIES:
            raise PQLError(f"priority is one of {', '.join(PRIORITIES)}, not {value!r}")
        return value

    def date_lookup(self, field):
        return DATES[field] + ("__date" if field in DATETIMES else "")

    def date_value(self):
        kind, value = self.take()
        if kind == "string":
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise PQLError(f"dates are YYYY-MM-DD, not {value!r}") from None
        if kind == "word" and value == "today":
            self.expect("punct", "(")
            self.expect("punct", ")")
            return timezone.localdate()
        if kind == "word" and value in DAY_FUNCTIONS:
            self.expect("punct", "(")
            sign_kind, days = self.take()
            if sign_kind != "number":
                raise PQLError(f"{value}() takes a whole number of days")
            self.expect("punct", ")")
            try:
                return timezone.localdate() + timedelta(days=DAY_FUNCTIONS[value] * int(days))
            except (OverflowError, ValueError):
                raise PQLError(f"{value}({days}) is out of the date range") from None
        raise PQLError(f"expected a date for comparison, got {value!r}")

    # conditions
    def match(self, field, values):
        if field in DATES or field in TEXT:
            raise PQLError(f"IN doesn't work on {field!r}")
        if field in STEP:
            return on_current_step(actor_id__in=values)
        if field in LINKS:
            model, column = LINKS[field]
            return Q(Exists(model.objects.filter(issue_id=OuterRef("pk"), **{f"{column}__in": values})))
        return Q(**{f"{SCALAR[field]}__in": values})

    def is_null(self, field):
        if field in STEP:
            return on_current_step(actor__isnull=True)
        if field in LINKS:
            model, _ = LINKS[field]
            return ~Q(Exists(model.objects.filter(issue_id=OuterRef("pk"))))
        if field in TEXT:
            raise PQLError(f"IS NULL doesn't work on {field!r}")
        lookup = DATES.get(field) or SCALAR[field]
        return Q(**{f"{lookup}__isnull": True})

    def predicate(self, name):
        self.expect("punct", "(")
        if name in ("hasNoAssignee", "hasNoLabel", "isTopLevel"):
            self.expect("punct", ")")
            field = {"hasNoAssignee": "assignee", "hasNoLabel": "label", "isTopLevel": "parent"}[name]
            return self.is_null(field)
        if name == "childOf":
            kind, ref = self.take()
            if kind != "string":
                raise PQLError('childOf() takes a quoted work item id, e.g. childOf("SQUAD-5")')
            self.expect("punct", ")")
            return Q(parent_id=self.resolve(ref))
        raise PQLError(f"unsupported function {name}()")

    def resolve(self, ref):
        """A work item UUID or KEY-N identifier -> its id; an unknown one matches nothing."""
        try:
            return uuid.UUID(ref)
        except ValueError:
            pass
        match = re.fullmatch(r"([A-Za-z0-9]+)-(\d+)", ref)
        if not match:
            raise PQLError(f"childOf() takes a work item id like SQUAD-5 or a UUID, not {ref!r}")
        found = (
            Issue.objects.filter(
                workspace__slug=self.context.workspace_slug,
                project__identifier__iexact=match.group(1),
                sequence_id=int(match.group(2)),
            )
            .values_list("id", flat=True)
            .first()
        )
        return found or uuid.UUID(int=0)


def compile_pql(text, context):
    """PQL text -> Q over Issue; raises PQLError naming what isn't supported."""
    return Parser(text, context).parse()
