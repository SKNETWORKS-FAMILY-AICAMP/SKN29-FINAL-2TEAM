import { useEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Badge, Button, Icon, InfoNote, Input, Modal, useToast } from '../../../components';
import {
  ApiError,
  createMySkill,
  createTeamSkill,
  deleteMySkill,
  deleteTeamSkill,
  getMySkill,
  getTeamSkill,
  listMySkills,
  listTeamSkills,
  updateMySkill,
  updateTeamSkill,
} from '../../../api/skills';
import type { Skill } from '../../../api/skills';
import { loadSessionToken, useSession } from '../../../utils/session';
import { josa } from '../../../utils/josa';
import styles from './tabs.module.css';

/**
 * 「스킬」 탭 — 업무 절차를 적어 두면 에이전트가 필요할 때 골라 읽는다.
 *
 * **사람의 「기술 스택」과 다른 것이다.** 그쪽은 HR 이 아는 보유 역량이고
 * (`SkillList.tsx`), 여기는 「구매 검토는 이렇게 한다」 같은 절차 문서다.
 *
 * ## 서버가 붙었다 (2026-08-22)
 *
 * 저장·조회는 `apps/skills`(내부적으로 `services.agent_runtime.skills.service`
 * — 채팅의 `skill_register` 도구와 같은 함수)가 한다. 404 를 「준비 중」으로
 * 따로 그리던 자리는 이제 없다 — 진짜 실패만 오류로 보인다.
 *
 * ## 개인 스킬 / 팀 스킬
 *
 * 안쪽 탭으로 나눈다(`MyFilesTab.tsx`의 내 파일/공유 받은 파일과 같은 자리).
 * **개인 스킬은 나만 쓴다.** 팀 스킬은 **조회는 팀원 전체가, 만들고 고치고
 * 지우는 것은 팀장만** 할 수 있다 — 서버가 최종 판단하고, 여기서는 버튼을
 * 미리 숨겨 헛클릭을 줄인다.
 *
 * ## 만드는 두 가지 방법
 *
 * Claude 의 스킬 업로드와 같은 방식이다 — **이름은 사람이 칸에 적는 것이
 * 아니라 파일의 frontmatter(`name:`)에서 그대로 읽는다.** 「직접 작성」 탭은
 * 이름 칸을 사람이 채우고, 「파일 업로드」 탭은 `.md` 파일 하나를 읽어 이름·
 * 설명·본문을 그 자리에서 채운다. 이름이 같은 스킬이 이미 있으면 서버가
 * 덮어쓰지 않고 거부한다(409) — 그 문구를 그대로 토스트로 보여준다.
 *
 * ## 이름은 한 번 정하면 못 바꾼다
 *
 * 저장 경로 자체가 이름으로 정해져서다(`api/skills.ts` 참고). 수정 화면에서는
 * 이름 칸을 잠근다 — 바꿀 수 있는 것처럼 보여 주고 서버가 조용히 무시하면
 * 더 나쁘다.
 *
 * ## 개인 스킬과 팀 스킬 이름이 같으면 (2026-08-22)
 *
 * `deepagents`의 `SkillsMiddleware`를 직접 읽어 확인했다
 * (`deepagents/middleware/skills.py` `before_agent()`) — 이름이 같으면
 * **나중 소스가 완전히 덮어쓴다.** `(팀)`/`(개인)` 같은 구분 표시는 없다.
 * 소스 순서(`skill_sources()`)가 팀을 나중에 두므로 **팀 스킬이 개인 스킬을
 * 가리고, 가려진 개인 스킬은 그 세션 동안 에이전트에게 아예 안 보인다** —
 * 오류도 안 뜬다. 새로 만들 때 같은 이름이 다른 범위에 이미 있으면 서버가
 * 막아 주지만(팀 스킬이 있는 상태에서 같은 이름의 개인 스킬을 만들려는
 * 경우), 반대 순서(개인 스킬이 있는데 다른 팀원이 나중에 같은 이름의 팀
 * 스킬을 만드는 경우)는 서버가 미리 알 방법이 없다 — 그래서 목록에 겹치는
 * 이름을 배지로 표시해 둔다(아래 `collidingNames`).
 *
 * ## 업로드 용량 (2026-08-22)
 *
 * `deepagents`가 SKILL.md 파일 하나에 진짜로 두는 상한은 10MB인데, 넘기면
 * 사람에게 아무 신호 없이 그 스킬이 조용히 목록에서 빠진다(`service.py`의
 * `MAX_SKILL_BODY_BYTES` 주석 참고). 여기서는 그 상한의 1/50인 200KB로
 * 미리 막는다 — 화면에서 바로 알려주지, 나중에 에이전트가 못 읽는 채로
 * 조용히 사라지게 두지 않는다.
 */

type Scope = 'personal' | 'team';
type CreateMode = 'write' | 'upload';

/** 만들기와 수정이 같은 폼을 쓴다. `null` 이면 폼이 닫혀 있다. */
type Editing = {
  scope: Scope;
  skill: Skill | null;
  name: string;
  description: string;
  body: string;
  mode: CreateMode;
  /** 업로드 탭에서 고른 파일 이름. 미리보기 표시 여부를 가른다. */
  uploadFileName: string | null;
  /** 업로드한 파일을 못 읽었을 때의 사유. */
  uploadError: string | null;
} | null;

function emptyEditing(scope: Scope): NonNullable<Editing> {
  return {
    scope,
    skill: null,
    name: '',
    description: '',
    body: '',
    mode: 'write',
    uploadFileName: null,
    uploadError: null,
  };
}

/**
 * 업로드한 `.md` 의 frontmatter 를 미리 읽어 화면에 보여 주기 위한 것.
 *
 * **최종 판단은 서버가 한다** — `services.agent_runtime.skills.service.parse_skill_md`
 * 와 같은 모양(`---\nname: …\ndescription: …\n---\n\n본문`)을 가볍게 흉내만
 * 낸다. 여기서 걸러도 서버가 다시 검사하므로, 여기 로직이 느슨해도 안전하다 —
 * 대신 사람에게는 올리자마자 무엇이 저장될지 보여 준다.
 */
function parseSkillMdPreview(content: string): { name: string; description: string; body: string } {
  const trimmed = content.replace(/^﻿/, '');
  if (!trimmed.startsWith('---')) {
    throw new Error('SKILL.md 형식이 아닙니다. 맨 위가 ---로 시작해야 합니다.');
  }
  const rest = trimmed.slice(3);
  const closeIndex = rest.indexOf('\n---');
  if (closeIndex === -1) {
    throw new Error('정보 칸(---)이 닫히지 않았습니다.');
  }
  const frontmatter = rest.slice(0, closeIndex);
  const body = rest
    .slice(closeIndex + 4)
    .replace(/^\n+/, '')
    .replace(/\n+$/, '');

  let name = '';
  let description = '';
  for (const line of frontmatter.split('\n')) {
    const match = line.match(/^([a-zA-Z_]+):\s*(.*)$/);
    if (!match) continue;
    const value = match[2].trim().replace(/^['"]|['"]$/g, '');
    if (match[1] === 'name') name = value;
    if (match[1] === 'description') description = value;
  }

  if (!name) throw new Error('파일에 이름(name)이 없습니다.');
  if (!description) throw new Error('파일에 설명(description)이 없습니다.');

  return { name, description, body };
}

const UPLOAD_ACCEPT = '.md';

/**
 * 스킬 본문 용량 상한. **서버 `service.py`의 `MAX_SKILL_BODY_BYTES`와 같은
 * 값이다** — 여기서 미리 막아야 파일을 다 읽고 나서야(업로드) 혹은 저장을
 * 눌러서야(직접 작성) 서버 오류로 아는 일이 없다. 값을 바꿀 때는 두 곳을
 * 같이 바꾼다.
 */
const MAX_SKILL_BODY_BYTES = 200 * 1024;

function byteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}

function formatKB(bytes: number): string {
  return `${Math.ceil(bytes / 1024)}KB`;
}

export function SkillsTab() {
  const { showToast } = useToast();
  const token = loadSessionToken();
  const isLeader = useSession()?.account.role === 'leader';

  const [scope, setScope] = useState<Scope>('personal');
  const [personalSkills, setPersonalSkills] = useState<Skill[]>([]);
  const [teamSkills, setTeamSkills] = useState<Skill[]>([]);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  /** 한 번이라도 목록을 받아 봤는가. **빈 목록과 못 받은 것을 가른다.** */
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState<Editing>(null);
  const [confirming, setConfirming] = useState<{ scope: Scope; skill: Skill } | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    if (!token) return;
    try {
      // 둘을 함께 받는다. 탭을 바꿀 때마다 부르면 넘어갈 때 빈 화면이 번쩍인다.
      const [mine, team] = await Promise.all([listMySkills(token), listTeamSkills(token)]);
      setPersonalSkills(mine);
      setTeamSkills(team);
      setError(null);
      setLoaded(true);
    } catch (exc) {
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
  async function openEdit(editScope: Scope, skill: Skill) {
    if (!token) return;
    setBusy(true);
    try {
      const full =
        editScope === 'personal'
          ? await getMySkill(token, skill.skill_id)
          : await getTeamSkill(token, skill.skill_id);
      setEditing({
        scope: editScope,
        skill: full,
        name: full.name,
        description: full.description,
        body: full.body ?? '',
        mode: 'write',
        uploadFileName: null,
        uploadError: null,
      });
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '불러오지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  function onPickFile(file: File) {
    if (!file.name.toLowerCase().endsWith('.md')) {
      setEditing((prev) =>
        prev ? { ...prev, uploadFileName: file.name, uploadError: '.md 파일만 올릴 수 있습니다.' } : prev,
      );
      return;
    }
    if (file.size > MAX_SKILL_BODY_BYTES) {
      setEditing((prev) =>
        prev
          ? {
              ...prev,
              uploadFileName: file.name,
              uploadError: `파일이 너무 큽니다 (${formatKB(file.size)}). 최대 ${formatKB(MAX_SKILL_BODY_BYTES)}까지 올릴 수 있습니다.`,
            }
          : prev,
      );
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === 'string' ? reader.result : '';
      try {
        const parsed = parseSkillMdPreview(text);
        setEditing((prev) =>
          prev
            ? {
                ...prev,
                name: parsed.name,
                description: parsed.description,
                body: parsed.body,
                uploadFileName: file.name,
                uploadError: null,
              }
            : prev,
        );
      } catch (exc) {
        setEditing((prev) =>
          prev
            ? { ...prev, uploadFileName: file.name, uploadError: exc instanceof Error ? exc.message : '파일을 읽지 못했습니다.' }
            : prev,
        );
      }
    };
    reader.onerror = () => {
      setEditing((prev) => (prev ? { ...prev, uploadFileName: file.name, uploadError: '파일을 읽지 못했습니다.' } : prev));
    };
    reader.readAsText(file);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onPickFile(file);
  }

  async function save() {
    if (!token || !editing) return;
    setBusy(true);
    try {
      if (editing.skill) {
        const patch = { description: editing.description.trim(), body: editing.body };
        if (editing.scope === 'personal') await updateMySkill(token, editing.skill.skill_id, patch);
        else await updateTeamSkill(token, editing.skill.skill_id, patch);
        showToast('스킬을 수정했습니다.', 'success');
      } else {
        const input = { name: editing.name.trim(), description: editing.description.trim(), body: editing.body };
        if (editing.scope === 'personal') await createMySkill(token, input);
        else await createTeamSkill(token, input);
        showToast('스킬을 만들었습니다.', 'success');
      }
      setEditing(null);
      await load();
    } catch (exc) {
      // 이름이 겹치면 서버가 409로 거부한다 — 그 문구를 그대로 보여준다.
      showToast(exc instanceof ApiError ? exc.message : '저장하지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function remove(removeScope: Scope, skill: Skill) {
    if (!token) return;
    setConfirming(null);
    setBusy(true);
    try {
      if (removeScope === 'personal') {
        await deleteMySkill(token, skill.skill_id);
        setPersonalSkills((prev) => prev.filter((item) => item.skill_id !== skill.skill_id));
      } else {
        await deleteTeamSkill(token, skill.skill_id);
        setTeamSkills((prev) => prev.filter((item) => item.skill_id !== skill.skill_id));
      }
      showToast('스킬을 삭제했습니다.', 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '삭제하지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  const rows = scope === 'personal' ? personalSkills : teamSkills;
  /** 팀 스킬 화면에서 쓰기 조작(만들기·수정·삭제)을 낼 수 있는가. */
  const canWriteTeam = isLeader === true;
  const canCreate = scope === 'personal' || canWriteTeam;
  const canWriteRow = scope === 'personal' || canWriteTeam;

  /** 이름으로 걸러진 목록. 서버를 다시 안 부른다 — 두 목록 다 이미 화면에 있다. */
  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter(
      (skill) => skill.name.toLowerCase().includes(query) || skill.description.toLowerCase().includes(query),
    );
  }, [rows, search]);

  /**
   * 개인/팀에 같은 이름이 있는 스킬. **팀 스킬이 개인 스킬을 가린다**
   * (`SkillsMiddleware` 실측, 위 컴포넌트 docstring 참고) — 서버가 미리 못
   * 막는 방향(개인 스킬이 있는 뒤에 다른 팀원이 같은 이름의 팀 스킬을 만드는
   * 경우)까지 여기서 보여준다.
   */
  const collidingNames = useMemo(() => {
    const teamNames = new Set(teamSkills.map((skill) => skill.name));
    const personalNames = new Set(personalSkills.map((skill) => skill.name));
    const both = new Set<string>();
    for (const name of personalNames) if (teamNames.has(name)) both.add(name);
    return both;
  }, [personalSkills, teamSkills]);

  const bodyBytes = editing ? byteLength(editing.body) : 0;
  const bodyTooLarge = bodyBytes > MAX_SKILL_BODY_BYTES;

  /** 업로드 탭은 파일을 성공적으로 읽었을 때만 저장할 수 있다. */
  const saveable =
    editing !== null &&
    editing.name.trim().length > 0 &&
    editing.description.trim().length > 0 &&
    !bodyTooLarge &&
    (editing.skill !== null || editing.mode === 'write' || (editing.uploadFileName !== null && editing.uploadError === null));

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
              <p>
                <strong>개인 스킬</strong>은 나만 씁니다. <strong>팀 스킬</strong>은 팀원 모두가
                보되, 만들고 고치고 지우는 것은 팀장만 할 수 있습니다.
              </p>
              <p>
                파일로 올릴 때는 이름을 따로 적지 않습니다 — 파일 안 <code>name</code>을 그대로
                씁니다. 파일 하나는 최대 {formatKB(MAX_SKILL_BODY_BYTES)}까지 올릴 수 있습니다.
              </p>
              <p>
                개인 스킬과 팀 스킬 이름이 같으면 <strong>팀 스킬이 우선 적용</strong>됩니다 —
                개인 스킬은 에이전트에게 안 보이게 됩니다. 겹치면 목록에 표시합니다.
              </p>
            </InfoNote>
          </h2>
          {/* 검색창을 「새 스킬」 옆에 둔다 — 목록 위 한 줄에서 필터와 만들기를
              같이 다룬다. */}
          <div className={styles.headActions}>
            <div className={styles.searchBox}>
              <Icon name="search" size={16} color="var(--color-placeholder)" />
              <input
                type="text"
                className={styles.searchInput}
                placeholder="스킬 이름 또는 설명 검색..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            {canCreate && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing(emptyEditing(scope))}>
                새 스킬
              </Button>
            )}
          </div>
        </div>

        <div className={styles.innerTabs} role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={scope === 'personal'}
            className={[styles.innerTab, scope === 'personal' ? styles.innerTabOn : ''].filter(Boolean).join(' ')}
            onClick={() => setScope('personal')}
          >
            내 스킬 {personalSkills.length}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={scope === 'team'}
            className={[styles.innerTab, scope === 'team' ? styles.innerTabOn : ''].filter(Boolean).join(' ')}
            onClick={() => setScope('team')}
          >
            팀 스킬 {teamSkills.length}
          </button>
        </div>

        <div className={styles.list}>
          {loaded && rows.length === 0 && (
            <p className={styles.cardSub}>
              {scope === 'personal' ? '아직 만든 스킬이 없습니다.' : '아직 등록된 팀 스킬이 없습니다.'}
            </p>
          )}

          {loaded && rows.length > 0 && filteredRows.length === 0 && (
            <p className={styles.cardSub}>검색 결과가 없습니다.</p>
          )}

          {filteredRows.map((skill) => {
            const colliding = collidingNames.has(skill.name);
            return (
              <div key={skill.skill_id} className={`${styles.row} ${styles.rowTall}`}>
                <span className={styles.rowIcon}>
                  <Icon name="sparkles" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.rowBody}>
                  <span className={styles.rowName}>
                    {skill.name}
                    {colliding && <Badge tone="warning">이름 겹침</Badge>}
                  </span>
                  {/* 설명은 줄여서 감추지 않는다 — 에이전트가 이것만 보고 고르는
                      값이라, 사람도 여기서 그대로 읽고 고칠 수 있어야 한다. */}
                  <span className={styles.rowMeta}>{skill.description}</span>
                  {colliding && (
                    <span className={styles.rowMeta}>
                      {scope === 'personal'
                        ? '같은 이름의 팀 스킬이 있어 에이전트는 이 개인 스킬 대신 팀 스킬을 씁니다.'
                        : '같은 이름의 내 개인 스킬이 있습니다 — 에이전트는 이 팀 스킬을 씁니다.'}
                    </span>
                  )}
                </div>
                {canWriteRow && (
                  <div className={styles.rowActions}>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => openEdit(scope, skill)}>
                      수정
                    </Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirming({ scope, skill })}>
                      삭제
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing?.skill ? '스킬 수정' : editing?.scope === 'team' ? '새 팀 스킬' : '새 스킬'}
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
          {/* 새로 만들 때만 방법을 고른다 — 수정할 때는 이미 있는 내용을
              고치는 것이라 「업로드」가 의미가 없다. */}
          {editing?.skill === null && (
            <div className={styles.innerTabs} role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={editing.mode === 'write'}
                className={[styles.innerTab, editing.mode === 'write' ? styles.innerTabOn : ''].filter(Boolean).join(' ')}
                onClick={() => setEditing((prev) => (prev ? { ...prev, mode: 'write' } : prev))}
              >
                직접 작성
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={editing.mode === 'upload'}
                className={[styles.innerTab, editing.mode === 'upload' ? styles.innerTabOn : ''].filter(Boolean).join(' ')}
                onClick={() => setEditing((prev) => (prev ? { ...prev, mode: 'upload' } : prev))}
              >
                파일 업로드
              </button>
            </div>
          )}

          {editing?.skill === null && editing.mode === 'upload' ? (
            <>
              {/* Claude 의 스킬 업로드와 같은 방식 — 이름은 이 화면에서 안
                  받는다. 파일의 frontmatter `name:` 을 그대로 쓴다. */}
              <div
                className={[styles.dropZone, dragging ? styles.dropZoneOn : ''].filter(Boolean).join(' ')}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') fileInputRef.current?.click();
                }}
              >
                <Icon name="file-text" size={22} color="var(--color-primary)" />
                <span className={styles.dropTitle}>
                  {editing.uploadFileName ?? '여기로 끌어다 놓거나 눌러서 SKILL.md를 고르세요'}
                </span>
                <span className={styles.dropHint}>
                  .md 파일 하나 · frontmatter에 name·description 필요 · 최대 {formatKB(MAX_SKILL_BODY_BYTES)}
                </span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={UPLOAD_ACCEPT}
                  className={styles.fileInput}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) onPickFile(file);
                    event.target.value = '';
                  }}
                />
              </div>

              {editing.uploadError && <p className={`${styles.notice} ${styles.noticeDanger}`}>{editing.uploadError}</p>}

              {editing.uploadFileName && !editing.uploadError && (
                <div className={styles.formStack}>
                  <div className={styles.formField}>
                    <span className={styles.formLabel}>이름</span>
                    <p className={styles.confirmText}>{editing.name}</p>
                  </div>
                  <div className={styles.formField}>
                    <span className={styles.formLabel}>설명</span>
                    <p className={styles.confirmText}>{editing.description}</p>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <Input
                label="이름"
                required
                disabled={editing?.skill != null}
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
                <span className={[styles.byteCount, bodyTooLarge ? styles.byteCountOver : ''].filter(Boolean).join(' ')}>
                  {formatKB(bodyBytes)} / {formatKB(MAX_SKILL_BODY_BYTES)}
                  {bodyTooLarge && ' · 용량을 넘었습니다'}
                </span>
              </div>
            </>
          )}
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
            <Button variant="primary" disabled={busy} onClick={() => confirming && void remove(confirming.scope, confirming.skill)}>
              {busy ? '삭제하는 중…' : '삭제'}
            </Button>
          </>
        )}
      >
        <p className={styles.confirmText}>
          <strong>{confirming?.skill.name}</strong>
          {josa(confirming?.skill.name ?? '', '을/를')} 삭제합니다. <strong>되돌릴 수 없습니다.</strong>
        </p>
        <p className={styles.confirmText}>
          {confirming?.scope === 'team'
            ? '팀 전체 에이전트가 더 이상 이 절차를 따르지 않습니다.'
            : '에이전트가 더 이상 이 절차를 따르지 않습니다.'}
        </p>
      </Modal>
    </div>
  );
}
