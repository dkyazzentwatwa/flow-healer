'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const BOARD_SIZE = 14;
const TICK_MS = 140;

const DIRECTION_BY_KEY = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
  w: 'up',
  W: 'up',
  s: 'down',
  S: 'down',
  a: 'left',
  A: 'left',
  d: 'right',
  D: 'right',
};

const DELTA_BY_DIRECTION = {
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
};

const OPPOSITE = {
  up: 'down',
  down: 'up',
  left: 'right',
  right: 'left',
};

function randomFood(excluded) {
  while (true) {
    const food = {
      x: Math.floor(Math.random() * BOARD_SIZE),
      y: Math.floor(Math.random() * BOARD_SIZE),
    };
    if (!excluded.some((segment) => segment.x === food.x && segment.y === food.y)) {
      return food;
    }
  }
}

function createInitialGame() {
  return {
    snake: [
      { x: 6, y: 7 },
      { x: 5, y: 7 },
      { x: 4, y: 7 },
    ],
    direction: 'right',
    score: 0,
    food: { x: 10, y: 7 },
    lastMove: 'ready',
    gameOver: false,
    started: false,
  };
}

function isOnSnake(snake, x, y) {
  return snake.some((segment) => segment.x === x && segment.y === y);
}

export default function SnakePage() {
  const [game, setGame] = useState(createInitialGame);
  const pendingDirectionRef = useRef(null);
  const gameSurfaceRef = useRef(null);

  const handleDirectionInput = useCallback((key) => {
    const nextDirection = DIRECTION_BY_KEY[key];
    if (!nextDirection) {
      return false;
    }

    setGame((current) => {
      if (current.gameOver) {
        return current;
      }

      if (OPPOSITE[current.direction] === nextDirection && current.started) {
        return current;
      }

      pendingDirectionRef.current = nextDirection;

      return {
        ...current,
        direction: nextDirection,
        started: true,
        lastMove: nextDirection,
      };
    });

    return true;
  }, []);

  const restart = useCallback(() => {
    pendingDirectionRef.current = null;
    setGame(createInitialGame());
  }, []);

  useEffect(() => {
    gameSurfaceRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(event) {
      if (!handleDirectionInput(event.key)) {
        return;
      }

      event.preventDefault();
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleDirectionInput]);

  useEffect(() => {
    const timer = setInterval(() => {
      setGame((current) => {
        if (current.gameOver || !current.started) {
          return current;
        }

        const direction = pendingDirectionRef.current ?? current.direction;
        pendingDirectionRef.current = null;
        const delta = DELTA_BY_DIRECTION[direction];
        const head = current.snake[0];
        const nextHead = { x: head.x + delta.x, y: head.y + delta.y };

        const hitWall =
          nextHead.x < 0 ||
          nextHead.x >= BOARD_SIZE ||
          nextHead.y < 0 ||
          nextHead.y >= BOARD_SIZE;
        const hitSelf = isOnSnake(current.snake, nextHead.x, nextHead.y);

        if (hitWall || hitSelf) {
          return {
            ...current,
            gameOver: true,
          };
        }

        const ateFood =
          nextHead.x === current.food.x && nextHead.y === current.food.y;

        const nextSnake = [nextHead, ...current.snake];
        if (!ateFood) {
          nextSnake.pop();
        }

        return {
          ...current,
          snake: nextSnake,
          score: ateFood ? current.score + 1 : current.score,
          food: ateFood ? randomFood(nextSnake) : current.food,
          direction,
          lastMove: direction,
        };
      });
    }, TICK_MS);

    return () => clearInterval(timer);
  }, []);

  const cells = useMemo(() => {
    const board = [];
    for (let y = 0; y < BOARD_SIZE; y += 1) {
      for (let x = 0; x < BOARD_SIZE; x += 1) {
        const key = `${x}-${y}`;
        let kind = 'empty';
        if (game.food.x === x && game.food.y === y) {
          kind = 'food';
        }
        if (isOnSnake(game.snake, x, y)) {
          kind = x === game.snake[0].x && y === game.snake[0].y ? 'head' : 'snake';
        }
        board.push({ key, kind });
      }
    }
    return board;
  }, [game.food.x, game.food.y, game.snake]);

  return (
    <main
      style={{
        minHeight: '100vh',
        background:
          'radial-gradient(circle at 15% 15%, #17432f 0%, #0f261b 36%, #09140f 100%)',
        color: '#f0f7ef',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem 1rem',
      }}
    >
      <section
        style={{
          width: 'min(100%, 50rem)',
          borderRadius: '24px',
          border: '1px solid rgba(213, 246, 201, 0.25)',
          background: 'rgba(6, 16, 11, 0.78)',
          boxShadow: '0 20px 50px rgba(2, 6, 4, 0.45)',
          padding: '1.5rem',
        }}
      >
        <h1 style={{ margin: 0, fontSize: '1.9rem' }}>Snake Browser Signal S1</h1>
        <p style={{ marginTop: '0.75rem', marginBottom: '0.35rem', color: '#d3eecf' }}>
          Score: {game.score}
        </p>
        <p style={{ marginTop: '0.2rem', marginBottom: '0.35rem', color: '#b9e8b3' }}>
          Last move: {game.lastMove}
        </p>
        <p style={{ marginTop: '0.2rem', marginBottom: '1rem', color: '#d3eecf' }}>
          Use arrow keys or WASD to steer the snake.
        </p>

        <div
          aria-label="Snake game board"
          onKeyDown={(event) => {
            if (!handleDirectionInput(event.key)) {
              return;
            }

            event.preventDefault();
          }}
          ref={gameSurfaceRef}
          tabIndex={0}
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${BOARD_SIZE}, minmax(0, 1fr))`,
            gap: '4px',
            padding: '0.75rem',
            borderRadius: '16px',
            background: 'rgba(176, 233, 155, 0.12)',
            border: '1px solid rgba(176, 233, 155, 0.2)',
            width: 'min(100%, 34rem)',
            aspectRatio: '1 / 1',
          }}
        >
          {cells.map((cell) => {
            const color =
              cell.kind === 'head'
                ? '#7dff8b'
                : cell.kind === 'snake'
                  ? '#37c26a'
                  : cell.kind === 'food'
                    ? '#ff6f6f'
                    : 'rgba(7, 22, 14, 0.9)';
            return (
              <div
                key={cell.key}
                style={{
                  borderRadius: '6px',
                  backgroundColor: color,
                  border: '1px solid rgba(255, 255, 255, 0.04)',
                }}
              />
            );
          })}
        </div>

        <div
          style={{
            display: 'flex',
            gap: '0.75rem',
            flexWrap: 'wrap',
            marginTop: '1rem',
            alignItems: 'center',
          }}
        >
          <button
            type="button"
            onClick={restart}
            style={{
              border: '1px solid #8fd484',
              borderRadius: '999px',
              background: 'linear-gradient(180deg, #90df71 0%, #58ab4f 100%)',
              color: '#0b1d13',
              fontWeight: 700,
              padding: '0.45rem 1rem',
              cursor: 'pointer',
            }}
          >
            Restart
          </button>
          {game.gameOver ? (
            <span style={{ color: '#ffd6d6' }}>Game over. Press restart to play again.</span>
          ) : (
            <span style={{ color: '#c7efc1' }}>Collect food and avoid walls and your tail.</span>
          )}
        </div>
      </section>
    </main>
  );
}
