import collections
import contextlib
import functools
import itertools
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
        l = len(self.tracks)
        first = self.tracks[0].split(":")[-1]
        last = self.tracks[-1].split(":")[-1]
        tracks = f"{first}...{last}" if l > 1 else first
        action = {"-":"delete","+":"insert","m":"move"}
        pos = f"{self.frm} to {self.to}" if self.op == 'm' else self.frm
        return f'<{action.get(self.op)} {l} tracks [{tracks}] at {pos}>'


def myers(old, new):
    """
    Myers diff implementation adapted from Robert Elder (ASL-2.0)
    https://blog.robertelder.org/diff-algorithm/
    Instead of returning the number of edit operations, this returns an edit
    history with each element tagged as '='(same), '+'(inserted), '-'(removed).
    """
    N = len(old)
    M = len(new)
    MAX = N + M

    V_SIZE = 2*min(N,M) + 2
    V = [None] * V_SIZE
    V[1] = (0, [])  # x, history
    for D in range(0, MAX + 1):
        for k in range(-(D - 2*max(0, D-M)), D - 2*max(0, D-N) + 1, 2):
            down = k == -D or k != D and V[(k - 1) % V_SIZE][0] < V[(k + 1) % V_SIZE][0]
            if down:
                x, hist = V[(k + 1) % V_SIZE]
            else:
                x, hist = V[(k - 1) % V_SIZE]
                x += 1
            hist = hist[:] # copy
            y = x - k

            # Note: Myers' algorithm is one-indexed, but our lists are
            # zero-indexed. Hence, we have to use x-1 to get the index we
            # actually want. Except in the case for '+', as when inserting the
            # "old" index (x) is lagging behind by 1.
            if down and y <= M and 1 <= y:
                hist.append(op('+', new[y-1], x))
            elif x <= N and 1 <= x:
                hist.append(op('-', old[x-1], x-1))

            while x < N and y < M and old[x] == new[y]:
                x = x + 1
                y = y + 1
                hist.append(op('=', old[x-1], x-1))
            V[k % V_SIZE] = (x, hist)
            if x == N and y == M:
                return hist


def _is_move(op1, op2):
    return op1.op == '-' and op2.op == '+' and op1.tracks == op2.tracks


def _op_split(o, chunksize):
    def partition(o, n):
        for i in range(0, len(o.tracks), n):
            inc = lambda m: m+i if o.op == '-' or o.op == 'm' else m
            yield op(o.op, o.tracks[i:i+n], inc(o.frm), inc(o.to))

    return list(partition(o, chunksize)) if o.op != 'm' else [o]


def diff(old, new, chunksize=100):
    # first, apply myers diff and group consecutive operations into ranges:
    ops = itertools.groupby(myers(old, new), lambda x: x.op)

    # then, remove unmodified ranges and transform groupby-iterators to lists:
    ops = [(k,list(v)) for k,v in ops if k != '=']

    # now, reorder the data structure to ressemble op-tuples again: [ op, [tracks], from, to ]
    ops = [op(k, [v.tracks for v in v], v[0].frm, v[0].to) for k,v in ops]

    # then, merge pairs of insertions and deletions into a transposition:
    # for this, we start from the rightmost element,
    for r in reversed(range(len(ops))):
        # and compare against all elements on its left
        for l in reversed(range(r)):
            # if we found a pair of ins/del that can be combined,
            if _is_move(ops[r], ops[l]) or _is_move(ops[l], ops[r]):
                # replace the left item with a mov
                del_at = ops[l].frm if ops[l].op == '-' else ops[r].frm
                ins_at = ops[l].frm if ops[l].op == '+' else ops[r].frm
                ops[l] = op('m', ops[l].tracks, del_at, ins_at)
                # and delete the right one (this is why we go right-to-left)
                del ops[r]
                break  # check the next outer element

    # finally, split add/del ops to work on <= 100 tracks (but not mov ops):
    ops = functools.reduce(lambda xs, x: xs + _op_split(x, chunksize), ops, [])

    return ops
