import { createContext, useContext, useState, type ReactNode } from 'react';
import type { AnalyzeResponse } from '../api/client';

export interface AnalysisInputs {
  narrative: string;
  productCode: string;
  eventType: string;
  manufacturer: string;
}

interface AnalysisState {
  inputs: AnalysisInputs;
  setInputs: (inputs: AnalysisInputs) => void;
  result: AnalyzeResponse | null;
  setResult: (result: AnalyzeResponse | null) => void;
}

const DEFAULT_INPUTS: AnalysisInputs = {
  narrative: '',
  productCode: 'LNH',
  eventType: 'Malfunction',
  manufacturer: '',
};

const AnalysisContext = createContext<AnalysisState | undefined>(undefined);

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const [inputs, setInputs] = useState<AnalysisInputs>(DEFAULT_INPUTS);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  return (
    <AnalysisContext.Provider value={{ inputs, setInputs, result, setResult }}>
      {children}
    </AnalysisContext.Provider>
  );
}

export function useAnalysis(): AnalysisState {
  const ctx = useContext(AnalysisContext);
  if (!ctx) {
    throw new Error('useAnalysis must be used within an AnalysisProvider');
  }
  return ctx;
}
