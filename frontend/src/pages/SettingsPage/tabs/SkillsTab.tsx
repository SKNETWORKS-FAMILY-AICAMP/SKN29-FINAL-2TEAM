import { useEffect, useState } from 'react';
import { Button, Icon, InfoNote, Input, Modal, useToast } from '../../../components';
import {
  ApiError,
  createMySkill,
  deleteMySkill,
  getMySkill,
  listMySkills,
  updateMySkill,
} from '../../../api/skills';
import type { Skill } from '../../../api/skills';
import { loadSessionToken } from '../../../utils/session';
import { josa } from '../../../utils/josa';
import styles from './tabs.module.css';

/**
 * 「스킬」 탭 — 업무 절차를 적어 두면 에이전트가 필요할 때 골라 읽는다.
 *
 * **사람의 「기술 스택」과 다른 것이다.** 그쪽은 HR 이 아는 보유 역량이고
 * (`SkillList.tsx`), 여기는 「구매 검토는 이렇게 한다」 같은 절차 문서다.
 *
 * ## 화면만 있다 (2026-08-21, 준 → 주연 인계)
 *
 * 저장과 런타임 배선(`SkillsMiddleware`)은 주연 몫이라 아직 서버가 없다.
 * `api/skills.ts` 가 그 계약이고, 여기서는 **404 만 따로 받아 「준비 중」으로
 * 그린다** — 다른 오류와 같은 자리에 두면 「서버가 죽었다」로 읽힌다.
 * 엔드포인트가 붙는 순간 이 화면은 코드 변경 없이 그대로 산다.
 *
 * ## 팀 공유는 없다
 *
 * 내 것만 다룬다. 공유 범위·승인 권한은 아직 안 정해졌고, 정해지면 「내
 * 파일」 탭의 안쪽 탭(`Inner = 'mine' | 'shared'`)을 그대로 옮겨 오면 된다 —
 * 지금 미리 만들어 두면 안 정해진 것을 화면이 먼저 주장하게 된다.
 */

/** 만들기와 수정이 같은 폼을 쓴다. `null` 이면 폼이 닫혀 있다. */
type Editing = { skill: Skill | null; name: string; description: string; body: string } | null;

const EMPTY: NonNullable<Editing> = { skill: null, name: '', description: '', body: '' };

export function SkillsTab() {
  const { showToast } = useToast();
  const token = loadSessionToken();

  const [skills, setSkills] = useState<Skill[]>([]);
  const [error, setError] = useState<string | null>(null);
  /** 서버가 아직 없다(404). 오류와 다른 층이라 따로 센다 — 위 주석 참고. */
  const [unavailable, setUnavailable] = useState(false);
  /** 한 번이라도 목록을 받아 봤는가. **빈 목록과 못 받은 것을 가른다** — 안
      가르면 서버가 죽었을 때도 「아직 만든 스킬이 없습니다」가 뜬다. */
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState<Editing>(null);
  const [confirming, setConfirming] = useState<Skill | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!token) return;
    try {
      setSkills(await listMySkills(token));
      setError(null);
      setUnavailable(false);
      setLoaded(true);
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 404) {
        setUnavailable(true);
        return;
      }
      setError(exc instanceof ApiError ? exc.message : '목록을 불러오지 못했습니다.');
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  /**
   * 수정 폼을 연다. **본문은 그때 받는다** — 목록 응답에 본문을 실으면
   * 스킬이 늘수록 목록이 무거워지는데, 정작 읽는 건 여는 한 건뿐이다.
   */
  async function openEdit(skill: Skill) {
    if (!token) return;
    setBusy(true);
    try {
      const full = await getMySkill(token, skill.skill_id);
      setEditing({
        skill: full,
        name: full.name,
        description: full.description,
        body: full.body ?? '',
      });
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '불러오지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!token || !editing) return;
    setBusy(true);
    try {
      const input = {
        name: editing.name.trim(),
        description: editing.description.trim(),
        body: editing.body,
      };
      if (editing.skill) {
        await updateMySkill(token, editing.skill.skill_id, input);
        showToast('스킬을 수정했습니다.', 'success');
      } else {
        await createMySkill(token, input);
        showToast('스킬을 만들었습니다.', 'success');
      }
      setEditing(null);
      await load();
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '저장하지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function remove(skill: Skill) {
    if (!token) return;
    setConfirming(null);
    setBusy(true);
    try {
      await deleteMySkill(token, skill.skill_id);
      setSkills((prev) => prev.filter((item) => item.skill_id !== skill.skill_id));
      showToast('스킬을 삭제했습니다.', 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '삭제하지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  /** 이름과 설명이 없으면 에이전트가 이 스킬을 고를 수 없다. 본문은 비어도 저장된다. */
  const saveable =
    editing !== null && editing.name.trim().length > 0 && editing.description.trim().length > 0;

  return (
    <div className={styles.tab}>
      {error && <p className={`${styles.notice} ${styles.noticeDanger}`}>{error}</p>}

      <section className={styles.card}>
        <div className={`${styles.cardHead} ${styles.cardHeadRow}`}>
          <h2 className={styles.cardTitle}>
            스킬
            <InfoNote title="스킬">
              <p>회사에서 일하는 절차를 적어 두는 곳입니다. 에이전트가 그대로 따라 합니다.</p>
              <p>
                <strong>설명</strong>은 에이전트가 이 스킬을 쓸지 판단하는 근거입니다. 어떤 일에
                쓰는 절차인지 한 줄로 적으세요.
              </p>
              <p>내용은 고른 뒤에 읽습니다. 길어도 대화가 무거워지지 않습니다.</p>
              <p>여기 만든 스킬은 나만 사용합니다.</p>
            </InfoNote>
          </h2>
          <Button
            size="sm"
            variant="outline"
            disabled={unavailable || busy}
            onClick={() => setEditing(EMPTY)}
          >
            {unavailable ? '새 스킬 (준비 중)' : '새 스킬'}
          </Button>
        </div>

        {/* 서버가 아직 없다는 것을 그대로 말한다. 빈 목록으로 그리면 「만든 게
            없다」로 읽혀서, 만들려다 실패하고 나서야 알게 된다. */}
        {unavailable ? (
          <p className={`${styles.notice} ${styles.noticeNeutral}`}>
            스킬 저장 기능은 아직 준비 중입니다. 지금은 화면만 볼 수 있습니다.
          </p>
        ) : (
          <div className={styles.list}>
            {loaded && skills.length === 0 && (
              <p className={styles.cardSub}>아직 만든 스킬이 없습니다.</p>
            )}

            {skills.map((skill) => (
              <div key={skill.skill_id} className={`${styles.row} ${styles.rowTall}`}>
                <span className={styles.rowIcon}>
                  <Icon name="sparkles" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.rowBody}>
                  <span className={styles.rowName}>{skill.name}</span>
                  {/* 설명은 줄여서 감추지 않는다 — 에이전트가 이것만 보고 고르는
                      값이라, 사람도 여기서 그대로 읽고 고칠 수 있어야 한다. */}
                  <span className={styles.rowMeta}>{skill.description}</span>
                </div>
                <div className={styles.rowActions}>
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => openEdit(skill)}>
                    수정
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => setConfirming(skill)}
                  >
                    삭제
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing?.skill ? '스킬 수정' : '새 스킬'}
        footer={(
          <>
            <Button variant="outline" onClick={() => setEditing(null)}>
              취소
            </Button>
            <Button variant="primary" disabled={!saveable || busy} onClick={() => void save()}>
              {busy ? '저장하는 중…' : '저장'}
            </Button>
          </>
        )}
      >
        <div className={styles.formStack}>
          <Input
            label="이름"
            required
            value={editing?.name ?? ''}
            placeholder="구매 검토 절차"
            onChange={(event) =>
              setEditing((prev) => (prev ? { ...prev, name: event.target.value } : prev))
            }
          />
          <Input
            label="설명"
            required
            value={editing?.description ?? ''}
            placeholder="구매 요청을 검토하고 승인 라인을 정할 때 사용합니다"
            onChange={(event) =>
              setEditing((prev) => (prev ? { ...prev, description: event.target.value } : prev))
            }
          />
          <div className={styles.formField}>
            <label className={styles.formLabel} htmlFor="skill-body">
              내용
            </label>
            <textarea
              id="skill-body"
              className={styles.formTextarea}
              rows={12}
              value={editing?.body ?? ''}
              placeholder={'1. 요청 금액을 확인한다.\n2. 500만원을 넘으면 팀장 승인을 받는다.'}
              onChange={(event) =>
                setEditing((prev) => (prev ? { ...prev, body: event.target.value } : prev))
              }
            />
          </div>
        </div>
      </Modal>

      {/* 「내 파일」 삭제와 같은 꼴로 묻는다 — 되돌릴 수 없는 것은 무엇이
          사라지는지 먼저 말한다. */}
      <Modal
        open={confirming !== null}
        onClose={() => setConfirming(null)}
        title="스킬 삭제"
        footer={(
          <>
            <Button variant="outline" onClick={() => setConfirming(null)}>
              취소
            </Button>
            <Button
              variant="primary"
              disabled={busy}
              onClick={() => confirming && void remove(confirming)}
            >
              {busy ? '삭제하는 중…' : '삭제'}
            </Button>
          </>
        )}
      >
        <p className={styles.confirmText}>
          <strong>{confirming?.name}</strong>
          {josa(confirming?.name ?? '', '을/를')} 삭제합니다.{' '}
          <strong>되돌릴 수 없습니다.</strong>
        </p>
        <p className={styles.confirmText}>
          에이전트가 더 이상 이 절차를 따르지 않습니다.
        </p>
      </Modal>
    </div>
  );
}
