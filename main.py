"""
Battlesnake 竞赛级 AI
策略：Minimax + Alpha-Beta 剪枝 + Flood Fill 空间评估
包含：安全移动过滤、空间控制、追尾、头碰头击杀、食物策略
"""
import random
import typing
import time
from collections import deque
from copy import deepcopy


# ══════════════════════════════════════════════════════════════
# API 元信息
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
# 常量与工具
# ══════════════════════════════════════════════════════════════

MOVES = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
MOVE_LIST = ["up", "down", "left", "right"]

# 搜索时间预算(秒) — 留 50ms 网络余量
TIME_BUDGET = 0.35


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ══════════════════════════════════════════════════════════════
# 游戏状态轻量表示（用于 Minimax 快速模拟）
# ══════════════════════════════════════════════════════════════

class GameState:
    """精简的游戏状态，用于搜索树中快速复制和模拟。"""

    __slots__ = ['width', 'height', 'snakes', 'food', 'my_id']

    def __init__(self, game_state: dict = None):
        if game_state is None:
            return
        board = game_state["board"]
        self.width = board["width"]
        self.height = board["height"]
        self.food = frozenset((f["x"], f["y"]) for f in board["food"])
        self.my_id = game_state["you"]["id"]

        self.snakes = {}
        for s in board["snakes"]:
            self.snakes[s["id"]] = {
                "body": [(seg["x"], seg["y"]) for seg in s["body"]],
                "health": s["health"],
                "length": s["length"],
            }

    def clone(self):
        gs = GameState()
        gs.width = self.width
        gs.height = self.height
        gs.food = self.food
        gs.my_id = self.my_id
        gs.snakes = {}
        for sid, s in self.snakes.items():
            gs.snakes[sid] = {
                "body": s["body"][:],
                "health": s["health"],
                "length": s["length"],
            }
        return gs

    def in_bounds(self, pos):
        return 0 <= pos[0] < self.width and 0 <= pos[1] < self.height

    def get_occupied(self):
        """获取所有被蛇身体占据的格子集合。"""
        occ = set()
        for s in self.snakes.values():
            for seg in s["body"]:
                occ.add(seg)
        return occ

    def get_safe_moves(self, snake_id):
        """获取某条蛇的安全移动方向（不撞墙、不撞身体）。"""
        if snake_id not in self.snakes:
            return []
        snake = self.snakes[snake_id]
        head = snake["body"][0]

        # 所有蛇身体（含尾，保守处理）
        occupied = self.get_occupied()
        # 移除自己的尾巴（如果没刚吃食物，尾巴会移走）
        my_tail = snake["body"][-1]
        # 只有尾巴不是重复节点时才能安全移除
        if snake["body"].count(my_tail) == 1:
            occupied.discard(my_tail)

        safe = []
        for move_name, (dx, dy) in MOVES.items():
            nb = add(head, (dx, dy))
            if self.in_bounds(nb) and nb not in occupied:
                safe.append(move_name)
        return safe

    def apply_move(self, snake_id, move_name):
        """
        应用一个蛇的移动，返回新状态。
        处理：移动、吃食物、碰撞检测。
        """
        gs = self.clone()
        if snake_id not in gs.snakes:
            return gs

        snake = gs.snakes[snake_id]
        dx, dy = MOVES[move_name]
        new_head = add(snake["body"][0], (dx, dy))

        # 移动蛇头
        snake["body"].insert(0, new_head)
        snake["health"] -= 1

        # 吃食物
        if new_head in gs.food:
            snake["health"] = 100
            snake["length"] += 1
            gs.food = gs.food - {new_head}
        else:
            snake["body"].pop()  # 去尾

        return gs

    def apply_moves(self, moves_dict):
        """同时应用所有蛇的移动，然后处理碰撞。"""
        gs = self.clone()
        new_food = set(gs.food)

        for sid, move_name in moves_dict.items():
            if sid not in gs.snakes:
                continue
            snake = gs.snakes[sid]
            dx, dy = MOVES[move_name]
            new_head = add(snake["body"][0], (dx, dy))

            snake["body"].insert(0, new_head)
            snake["health"] -= 1

            if new_head in new_food:
                snake["health"] = 100
                snake["length"] += 1
                new_food.discard(new_head)
            else:
                snake["body"].pop()

        gs.food = frozenset(new_food)

        # 碰撞检测：出界、撞身体、头碰头
        to_remove = set()
        for sid, snake in gs.snakes.items():
            head = snake["body"][0]
            # 出界
            if not gs.in_bounds(head):
                to_remove.add(sid)
                continue
            # 撞其他蛇身体（不含对方头）
            for other_id, other in gs.snakes.items():
                if other_id == sid:
                    # 撞自己身体（不含头）
                    if head in other["body"][1:]:
                        to_remove.add(sid)
                else:
                    if head in other["body"][1:]:
                        to_remove.add(sid)

        # 头碰头：长度短的或等长的都死
        heads = {}
        for sid, snake in gs.snakes.items():
            if sid in to_remove:
                continue
            head = snake["body"][0]
            if head not in heads:
                heads[head] = []
            heads[head].append(sid)

        for pos, sids in heads.items():
            if len(sids) > 1:
                max_len = max(gs.snakes[s]["length"] for s in sids)
                for s in sids:
                    if gs.snakes[s]["length"] < max_len:
                        to_remove.add(s)
                    elif sids.count(s) < len(sids):
                        # 所有等长的都碰头 → 都死
                        pass
                # 如果全部等长，全死
                lengths = [gs.snakes[s]["length"] for s in sids if s not in to_remove]
                if len(lengths) > 1 and len(set(lengths)) == 1:
                    for s in sids:
                        to_remove.add(s)

        for sid in to_remove:
            del gs.snakes[sid]

        # 饿死
        starved = [sid for sid, s in gs.snakes.items() if s["health"] <= 0]
        for sid in starved:
            del gs.snakes[sid]

        return gs

    def is_alive(self, snake_id):
        return snake_id in self.snakes

    def get_opponents(self, my_id):
        return [sid for sid in self.snakes if sid != my_id]


# ══════════════════════════════════════════════════════════════
# Flood Fill 空间评估
# ══════════════════════════════════════════════════════════════

def flood_fill(gs: GameState, start_pos):
    """从 start_pos 开始 flood fill，返回可达格子数。"""
    if not gs.in_bounds(start_pos):
        return 0
    occupied = gs.get_occupied()
    occupied.discard(start_pos)

    visited = {start_pos}
    queue = deque([start_pos])
    count = 0

    while queue:
        pos = queue.popleft()
        count += 1
        for dx, dy in MOVES.values():
            nb = add(pos, (dx, dy))
            if gs.in_bounds(nb) and nb not in occupied and nb not in visited:
                visited.add(nb)
                queue.append(nb)

    return count


def voronoi_score(gs: GameState, my_id):
    """
    Voronoi 空间控制：BFS 同时从所有蛇头出发，
    每个蛇"拥有"离它最近的空格数。
    返回 (我的面积, 对手最大面积)。
    """
    if my_id not in gs.snakes:
        return 0, 0

    occupied = gs.get_occupied()
    # 蛇头不算占据
    for s in gs.snakes.values():
        occupied.discard(s["body"][0])

    ownership = {}  # pos -> snake_id
    queue = deque()

    for sid, snake in gs.snakes.items():
        head = snake["body"][0]
        if gs.in_bounds(head):
            ownership[head] = sid
            queue.append((head, sid, 0))

    while queue:
        pos, sid, dist = queue.popleft()
        for dx, dy in MOVES.values():
            nb = add(pos, (dx, dy))
            if gs.in_bounds(nb) and nb not in occupied and nb not in ownership:
                ownership[nb] = sid
                queue.append((nb, sid, dist + 1))

    my_area = sum(1 for v in ownership.values() if v == my_id)
    opp_areas = {}
    for v in ownership.values():
        if v != my_id:
            opp_areas[v] = opp_areas.get(v, 0) + 1
    max_opp_area = max(opp_areas.values()) if opp_areas else 0

    return my_area, max_opp_area


# ══════════════════════════════════════════════════════════════
# 评估函数
# ══════════════════════════════════════════════════════════════

def evaluate(gs: GameState, my_id):
    """
    综合评估函数，返回分数（越高对我越好）。
    权重经过竞赛验证的启发式调优。
    """
    # 如果我死了
    if not gs.is_alive(my_id):
        return -10000

    # 如果对手全死了（我赢了）
    opponents = gs.get_opponents(my_id)
    if not opponents:
        return 10000

    me = gs.snakes[my_id]
    my_head = me["body"][0]
    my_length = me["length"]
    my_health = me["health"]

    score = 0.0

    # ── 1. 空间控制（最重要的因子）──
    my_space = flood_fill(gs, my_head)
    # 如果空间小于自身长度，极度危险
    if my_space < my_length:
        score -= 500 * (my_length - my_space)
    else:
        score += my_space * 3

    # Voronoi 空间优势
    my_area, max_opp_area = voronoi_score(gs, my_id)
    score += (my_area - max_opp_area) * 2

    # ── 2. 长度优势 ──
    for opp_id in opponents:
        opp = gs.snakes[opp_id]
        length_diff = my_length - opp["length"]
        if length_diff > 0:
            score += length_diff * 15  # 比对手长，可以头碰头杀
        else:
            score += length_diff * 10  # 比对手短，有风险

    # ── 3. 生命值管理 ──
    if my_health < 30:
        # 低血量，需要食物
        if gs.food:
            min_food_dist = min(manhattan(my_head, f) for f in gs.food)
            score -= min_food_dist * 5
        score -= (30 - my_health) * 3
    elif my_health < 60:
        if gs.food:
            min_food_dist = min(manhattan(my_head, f) for f in gs.food)
            score -= min_food_dist * 2

    # ── 4. 中心控制 ──
    center = (gs.width // 2, gs.height // 2)
    center_dist = manhattan(my_head, center)
    score -= center_dist * 1.5

    # ── 5. 追尾可达性（保底策略） ──
    my_tail = me["body"][-1]
    tail_dist = manhattan(my_head, my_tail)
    if my_length > 3:
        score -= tail_dist * 0.5

    # ── 6. 对手头碰头威胁 ──
    for opp_id in opponents:
        opp = gs.snakes[opp_id]
        opp_head = opp["body"][0]
        dist_to_opp = manhattan(my_head, opp_head)
        if dist_to_opp <= 2:
            if my_length > opp["length"]:
                score += 50  # 有击杀机会
            elif my_length <= opp["length"]:
                score -= 40  # 危险，应远离

    return score


# ══════════════════════════════════════════════════════════════
# Minimax + Alpha-Beta 剪枝
# ══════════════════════════════════════════════════════════════

def get_opponent_move(gs: GameState, opp_id):
    """对手的启发式移动预测（用于加速搜索）。"""
    safe = gs.get_safe_moves(opp_id)
    if not safe:
        return "up"  # 对手要死了

    opp = gs.snakes[opp_id]
    opp_head = opp["body"][0]

    # 对手优先选空间大的方向
    best_move = safe[0]
    best_space = -1
    for m in safe:
        dx, dy = MOVES[m]
        nb = add(opp_head, (dx, dy))
        gs_temp = gs.apply_move(opp_id, m)
        space = flood_fill(gs_temp, nb)
        if space > best_space:
            best_space = space
            best_move = m

    return best_move


def minimax(gs: GameState, my_id, depth, alpha, beta, is_max, start_time):
    """
    Minimax with Alpha-Beta pruning.
    is_max=True: 我方回合（最大化）
    is_max=False: 对手回合（最小化，paranoid假设）
    """
    # 终止条件
    if time.time() - start_time > TIME_BUDGET:
        return evaluate(gs, my_id), None

    if not gs.is_alive(my_id):
        return -10000, None

    opponents = gs.get_opponents(my_id)
    if not opponents:
        return 10000, None

    if depth <= 0:
        return evaluate(gs, my_id), None

    if is_max:
        # 我方回合
        safe_moves = gs.get_safe_moves(my_id)
        if not safe_moves:
            return -10000, None

        max_eval = float('-inf')
        best_move = safe_moves[0]

        # 按 flood fill 排序（先搜好的方向，提升剪枝效率）
        move_scores = []
        me = gs.snakes[my_id]
        my_head = me["body"][0]
        for m in safe_moves:
            dx, dy = MOVES[m]
            nb = add(my_head, (dx, dy))
            gs_after = gs.apply_move(my_id, m)
            space = flood_fill(gs_after, nb)
            move_scores.append((space, m))
        move_scores.sort(reverse=True)

        for _, m in move_scores:
            # 应用我的移动
            gs_next = gs.apply_move(my_id, m)
            # 对手回合
            eval_score, _ = minimax(gs_next, my_id, depth - 1, alpha, beta, False, start_time)

            if eval_score > max_eval:
                max_eval = eval_score
                best_move = m

            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break  # Beta 剪枝

            if time.time() - start_time > TIME_BUDGET:
                break

        return max_eval, best_move

    else:
        # 对手回合（paranoid: 所有对手联合对抗我）
        min_eval = float('inf')

        # 简化：对手按启发式走最优一步（避免指数爆炸）
        moves_dict = {}
        for opp_id in opponents:
            if gs.is_alive(opp_id):
                moves_dict[opp_id] = get_opponent_move(gs, opp_id)

        # 同时应用对手移动
        gs_next = gs.clone()
        for opp_id, opp_move in moves_dict.items():
            gs_next = gs_next.apply_move(opp_id, opp_move)

        # 处理碰撞
        # 简化：逐个检查是否有蛇死亡
        to_remove = set()
        for sid, snake in gs_next.snakes.items():
            head = snake["body"][0]
            if not gs_next.in_bounds(head):
                to_remove.add(sid)
                continue
            for other_id, other in gs_next.snakes.items():
                if other_id != sid and head in other["body"][1:]:
                    to_remove.add(sid)
        for sid in to_remove:
            if sid in gs_next.snakes:
                del gs_next.snakes[sid]

        eval_score, _ = minimax(gs_next, my_id, depth - 1, alpha, beta, True, start_time)
        min_eval = min(min_eval, eval_score)

        return min_eval, None


# ══════════════════════════════════════════════════════════════
# 迭代加深搜索
# ══════════════════════════════════════════════════════════════

def iterative_deepening(gs: GameState, my_id, start_time):
    """
    迭代加深：从深度 2 开始逐步加深，直到时间预算用完。
    保证在时间限制内返回当前最优移动。
    """
    best_move = None
    best_score = float('-inf')

    # 先用 flood fill 选一个保底移动
    safe_moves = gs.get_safe_moves(my_id)
    if not safe_moves:
        return "down"
    if len(safe_moves) == 1:
        return safe_moves[0]

    # 保底：选空间最大的
    me = gs.snakes[my_id]
    my_head = me["body"][0]
    for m in safe_moves:
        dx, dy = MOVES[m]
        nb = add(my_head, (dx, dy))
        gs_after = gs.apply_move(my_id, m)
        space = flood_fill(gs_after, nb)
        if space > best_score:
            best_score = space
            best_move = m

    # 迭代加深 minimax
    for depth in range(2, 12, 2):
        if time.time() - start_time > TIME_BUDGET:
            break

        score, move = minimax(gs, my_id, depth, float('-inf'), float('inf'), True, start_time)

        if move is not None and time.time() - start_time <= TIME_BUDGET:
            best_move = move
            best_score = score

    return best_move


# ══════════════════════════════════════════════════════════════
# 主决策入口
# ══════════════════════════════════════════════════════════════

def move(game_state: typing.Dict) -> typing.Dict:
    start_time = time.time()

    gs = GameState(game_state)

    # 只剩我一条蛇时，简单求生
    if len(gs.snakes) == 1:
        safe = gs.get_safe_moves(gs.my_id)
        if safe:
            # 选空间大的方向
            best_m = safe[0]
            best_s = 0
            me = gs.snakes[gs.my_id]
            for m in safe:
                dx, dy = MOVES[m]
                nb = add(me["body"][0], (dx, dy))
                gs_after = gs.apply_move(gs.my_id, m)
                s = flood_fill(gs_after, nb)
                if s > best_s:
                    best_s = s
                    best_m = m
            return {"move": best_m}
        return {"move": "down"}

    # 多蛇对战：迭代加深 Minimax
    best_move = iterative_deepening(gs, gs.my_id, start_time)

    return {"move": best_move}


# ══════════════════════════════════════════════════════════════
# 本地启动
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})
