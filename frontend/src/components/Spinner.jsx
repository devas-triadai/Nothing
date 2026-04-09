export default function Spinner({ size = 32 }) {
  return (
    <div style={{
      width: size,
      height: size,
      border: '3px solid var(--border)',
      borderTop: '3px solid #1e6bff',
      borderRadius: '50%',
      animation: 'spin 0.8s linear infinite',
      margin: '60px auto'
    }} />
  );
}
