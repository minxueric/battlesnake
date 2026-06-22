"""Battlesnake - 贪心策略：BFS找最近食物 + 安全过滤（不撞墙/不撞身/避头碰头）。"""
import random
import typing
from collections import deque


def info() -> typing.Dict:
    return {
        "apiversion": "1",
        "author": "minxueric",
        "color": "#FF6600",
        "head": "pixel",
        "tail": "bolt",
    }


def start(game_state: typing.Dict):
    pass


def end(game_state: typing.Dict):
    pass


# ── 工具函数 ──────────────────────────────────────────

MOVES = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def in_bounds(pos, w, h):
    return 0 <= pos[0] < w and 0 <= pos[1] < h


def get_safe_moves(game_state):
    """返回不会立即死亡的方向列表。"""
    me = game_state["you"]
    head = (me["head"]["x"], me["head"]["y"])
    body_set = {(s["x"], s["y"]) for s in me["body"]}
    w = game_state["board"]["width"]
    h = game_state["board"]["height"]

    # 所有蛇的身体（不含尾，尾会让位——除非刚吃了食物）
    occupied = set()
    for snake in game_state["board"]["snakes"]:
        sbody = [(s["x"], s["y"]) for s in snake["body"]]
        # 保守：保留全身（包含尾），因为对手可能刚吃食物
        for seg in sbody:
            occupied.add(seg)

    # 对手头碰头危险区（≥我长的对手下一步可达格）
    my_len = me["length"]
    lethal = set()
    for snake in game_state["board"]["snakes"]:
        if snake["id"] == me["id"]:
            continue
        if snake["length"] >= my_len:
            ohead = (snake["head"]["x"], snake["head"]["y"])
            for d, (dx, dy) in MOVES.items():
                nb = add(ohead, (dx, dy))
                if in_bounds(nb, w, h):
                    lethal.add(nb)

    safe = []
    risky = []  # 在lethal中但不会立即死的
    for move, (dx, dy) in MOVES.items():
        nb = add(head, (dx, dy))
        if not in_bounds(nb, w, h):
            continue
        if nb in occupied:
            continue
        if nb in lethal:
            risky.append(move)
        else:
            safe.append(move)

    return safe if safe else risky


def bfs_nearest_food(game_state, allowed_moves):
    """BFS找最近食物，返回第一步方向。"""
    me = game_state["you"]
    head = (me["head"]["x"], me["head"]["y"])
    w = game_state["board"]["width"]
    h = game_state["board"]["height"]
    foods = {(f["x"], f["y"]) for f in game_state["board"]["food"]}

    if not foods or not allowed_moves:
        return None

    # 阻塞集
    occupied = set()
    for snake in game_state["board"]["snakes"]:
        for seg in snake["body"][:-1]:  # BFS时放开尾
            occupied.add((seg["x"], seg["y"]))

    visited = {head}
    queue = deque()
    # 从允许的第一步方向开始
    for move in allowed_moves:
        dx, dy = MOVES[move]
        nb = add(head, (dx, dy))
        if in_bounds(nb, w, h) and nb not in occupied and nb not in visited:
            visited.add(nb)
            queue.append((nb, move))

    while queue:
        pos, first_move = queue.popleft()
        if pos in foods:
            return first_move
        for d, (dx, dy) in MOVES.items():
            nb = add(pos, (dx, dy))
            if in_bounds(nb, w, h) and nb not in occupied and nb not in visited:
                visited.add(nb)
                queue.append((nb, first_move))

    return None


# ── 主决策 ──────────────────────────────────────────

def move(game_state: typing.Dict) -> typing.Dict:
    safe_moves = get_safe_moves(game_state)

    if not safe_moves:
        return {"move": "down"}

    # BFS找食物
    food_move = bfs_nearest_food(game_state, safe_moves)
    if food_move:
        next_move = food_move
    else:
        next_move = random.choice(safe_moves)

    return {"move": next_move}


if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})
