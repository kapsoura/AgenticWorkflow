import { ReactNode } from 'react';
import styles from './Card.module.css';

interface CardProps {
  children: ReactNode;
  className?: string;
}

export default function Card({ children, className = '' }: CardProps) {
  return <div className={`${styles.card} ${className}`}>{children}</div>;
}

export function StatCard({
  label,
  value,
  trend,
}: {
  label: string;
  value: string | number;
  trend?: 'up' | 'down' | 'flat';
}) {
  return (
    <div className={styles.stat}>
      <div className={styles.statValue}>{value}</div>
      <div className={styles.statLabel}>
        {label}
        {trend && (
          <span
            className={
              trend === 'up'
                ? styles.trendUp
                : trend === 'down'
                ? styles.trendDown
                : styles.trendFlat
            }
          >
            {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'}
          </span>
        )}
      </div>
    </div>
  );
}
