import { useQuery } from '@tanstack/react-query';
import { BookOpen, Download } from 'lucide-react';
import { fetchTemplates } from '../api/client';
import Spinner from '../components/Spinner';
import styles from './Reports.module.css';

export default function Reports() {
  const { data: templates, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: fetchTemplates,
  });

  if (isLoading) {
    return (
      <div className={styles.loading}>
        <Spinner size={32} />
        <p>Loading report templates...</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Report Templates</h1>
        <p className={styles.subtitle}>
          Available report structures and section catalog
        </p>
      </div>

      {/* Blueprints */}
      <div className={styles.section}>
        <h2>Report Blueprints</h2>
        <p className={styles.sectionDesc}>
          Pre-defined report structures used when no template is supplied
        </p>

        <div className={styles.blueprintGrid}>
          {templates?.blueprints &&
            Object.entries(templates.blueprints).map(([type, sections]) => (
              <div key={type} className={styles.blueprintCard}>
                <div className={styles.blueprintHeader}>
                  <BookOpen size={18} />
                  <h3>{type}</h3>
                  <span className={styles.badge}>{sections.length} sections</span>
                </div>
                <ol className={styles.sectionList}>
                  {sections.map((sec, i) => (
                    <li key={i}>
                      <span className={styles.secName}>{sec.name}</span>
                      <span className={styles.secTitle}>{sec.title}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
        </div>
      </div>

      {/* Section Catalog */}
      <div className={styles.section}>
        <h2>Section Catalog</h2>
        <p className={styles.sectionDesc}>
          Sections matched against uploaded template headings via keyword matching
        </p>

        <div className={styles.catalogTable}>
          <table>
            <thead>
              <tr>
                <th>Section</th>
                <th>Keywords</th>
              </tr>
            </thead>
            <tbody>
              {templates?.section_catalog?.map((item, i) => (
                <tr key={i}>
                  <td className={styles.sectionName}>{item.section}</td>
                  <td>
                    <div className={styles.keywords}>
                      {item.keywords.map((kw, j) => (
                        <span key={j} className={styles.keyword}>
                          {kw}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className={styles.downloadNote}>
        <Download size={16} />
        <span>
          To download a generated report, use the <strong>Analyze</strong> page
          and click <strong>Download DOCX</strong> to save a Word report.
        </span>
      </div>
    </div>
  );
}
