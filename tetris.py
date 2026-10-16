"""俄罗斯方块。

在 new_demo 目录下运行：

    source venv/bin/activate
    python tetris.py

不打开窗口、只检查玩法逻辑：

    python tetris.py --self-test
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass

import pygame

COLS = 10
ROWS = 20
CELL = 30
SIDEBAR = 220
MARGIN = 24
WIDTH = MARGIN * 2 + COLS * CELL + SIDEBAR
HEIGHT = MARGIN * 2 + ROWS * CELL
FPS = 60

# 经典七种方块。1 表示有方块，矩阵按顺时针旋转。
SHAPES: dict[str, list[list[int]]] = {
    "I": [
        [0, 0, 0, 0],
        [1, 1, 1, 1],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ],
    "O": [
        [1, 1],
        [1, 1],
    ],
    "T": [
        [0, 1, 0],
        [1, 1, 1],
        [0, 0, 0],
    ],
    "S": [
        [0, 1, 1],
        [1, 1, 0],
        [0, 0, 0],
    ],
    "Z": [
        [1, 1, 0],
        [0, 1, 1],
        [0, 0, 0],
    ],
    "J": [
        [1, 0, 0],
        [1, 1, 1],
        [0, 0, 0],
    ],
    "L": [
        [0, 0, 1],
        [1, 1, 1],
        [0, 0, 0],
    ],
}

COLORS = {
    "I": (0, 220, 220),
    "O": (240, 200, 40),
    "T": (170, 70, 210),
    "S": (70, 200, 80),
    "Z": (220, 60, 70),
    "J": (60, 110, 230),
    "L": (240, 140, 40),
}

LINE_SCORES = {1: 100, 2: 300, 3: 500, 4: 800}
KICKS = [(0, 0), (-1, 0), (1, 0), (-2, 0), (2, 0), (0, -1), (0, 1)]

BG = (16, 18, 28)
PANEL = (28, 32, 48)
GRID = (42, 48, 68)
TEXT = (236, 238, 245)
MUTED = (160, 168, 188)
ACCENT = (120, 190, 255)


def rotate_cw(matrix: list[list[int]]) -> list[list[int]]:
    return [list(row) for row in zip(*matrix[::-1])]


def rotate_ccw(matrix: list[list[int]]) -> list[list[int]]:
    return [list(row) for row in zip(*matrix)][::-1]


def cells_of(matrix: list[list[int]]) -> list[tuple[int, int]]:
    found = []
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            if value:
                found.append((x, y))
    return found


@dataclass
class Piece:
    kind: str
    matrix: list[list[int]]
    x: int
    y: int

    def cells(self) -> list[tuple[int, int]]:
        return [(self.x + cx, self.y + cy) for cx, cy in cells_of(self.matrix)]


class Bag:
    """7-bag：每种方块各出现一次后再洗牌，避免长期不出现某一种。"""

    def __init__(self) -> None:
        self._items: list[str] = []

    def next(self) -> str:
        if not self._items:
            self._items = list(SHAPES)
            random.shuffle(self._items)
        return self._items.pop()


class Game:
    def __init__(self) -> None:
        self.bag = Bag()
        self.reset()

    def reset(self) -> None:
        self.board: list[list[str | None]] = [
            [None for _ in range(COLS)] for _ in range(ROWS)
        ]
        self.bag = Bag()
        self.hold_kind: str | None = None
        self.hold_used = False
        self.score = 0
        self.lines = 0
        self.level = 1
        self.game_over = False
        self.paused = False
        self.next_kind = self.bag.next()
        self.piece = self._spawn(self.bag.next())
        self.drop_ms = 0
        if self._hits(self.piece):
            self.game_over = True

    def gravity_interval(self) -> int:
        return max(70, int(800 * (0.82 ** (self.level - 1))))

    def _spawn(self, kind: str) -> Piece:
        matrix = [row[:] for row in SHAPES[kind]]
        width = len(matrix[0])
        return Piece(kind, matrix, (COLS - width) // 2, 0)

    def _hits(self, piece: Piece) -> bool:
        for x, y in piece.cells():
            if x < 0 or x >= COLS or y >= ROWS:
                return True
            if y >= 0 and self.board[y][x] is not None:
                return True
        return False

    def _try_place(self, kind: str, matrix: list[list[int]], x: int, y: int) -> Piece | None:
        piece = Piece(kind, matrix, x, y)
        if self._hits(piece):
            return None
        return piece

    def move(self, dx: int, dy: int) -> bool:
        if self.game_over or self.paused or self.piece is None:
            return False
        moved = self._try_place(
            self.piece.kind, self.piece.matrix, self.piece.x + dx, self.piece.y + dy
        )
        if moved is None:
            return False
        self.piece = moved
        return True

    def rotate(self, clockwise: bool = True) -> bool:
        if self.game_over or self.paused or self.piece is None:
            return False
        if self.piece.kind == "O":
            return True
        matrix = rotate_cw(self.piece.matrix) if clockwise else rotate_ccw(self.piece.matrix)
        for kick_x, kick_y in KICKS:
            moved = self._try_place(
                self.piece.kind,
                matrix,
                self.piece.x + kick_x,
                self.piece.y + kick_y,
            )
            if moved is not None:
                self.piece = moved
                return True
        return False

    def hard_drop(self) -> None:
        if self.game_over or self.paused or self.piece is None:
            return
        distance = self.ghost_distance()
        self.piece.y += distance
        self.score += distance * 2
        self.lock()

    def ghost_distance(self) -> int:
        if self.piece is None:
            return 0
        distance = 0
        probe = Piece(self.piece.kind, self.piece.matrix, self.piece.x, self.piece.y)
        while True:
            nxt = self._try_place(probe.kind, probe.matrix, probe.x, probe.y + 1)
            if nxt is None:
                break
            probe = nxt
            distance += 1
        return distance

    def hold(self) -> None:
        if self.game_over or self.paused or self.piece is None or self.hold_used:
            return
        current = self.piece.kind
        self.hold_used = True
        if self.hold_kind is None:
            self.hold_kind = current
            self.piece = self._spawn(self.next_kind)
            self.next_kind = self.bag.next()
        else:
            self.hold_kind, kind = current, self.hold_kind
            self.piece = self._spawn(kind)
        if self._hits(self.piece):
            self.game_over = True

    def lock(self) -> None:
        if self.piece is None:
            return
        for x, y in self.piece.cells():
            if y < 0:
                self.game_over = True
                self.piece = None
                return
            self.board[y][x] = self.piece.kind
        cleared = self._clear_lines()
        if cleared:
            self.lines += cleared
            self.score += LINE_SCORES[cleared] * self.level
            self.level = self.lines // 10 + 1
        self.hold_used = False
        self.drop_ms = 0
        self.piece = self._spawn(self.next_kind)
        self.next_kind = self.bag.next()
        if self._hits(self.piece):
            self.game_over = True
            self.piece = None

    def _clear_lines(self) -> int:
        kept = [row for row in self.board if any(cell is None for cell in row)]
        cleared = ROWS - len(kept)
        while len(kept) < ROWS:
            kept.insert(0, [None for _ in range(COLS)])
        self.board = kept
        return cleared

    def tick(self, dt_ms: int) -> None:
        if self.game_over or self.paused or self.piece is None:
            return
        self.drop_ms += dt_ms
        interval = self.gravity_interval()
        while self.drop_ms >= interval:
            self.drop_ms -= interval
            if not self.move(0, 1):
                self.lock()
                break


def load_font(size: int, bold: bool = False) -> pygame.font.Font:
    candidates = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
    ]
    for path in candidates:
        try:
            return pygame.font.Font(path, size)
        except (FileNotFoundError, OSError):
            continue
    return pygame.font.SysFont("arial", size, bold=bold)


def draw_cell(
    surface: pygame.Surface,
    x: int,
    y: int,
    color: tuple[int, int, int],
    size: int = CELL,
    ghost: bool = False,
) -> None:
    rect = pygame.Rect(x, y, size - 1, size - 1)
    if ghost:
        pygame.draw.rect(surface, color, rect, 2, border_radius=4)
        return
    pygame.draw.rect(surface, color, rect, border_radius=4)
    highlight = tuple(min(255, c + 50) for c in color)
    pygame.draw.rect(surface, highlight, (x + 3, y + 3, size - 10, 5), border_radius=3)


def draw_matrix(
    surface: pygame.Surface,
    matrix: list[list[int]],
    kind: str,
    origin: tuple[int, int],
    cell: int,
) -> None:
    ox, oy = origin
    for cx, cy in cells_of(matrix):
        draw_cell(surface, ox + cx * cell, oy + cy * cell, COLORS[kind], cell)


def draw(screen: pygame.Surface, game: Game, fonts: dict[str, pygame.font.Font]) -> None:
    screen.fill(BG)
    board_rect = pygame.Rect(MARGIN, MARGIN, COLS * CELL, ROWS * CELL)
    pygame.draw.rect(screen, (12, 14, 22), board_rect, border_radius=6)

    for y in range(ROWS):
        for x in range(COLS):
            px = MARGIN + x * CELL
            py = MARGIN + y * CELL
            pygame.draw.rect(screen, GRID, (px, py, CELL - 1, CELL - 1), 1, border_radius=3)
            kind = game.board[y][x]
            if kind:
                draw_cell(screen, px, py, COLORS[kind])

    if game.piece is not None:
        ghost_y = game.piece.y + game.ghost_distance()
        for x, y in Piece(game.piece.kind, game.piece.matrix, game.piece.x, ghost_y).cells():
            if y >= 0:
                draw_cell(
                    screen,
                    MARGIN + x * CELL,
                    MARGIN + y * CELL,
                    COLORS[game.piece.kind],
                    ghost=True,
                )
        for x, y in game.piece.cells():
            if y >= 0:
                draw_cell(screen, MARGIN + x * CELL, MARGIN + y * CELL, COLORS[game.piece.kind])

    side_x = MARGIN + COLS * CELL + 20
    title = fonts["title"].render("俄罗斯方块", True, TEXT)
    screen.blit(title, (side_x, MARGIN))

    stats = [
        ("分数", str(game.score)),
        ("等级", str(game.level)),
        ("消行", str(game.lines)),
    ]
    y = MARGIN + 48
    for label, value in stats:
        screen.blit(fonts["small"].render(label, True, MUTED), (side_x, y))
        screen.blit(fonts["body"].render(value, True, ACCENT), (side_x + 70, y - 4))
        y += 36

    y += 8
    screen.blit(fonts["small"].render("下一个", True, MUTED), (side_x, y))
    preview = pygame.Rect(side_x, y + 28, 140, 90)
    pygame.draw.rect(screen, PANEL, preview, border_radius=8)
    matrix = SHAPES[game.next_kind]
    cell = 22
    draw_matrix(
        screen,
        matrix,
        game.next_kind,
        (preview.x + 22, preview.y + 16),
        cell,
    )

    y = preview.bottom + 16
    screen.blit(fonts["small"].render("暂存  C", True, MUTED), (side_x, y))
    hold_box = pygame.Rect(side_x, y + 28, 140, 90)
    pygame.draw.rect(screen, PANEL, hold_box, border_radius=8)
    if game.hold_kind:
        draw_matrix(
            screen,
            SHAPES[game.hold_kind],
            game.hold_kind,
            (hold_box.x + 22, hold_box.y + 16),
            22,
        )

    help_lines = [
        "← →  移动",
        "↑ / X  顺时针",
        "Z  逆时针",
        "↓  软降",
        "空格  硬降",
        "P  暂停    R  重开",
    ]
    y = hold_box.bottom + 20
    for line in help_lines:
        screen.blit(fonts["tiny"].render(line, True, MUTED), (side_x, y))
        y += 22

    if game.paused or game.game_over:
        overlay = pygame.Surface((board_rect.width, board_rect.height), pygame.SRCALPHA)
        overlay.fill((8, 10, 18, 180))
        screen.blit(overlay, board_rect.topleft)
        message = "已暂停" if game.paused else "游戏结束"
        hint = "按 P 继续" if game.paused else "按 R 重新开始"
        text = fonts["title"].render(message, True, TEXT)
        sub = fonts["small"].render(hint, True, MUTED)
        screen.blit(text, text.get_rect(center=(board_rect.centerx, board_rect.centery - 16)))
        screen.blit(sub, sub.get_rect(center=(board_rect.centerx, board_rect.centery + 24)))


def run() -> None:
    pygame.init()
    pygame.display.set_caption("俄罗斯方块")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    pygame.key.set_repeat(160, 45)
    fonts = {
        "title": load_font(28),
        "body": load_font(26),
        "small": load_font(18),
        "tiny": load_font(16),
    }
    game = Game()

    while True:
        dt = clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type != pygame.KEYDOWN:
                continue
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                pygame.quit()
                return
            if event.key == pygame.K_p:
                if not game.game_over:
                    game.paused = not game.paused
            elif event.key == pygame.K_r:
                game.reset()
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                game.move(-1, 0)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                game.move(1, 0)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                if game.move(0, 1):
                    game.score += 1
                else:
                    game.lock()
            elif event.key == pygame.K_SPACE:
                game.hard_drop()
            elif event.key in (pygame.K_UP, pygame.K_x, pygame.K_w):
                game.rotate(True)
            elif event.key == pygame.K_z:
                game.rotate(False)
            elif event.key == pygame.K_c:
                game.hold()

        game.tick(dt)
        draw(screen, game, fonts)
        pygame.display.flip()


def self_test() -> None:
    random.seed(1)
    game = Game()
    assert game.piece is not None
    assert not game.game_over

    if game.piece.kind != "O":
        before = [row[:] for row in game.piece.matrix]
        assert game.rotate(True)
        assert game.piece.matrix != before

    for _ in range(COLS + 4):
        game.move(-1, 0)
    assert all(x >= 0 for x, _ in game.piece.cells())
    for _ in range(COLS + 4):
        game.move(1, 0)
    assert all(x < COLS for x, _ in game.piece.cells())

    game.board = [[None for _ in range(COLS)] for _ in range(ROWS)]
    game.board[-1] = ["I"] * COLS
    game.board[-2] = ["O"] * COLS
    cleared = game._clear_lines()
    assert cleared == 2
    assert all(cell is None for cell in game.board[-1])

    game.reset()
    game.hard_drop()
    assert game.piece is not None
    assert any(any(cell is not None for cell in row) for row in game.board)

    blocked = Game()
    spawned = blocked._spawn("O")
    for x, y in spawned.cells():
        blocked.board[y][x] = "I"
    assert blocked._hits(spawned)

    print("self-test passed")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        run()
