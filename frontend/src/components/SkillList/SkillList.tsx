import { Badge } from '../Badge/Badge';
import type { BadgeTone } from '../Badge/Badge';
import type { PersonSkill } from '../../api/auth';
import styles from './SkillList.module.css';

/** 서버는 출처를 코드로 준다 — 한국어는 화면이 정한다. */
const SOURCE_LABEL: Record<string, string> = {
  HR: '인사 등록',
  RESUME: '이력서',
  USER_ADDED: '본인 입력',
  AI_INFERRED: 'AI 추정',
};

/**
 * 출처마다 신뢰도가 다르다. 인사가 등록한 것과 AI가 추정한 것을 같은 색으로
 * 보여주면, 배정 근거를 설명할 때 그 차이가 사라진다.
 */
const SOURCE_TONE: Record<string, BadgeTone> = {
  HR: 'success',
  RESUME: 'info',
  USER_ADDED: 'neutral',
  AI_INFERRED: 'warning',
};

export interface SkillListProps {
  skills: PersonSkill[];
}

/** 보유 스킬 목록. 팀장·팀원 설정이 같이 쓴다. */
export function SkillList({ skills }: SkillListProps) {
  if (skills.length === 0) {
    return (
      <p className={styles.empty}>
        등록된 스킬이 없습니다. 인사 시스템에 등록되거나 이력서를 분석하면 여기에 표시됩니다.
      </p>
    );
  }

  return (
    <div className={styles.list}>
      {skills.map((skill) => (
        <div key={skill.skill_id} className={styles.row}>
          <span className={styles.name}>{skill.name}</span>
          <span className={styles.category}>{skill.category ?? '-'}</span>
          {/* 숫자만 쓰면 5점 만점인지 알 수 없어 눈금으로 보여준다. */}
          <span className={styles.meter} title={`숙련도 ${skill.proficiency} / 5`}>
            {[1, 2, 3, 4, 5].map((step) => (
              <span
                key={step}
                className={[styles.step, step <= skill.proficiency ? styles.on : '']
                  .filter(Boolean)
                  .join(' ')}
              />
            ))}
          </span>
          <span className={styles.source}>
            {skill.source && (
              <Badge tone={SOURCE_TONE[skill.source] ?? 'neutral'}>
                {SOURCE_LABEL[skill.source] ?? skill.source}
              </Badge>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}

export default SkillList;
