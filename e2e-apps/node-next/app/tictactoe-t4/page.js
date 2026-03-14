'use client';

import { useState, useCallback } from 'react';

const WINNING_COMBINATIONS = [
  [0, 1, 2],
  [3, 4, 5],
  [6, 7, 8],
  [0, 3, 6],
  [1, 4, 7],
  [2, 5, 8],
  [0, 4, 8],
  [2, 4, 6],
];

function checkWinner(board) {
  for (const combo of WINNING_COMBINATIONS) {
    const [a, b, c] = combo;
    if (board[a] && board[a] === board[b] && board[a] === board[c]) {
      return board[a];
    }
  }
  return null;
}

export default function TicTacToePage() {
  const [board, setBoard] = useState(Array(9).fill(null));
  const [currentPlayer, setCurrentPlayer] = useState('X');
  const [winner, setWinner] = useState(null);

  const handleCellClick = useCallback((index) => {
    if (board[index] || winner) {
      return;
    }

    const newBoard = [...board];
    newBoard[index] = currentPlayer;
    setBoard(newBoard);

    const newWinner = checkWinner(newBoard);
    if (newWinner) {
      setWinner(newWinner);
    } else {
      setCurrentPlayer(currentPlayer === 'X' ? 'O' : 'X');
    }
  }, [board, currentPlayer, winner]);

  return (
    <main
      style={{
        minHeight: '100vh',
        background: 'radial-gradient(circle at 50% 50%, #1a1a2e 0%, #16213e 50%, #0f0f23 100%)',
        color: '#eaeaea',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem 1rem',
      }}
    >
      <section
        style={{
          width: 'min(100%, 30rem)',
          borderRadius: '24px',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          background: 'rgba(255, 255, 255, 0.05)',
          boxShadow: '0 20px 50px rgba(0, 0, 0, 0.3)',
          padding: '2rem',
        }}
      >
        <h1 style={{ margin: 0, fontSize: '1.75rem', textAlign: 'center' }}>
          Tic Tac Toe Browser Signal T4
        </h1>

        <p style={{ marginTop: '1rem', marginBottom: '1.5rem', color: '#a0a0a0', textAlign: 'center' }}>
          {winner ? `Winner: ${winner}` : `Current turn: ${currentPlayer}`}
        </p>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '8px',
            maxWidth: '300px',
            margin: '0 auto',
          }}
        >
          {board.map((cell, index) => (
            <button
              key={index}
              type="button"
              aria-label={`Cell ${index}`}
              onClick={() => handleCellClick(index)}
              disabled={!!cell || !!winner}
              style={{
                width: '100%',
                aspectRatio: '1',
                fontSize: '2.5rem',
                fontWeight: 'bold',
                borderRadius: '12px',
                border: '2px solid rgba(255, 255, 255, 0.2)',
                background: cell ? 'rgba(255, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.05)',
                color: cell === 'X' ? '#ff6b6b' : '#4ecdc4',
                cursor: cell || winner ? 'default' : 'pointer',
                transition: 'background 0.2s, transform 0.1s',
              }}
            >
              {cell}
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
