import contextlib
import difflib
import functools
import logging
import time

import requests
from mopidy import httpclient

from mopidy_spotify import Extension, __version__

logger = logging.getLogger(__name__)
TRACE = logging.getLevelName("TRACE")


def get_requests_session(proxy_config):
    user_agent = f"{Extension.dist_name}/{__version__}"
    proxy = httpclient.format_proxy(proxy_config)
    full_user_agent = httpclient.format_user_agent(user_agent)

    session = requests.Session()
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({"user-agent": full_user_agent})

    return session


@contextlib.contextmanager
def time_logger(name, level=TRACE):
    start = time.time()
    yield
    end = time.time() - start
    logger.log(level, f"{name} took {int(end * 1000)}ms")


def flatten(list_of_lists):
    return [item for sublist in list_of_lists for item in sublist]


class op:
    def __init__(self, op, tracks, frm, to=0):
        self.op = op
        self.tracks = tracks
        self.frm = frm
        self.to = to

    def __repr__(self):
        length = len(self.tracks)
        if length < 1:
            return "<invalid op()>"
        first = self.tracks[0].split(":")[-1]
        last = self.tracks[-1].split(":")[-1]
        tracks = f"{first}...{last}" if length > 1 else first
        action = {"-": "delete", "+": "insert", "m": "move"}
        pos = f"{self.frm} to {self.to}" if self.op == "m" else self.frm
        return f"<{action.get(self.op)} {length} tracks [{tracks}] at {pos}>"


def _is_move(op1, op2):
    return op1.op == "-" and op2.op == "+" and op1.tracks == op2.tracks


def _op_split(o, chunksize):
    def partition(o, n):
        def inc(m, i):
            return m + i if o.op == "-" or o.op == "m" else m

        for i in range(0, len(o.tracks), n):
            yield op(o.op, o.tracks[i : i + n], inc(o.frm, i), inc(o.to, i))

    return list(partition(o, chunksize)) if o.op != "m" else [o]


def diff(old, new, chunksize=100):
    # first, apply python's built-in diff algorithm, remove unmodified ranges,
    # split replacements into seperate insertions and deletions and transform
    # the data structure into op-objects:
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        a=old, b=new, autojunk=False
    ).get_opcodes():
        if tag in ("insert", "replace"):
            ops.append(op("+", new[j1:j2], i1))
        if tag in ("delete", "replace"):
            ops.append(op("-", old[i1:i2], i1))

    # then, merge pairs of insertions and deletions into a transposition:
    # for this, we start from the rightmost element and ...
    for R in reversed(range(len(ops))):
        # ..., unless we already worked on this element, ...
        if ops[R].op == "m":
            continue
        # ... compare against all elements on its left
        for L in reversed(range(R)):
            # if we found a pair of ins/del that can be combined,
            if _is_move(ops[R], ops[L]) or _is_move(ops[L], ops[R]):
                # replace the left item with a mov
                del_at = ops[L].frm if ops[L].op == "-" else ops[R].frm
                ins_at = ops[L].frm if ops[L].op == "+" else ops[R].frm
                ops[L] = op("m", ops[L].tracks, del_at, ins_at)
                # and delete the right one (this is why we go right-to-left)
                del ops[R]
                break  # check the next outer element

    # finally, split add/del ops to work on <= 100 tracks (but not mov ops):
    ops = functools.reduce(lambda xs, x: xs + _op_split(x, chunksize), ops, [])

    return ops
