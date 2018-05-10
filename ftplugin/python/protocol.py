from contextlib import contextmanager
import re


FULL_UPDATE_PREFIX = 'VIMPAIR_FULL_UPDATE'
UPDATE_START_PREFIX = 'VIMPAIR_CONTENTS_START'
UPDATE_PART_PREFIX = 'VIMPAIR_CONTENTS_PART'
UPDATE_END_PREFIX = 'VIMPAIR_CONTENTS_END'
CURSOR_POSITION_PREFIX = 'VIMPAIR_CURSOR_POSITION'

MESSAGE_LENGTH = 1024
_LENGTH_DIGITS_AND_MARKERS = 3 + 2
_NUM_MARKERS = 2
_UPDATE_START_CONTENTS_LENGTH = \
    MESSAGE_LENGTH - len(UPDATE_START_PREFIX) - _LENGTH_DIGITS_AND_MARKERS
_UPDATE_PART_CONTENTS_LENGTH = \
    MESSAGE_LENGTH - len(UPDATE_PART_PREFIX) - _LENGTH_DIGITS_AND_MARKERS

_noop = lambda *a, **k: None
_ensure_callable = lambda call: call if callable(call) else _noop

def generate_contents_update_messages(contents):

    contents_length = len(contents or '')

    def get_number_of_parts(contents):
        length_without_start = contents_length - _UPDATE_START_CONTENTS_LENGTH
        return 1 \
            + length_without_start // _UPDATE_PART_CONTENTS_LENGTH \
            + int(0 < length_without_start % _UPDATE_PART_CONTENTS_LENGTH)

    def get_part_prefix(index, num_parts):
        if num_parts > 1:
            prefixes = num_parts * [UPDATE_PART_PREFIX]
            prefixes[0] = UPDATE_START_PREFIX
            prefixes[-1] = UPDATE_END_PREFIX
            return prefixes[index]
        return FULL_UPDATE_PREFIX

    def get_part_size(contents_size, index, num_parts):
        first_part_size = min(_UPDATE_START_CONTENTS_LENGTH, contents_size)
        if num_parts > 1:
            sizes = num_parts * [_UPDATE_PART_CONTENTS_LENGTH]
            sizes[0] = first_part_size
            sizes[-1] = (contents_size - _UPDATE_START_CONTENTS_LENGTH) \
                    % _UPDATE_PART_CONTENTS_LENGTH
            return sizes[index]
        return first_part_size

    messages = []
    if contents:
        num_parts = get_number_of_parts(contents)
        for index in xrange(0, num_parts):
            prefix = get_part_prefix(index, num_parts)
            part_size = get_part_size(contents_length, index, num_parts)
            part_contents = contents[:part_size]
            messages.append('%s|%d|%s' % (prefix, part_size, part_contents))
            contents = contents[part_size:]
    return messages

def generate_cursor_position_message(line, column):
    line = max(0, line or 0)
    column = max(0, column or 0)
    return '%s|%d|%d' % (CURSOR_POSITION_PREFIX, line, column)


class MessageHandler(object):

    def __init__(self, update_contents=None, apply_cursor_position=None):
        self._current_message = ''
        self._pending_update = None
        self._update_contents = _ensure_callable(update_contents)
        self._apply_cursor_position = _ensure_callable(apply_cursor_position)

    def _remove_from_message(self, string):
        self._current_message = self._current_message.replace(string, '')

    @contextmanager
    def _find_match(self, expression):
        match = re.search(expression, self._current_message, re.DOTALL)
        yield match.groups() if match else None

    @contextmanager
    def _find_length_and_contents(self, expression):
        with self._find_match(expression) as groups:
            length = int(groups[0]) if groups else None
            contents = groups[1][:length] if groups else None
            yield length, contents

    def _contents_update(self):
        pattern = '%s\|(\d+)\|(.*)' % FULL_UPDATE_PREFIX
        with self._find_length_and_contents(pattern) as (length, contents):
            if contents != None:
                self._pending_update = None
                self._remove_from_message(
                    '%s|%d|%s' % (FULL_UPDATE_PREFIX, length, contents)
                )
                if length <= len(contents):
                    self._update_contents(contents)
            return contents != None

    def _contents_start(self):
        pattern = '%s\|(\d+)\|(.*)' % UPDATE_START_PREFIX
        with self._find_length_and_contents(pattern) as (length, contents):
            if contents != None:
                self._remove_from_message(
                    '%s|%d|%s' % (UPDATE_START_PREFIX, length, contents)
                )
                self._pending_update = contents
            return contents != None

    def _contents_part(self):
        pattern = '%s\|(\d+)\|(.*)' % UPDATE_PART_PREFIX
        with self._find_length_and_contents(pattern) as (length, contents):
            if contents != None:
                self._remove_from_message(
                    '%s|%d|%s' % (UPDATE_PART_PREFIX, length, contents)
                )
                if self._pending_update:
                    self._pending_update += contents[:length]
            return contents != None

    def _contents_end(self):
        pattern = '%s\|(\d+)\|(.*)' % UPDATE_END_PREFIX
        with self._find_length_and_contents(pattern) as (length, contents):
            if contents != None:
                self._remove_from_message(
                    '%s|%d|%s' % (UPDATE_END_PREFIX, length, contents)
                )
                if self._pending_update:
                    self._update_contents(self._pending_update + contents)
                self._pending_update = None
            return contents != None

    def _cursor_position(self):
        pattern = '%s\|(\d+)\|(\d+)' % CURSOR_POSITION_PREFIX
        with self._find_match(pattern) as group:
            if group != None:
                line = int(group[0])
                column = int(group[1])
                self._remove_from_message(
                    '%s|%d|%d' % (CURSOR_POSITION_PREFIX, line, column)
                )
                self._apply_cursor_position(line, column)
                self._pending_update = None
            return group != None

    def process(self, message):
        if message:
            self._current_message = message
            for processing_call in (
                self._contents_update,
                self._cursor_position,
                self._contents_start,
                self._contents_part,
                self._contents_end,
            ):
                while processing_call():
                    pass
            self._current_message = ''
