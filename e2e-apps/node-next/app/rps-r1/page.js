'use client';

import { useState } from 'react';

export default function RockPaperScissorsPage() {
  const [playerMove, setPlayerMove] = useState(null);
  const [botMove, setBotMove] = useState(null);
  const [result, setResult] = useState(null);

  const handleMove = (move) => {
    setPlayerMove(move);
    setBotMove('Scissors');
    setResult('You win');
  };

  const reset = () => {
    setPlayerMove(null);
    setBotMove(null);
    setResult(null);
  };

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
          Rock Paper Scissors Browser Signal R1
        </h1>

        {!playerMove ? (
          <p style={{ marginTop: '1rem', marginBottom: '1.5rem', color: '#a0a0a0', textAlign: 'center' }}>
            Choose your move
          </p>
        ) : null}

        {playerMove && (
          <p style={{ marginTop: '1rem', marginBottom: '0.5rem', color: '#4ecdc4', textAlign: 'center' }}>
            You played: {playerMove}
          </p>
        )}

        {botMove && (
          <p style={{ marginBottom: '0.5rem', color: '#ff6b6b', textAlign: 'center' }}>
            Bot played: {botMove}
          </p>
        )}

        {result && (
          <p style={{ marginBottom: '1.5rem', fontSize: '1.25rem', fontWeight: 'bold', color: '#ffd93d', textAlign: 'center' }}>
            Result: {result}
          </p>
        )}

        <div
          style={{
            display: 'flex',
            gap: '1rem',
            justifyContent: 'center',
            flexWrap: 'wrap',
          }}
        >
          <button
            type="button"
            onClick={() => handleMove('Rock')}
            style={{
              padding: '1rem 2rem',
              fontSize: '1.125rem',
              fontWeight: 'bold',
              borderRadius: '12px',
              border: '2px solid rgba(255, 255, 255, 0.2)',
              background: 'rgba(255, 255, 255, 0.1)',
              color: '#eaeaea',
              cursor: 'pointer',
              transition: 'background 0.2s, transform 0.1s',
            }}
          >
            Rock
          </button>

          <button
            type="button"
            onClick={() => handleMove('Paper')}
            style={{
              padding: '1rem 2rem',
              fontSize: '1.125rem',
              fontWeight: 'bold',
              borderRadius: '12px',
              border: '2px solid rgba(255, 255, 255, 0.2)',
              background: 'rgba(255, 255, 255, 0.1)',
              color: '#eaeaea',
              cursor: 'pointer',
              transition: 'background 0.2s, transform 0.1s',
            }}
          >
            Paper
          </button>

          <button
            type="button"
            onClick={() => handleMove('Scissors')}
            style={{
              padding: '1rem 2rem',
              fontSize: '1.125rem',
              fontWeight: 'bold',
              borderRadius: '12px',
              border: '2px solid rgba(255, 255, 255, 0.2)',
              background: 'rgba(255, 255, 255, 0.1)',
              color: '#eaeaea',
              cursor: 'pointer',
              transition: 'background 0.2s, transform 0.1s',
            }}
          >
            Scissors
          </button>
        </div>

        {playerMove && (
          <div style={{ marginTop: '1.5rem', textAlign: 'center' }}>
            <button
              type="button"
              onClick={reset}
              style={{
                padding: '0.75rem 1.5rem',
                fontSize: '1rem',
                borderRadius: '8px',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                background: 'transparent',
                color: '#a0a0a0',
                cursor: 'pointer',
              }}
            >
              Play Again
            </button>
          </div>
        )}
      </section>
    </main>
  );
}