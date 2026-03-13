'use client';

import { useState } from 'react';

const WINNING_LINES = [
  [0, 1, 2],
  [3, 4, 5],
  [6, 7, 8],
  [0, 3, 6],
  [1, 4, 7],
  [2, 5, 8],
  [0, 4, 8],
  [2, 4, 6],
];

function createBoard() {
  return Array(9).fill('');
}

function getWinner(board) {
  for (const [a, b, c] of WINNING_LINES) {
    if (board[a] && board[a] === board[b] && board[a] === board[c]) {
      return board[a];
    }
  }

  return '';
}

function getWinningLine(board) {
  for (const line of WINNING_LINES) {
    const [a, b, c] = line;
    if (board[a] && board[a] === board[b] && board[a] === board[c]) {
      return line;
    }
  }

  return [];
}

export default function TicTacToePage() {
  const [game, setGame] = useState({
    board: createBoard(),
    currentTurn: 'X',
  });

  const winner = getWinner(game.board);
  const winningLine = getWinningLine(game.board);
  const isDraw = !winner && game.board.every(Boolean);

  const status = winner
    ? `Winner: ${winner}`
    : isDraw
      ? 'Draw game'
      : `Current turn: ${game.currentTurn}`;

  function handleCellClick(index) {
    setGame((current) => {
      if (current.board[index] || getWinner(current.board)) {
        return current;
      }

      const board = [...current.board];
      board[index] = current.currentTurn;

      return {
        board,
        currentTurn: current.currentTurn === 'X' ? 'O' : 'X',
      };
    });
  }

  function handleRestart() {
    setGame({
      board: createBoard(),
      currentTurn: 'X',
    });
  }

  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem 1rem',
        background:
          'radial-gradient(circle at top, #243b55 0%, #141e30 45%, #0a1018 100%)',
        color: '#f7fbff',
      }}
    >
      <section
        style={{
          width: 'min(100%, 34rem)',
          padding: '2rem',
          borderRadius: '28px',
          background: 'rgba(8, 16, 27, 0.82)',
          border: '1px solid rgba(166, 207, 255, 0.22)',
          boxShadow: '0 24px 60px rgba(0, 0, 0, 0.3)',
        }}
      >
        <p
          style={{
            margin: 0,
            color: '#9fd6ff',
            textTransform: 'uppercase',
            letterSpacing: '0.14em',
            fontWeight: 700,
            fontSize: '0.82rem',
          }}
        >
          Tic Tac Toe Browser Signal T1
        </p>
        <h1 style={{ margin: '0.85rem 0 0.5rem', fontSize: '2.3rem' }}>
          Deterministic Tic-Tac-Toe
        </h1>
        <p
          aria-live="polite"
          role="status"
          style={{ margin: '0 0 1.5rem', fontSize: '1.05rem', color: '#dcecff' }}
        >
          {status}
        </p>
        <p style={{ margin: '0 0 1.25rem', color: '#b9d7f2', lineHeight: 1.6 }}>
          Follow the left column sequence to reproduce the deterministic X win.
        </p>

        <div
          aria-label="Tic Tac Toe board"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
            gap: '0.75rem',
            marginBottom: '1.5rem',
          }}
        >
          {game.board.map((cell, index) => {
            const isDisabled = Boolean(cell) || Boolean(winner);
            const isWinningCell = winningLine.includes(index);

            return (
              <button
                key={index}
                type="button"
                aria-label={`Cell ${index + 1}`}
                disabled={isDisabled}
                onClick={() => handleCellClick(index)}
                style={{
                  width: '100%',
                  aspectRatio: '1 / 1',
                  borderRadius: '20px',
                  border: '1px solid rgba(166, 207, 255, 0.26)',
                  background: cell
                    ? 'linear-gradient(180deg, rgba(77, 152, 230, 0.34), rgba(29, 86, 150, 0.52))'
                    : 'rgba(14, 34, 56, 0.94)',
                  color: '#ffffff',
                  fontSize: '2.8rem',
                  fontWeight: 800,
                  cursor: isDisabled ? 'default' : 'pointer',
                  boxShadow: isWinningCell
                    ? '0 0 0 3px rgba(255, 213, 79, 0.92), inset 0 0 0 1px rgba(255, 255, 255, 0.08)'
                    : 'inset 0 0 0 1px rgba(255, 255, 255, 0.04)',
                  transform: isWinningCell ? 'translateY(-2px)' : 'none',
                  transition: 'transform 120ms ease, box-shadow 120ms ease',
                }}
              >
                {cell}
              </button>
            );
          })}
        </div>

        <button
          type="button"
          onClick={handleRestart}
          style={{
            border: 'none',
            borderRadius: '999px',
            padding: '0.9rem 1.45rem',
            background: 'linear-gradient(180deg, #8ec5ff 0%, #5f9fe4 100%)',
            color: '#10243a',
            fontWeight: 800,
            fontSize: '1rem',
            cursor: 'pointer',
          }}
        >
          Restart
        </button>
      </section>
    </main>
  );
}
