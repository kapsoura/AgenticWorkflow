import styles from './Spinner.module.css';

export default function Spinner({ size = 24 }: { size?: number }) {
  return (
    <div
      className={styles.spinner}
      style={{ width: size, height: size }}
    />
  );
}
