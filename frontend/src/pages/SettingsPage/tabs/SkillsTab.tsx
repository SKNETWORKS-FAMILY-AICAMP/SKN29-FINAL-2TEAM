import { useEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Badge, Button, Icon, InfoNote, Input, Modal, ToggleSwitch, useToast } from '../../../components';
import { listAgentVersions } from '../../../api/agentVersions';
import {
  ApiError,
  createMySkill,
  deleteMySkill,
  deleteTeamSkill,
  getMySkill,
  getTeamSkill,
  importTeamSkill,
  listMySkills,
  listTeamSkills,
  shareMySkill,
  stopSharingMySkill,
  updateMySkill,
} from '../../../api/skills';
import type { Skill } from '../../../api/skills';
import {
  confirmMessage,
  createSession,
  deleteSession,
  setSessionToolRefs,
  streamMessage,
} from '../../../api/chat';
import type { ChatEvent } from '../../../api/chat';
import { ASK_FOLLOWUP_TOOL_NAME } from '../../ChatPage/liveChat';
import { loadSessionToken } from '../../../utils/session';
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
 * **개인 스킬만 에이전트가 사용한다.** 팀 스킬은 팀원이 공유한 카탈로그이며,
 * 다른 팀원이 가져오면 독립 개인 사본이 된다. 원 공유자의 비활성화·공유
 * 중지와 팀장의 카탈로그 삭제는 이미 가져간 사본에 영향을 주지 않는다.
 *
 * ## 만드는 두 가지 방법
 *
 * 「파일 업로드」 탭은 Claude 의 스킬 업로드와 같은 방식이다 — **이름은
 * 사람이 칸에 적는 것이 아니라 파일의 frontmatter(`name:`)에서 그대로
 * 읽는다.** `.md` 파일 하나를 읽어 이름·설명·본문을 그 자리에서 채운다.
 * 이름이 같은 스킬이 이미 있으면 서버가 덮어쓰지 않고 거부한다(409) — 그
 * 문구를 그대로 토스트로 보여준다.
 *
 * 「직접 작성」 탭은 **이름·설명·내용 칸을 더 안 받는다**(2026-08-24, 이 화면
 * 안에서 바로 만들도록 재작업 2026-08-24). 만들 스킬을 한 문장으로 적으면
 * 이 화면을 떠나지 않고 그대로 채팅 세션 하나를 조용히 열어(`createSession`)
 * `skill-creator` 내장 스킬에게 그 문장을 보낸다 — 이름·설명을 스스로 짓고,
 * 정보가 부족하면 `skill_creator_ask_followup`으로 한 번에 하나씩 되묻고,
 * 마지막엔 `skill_register` 확인 카드를 이 모달 안에 그대로 그린다
 * (`builtin_content.py`의 절차, 아래 `creation` 상태 기계). 여기서 폼으로
 * 다시 받으면 그 절차와 같은 판단을 사람이 두 번 하게 된다 — 그래서 안
 * 받는다. 수정(`editing.skill !== null`)은 이 대상이 아니다 — 이미 있는
 * 스킬을 고치는 것은 "만들기 절차"가 아니라 값 하나를 바꾸는 것이라 폼이
 * 그대로 맞다.
 *
 * ## 이름은 한 번 정하면 못 바꾼다
 *
 * 저장 경로 자체가 이름으로 정해져서다(`api/skills.ts` 참고). 수정 화면에서는
 * 이름 칸을 잠근다 — 바꿀 수 있는 것처럼 보여 주고 서버가 조용히 무시하면
 * 더 나쁘다.
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
  /**
   * 「직접 작성」 탭에서 새로 만들 때 받는 한 문장(2026-08-24). 이름·설명·
   * 내용을 여기서 안 받고, 이 문장을 들고 채팅(`/chat?ask=…`)으로 넘어간다
   * — `name`/`description`/`body`는 그 경로에서는 안 쓴다(수정 폼에서만
   * 쓴다).
   */
  sentence: string;
} | null;

/**
 * 「직접 작성」 새로 만들기 상태 기계(2026-08-24). 채팅으로 넘기지 않고 이
 * 모달 안에서 그대로 돌린다 — `ChatPage.tsx`의 `liveChat.ts` 리듀서를 그대로
 * 쓰지 않는 이유는, 그쪽은 대화 전체(과거 턴·추론·도구 진행률 카드)를 그리는
 * 상태 기계라 이 모달에 필요한 건 "질문 하나·확인 카드 하나·최종 결과"뿐이라
 * 훨씬 작다. 대신 이벤트 계약(`ChatEvent`, `ASK_FOLLOWUP_TOOL_NAME`)은 그대로
 * 재사용한다 — 서버가 보내는 모양은 채팅과 똑같기 때문이다.
 */
type CreationPhase = 'running' | 'ask' | 'confirm' | 'done' | 'cancelled' | 'error';

interface CreationAction {
  name: string;
  args: Record<string, unknown>;
}

interface CreationState {
  phase: CreationPhase;
  sessionId: string | null;
  /** `phase === 'ask'`일 때의 되묻기 질문. */
  question: string | null;
  /** `phase === 'confirm'`일 때 승인을 기다리는 도구 호출들(보통 `skill_register` 하나). */
  actions: CreationAction[] | null;
  /** `phase === 'done'`일 때, 등록까지 마친 모델의 마지막 답. */
  finalText: string | null;
  /** 실제로 `skill_register`가 성공했는가. `result` 이벤트의 완료 판정에 쓴다. */
  registered: boolean;
  /** 사용자가 등록 확인 카드에서 거절했는가. */
  registrationCancelled: boolean;
  /** `phase === 'error'`일 때 사유. */
  errorText: string | null;
  /**
   * `phase === 'running'`일 때 **왜** 도는지(2026-08-24 UX 점검 — 거절을
   * 눌러도 제목·본문이 항상 "스킬을 만드는 중…"이라, 실제로는 취소를
   * 반영하는 중인데 마치 새로 만드는 것처럼 보이고, 그 동안 모달을 닫을
   * 수도 없었다). 이유별로 제목·본문 문구와 닫기 가능 여부를 가른다.
   */
  runningReason: 'start' | 'answer' | 'approve' | 'cancel' | null;
}

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
    sentence: '',
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

  const [scope, setScope] = useState<Scope>('personal');
  const [personalSkills, setPersonalSkills] = useState<Skill[]>([]);
  const [teamSkills, setTeamSkills] = useState<Skill[]>([]);
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<
    Record<Scope, { activeOnly: boolean; sharedOnly: boolean; importedOnly: boolean }>
  >({
    personal: { activeOnly: false, sharedOnly: false, importedOnly: false },
    team: { activeOnly: false, sharedOnly: false, importedOnly: false },
  });
  const [error, setError] = useState<string | null>(null);
  /** 한 번이라도 목록을 받아 봤는가. **빈 목록과 못 받은 것을 가른다.** */
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState<Editing>(null);
  const [confirming, setConfirming] = useState<{ scope: Scope; skill: Skill } | null>(null);
  const [busy, setBusy] = useState(false);
  /** 상태 변경 중인 행만 잠근다. 개인·팀에서 id가 같을 수 있어 범위도 포함한다. */
  const [togglingSkillKey, setTogglingSkillKey] = useState<string | null>(null);
  const [sharingSkillKey, setSharingSkillKey] = useState<string | null>(null);
  const [importingSkillKey, setImportingSkillKey] = useState<string | null>(null);
  const [viewingSkill, setViewingSkill] = useState<Skill | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /** `null`이면 아직 「직접 작성」 한 문장 입력 단계 — `goCreateHere()`가 채운다. */
  const [creation, setCreation] = useState<CreationState | null>(null);
  /** 되묻기 카드(`skill_creator_ask_followup`)의 답변 입력값. 질문이 바뀔 때마다 비운다. */
  const [followupAnswer, setFollowupAnswer] = useState('');

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
        sentence: '',
      });
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '불러오지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function openTeamSkill(skill: Skill) {
    if (!token) return;
    setBusy(true);
    try {
      setViewingSkill(await getTeamSkill(token, skill.skill_id));
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '스킬 내용을 불러오지 못했습니다.', 'error');
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
        await updateMySkill(token, editing.skill.skill_id, patch);
        showToast('스킬을 수정했습니다.', 'success');
      } else {
        const input = { name: editing.name.trim(), description: editing.description.trim(), body: editing.body };
        await createMySkill(token, input);
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

  /**
   * 채팅과 같은 기본 에이전트를 고른다(`ChatPage.tsx`의 `usable.find((row) =>
   * row.is_default_chat)` 자리와 같은 규칙). 이 화면은 대화 목록이 없으므로
   * 매번 새로 조회한다 — 스킬 만들기는 자주 하는 조작이 아니라 캐싱까지는
   * 과하다.
   */
  async function resolveDefaultAgentId(): Promise<string | null> {
    if (!token) return null;
    const rows = await listAgentVersions(token);
    const usable = rows.filter((row) => row.status === 'ACTIVE' || row.status === 'DRAFT');
    return usable.find((row) => row.is_default_chat)?.agent_id ?? usable[0]?.agent_id ?? null;
  }

  /**
   * 스트림 이벤트 하나를 `creation` 상태로 접는다. `liveChat.ts`의
   * `awaiting_confirmation` 분기와 같은 판정 규칙을 쓴다 — 이 턴에 걸린
   * 호출이 `skill_creator_ask_followup` 하나뿐이면 되묻기, 아니면(보통
   * `skill_register`) 승인 카드다. 다른 타입(진행률·추론 등)은 이 작은
   * 모달에선 그리지 않고 조용히 무시한다 — 최종 결과만 보여 준다.
   *
   * **`result`만으로 "등록됐다"고 단정하지 않는다**(2026-08-24 실제로
   * 겪은 문제 — 모델이 정보가 부족한데도 `skill_creator_ask_followup`을
   * 안 부르고 채팅 텍스트로 질문 목록만 나열한 채 끝낸 경우에도 `result`가
   * 온다). 실제 등록 여부는 `skill_register`의 `tool_completed`를 따로
   * 봐서 `registered`에 남긴다 — `result` 쪽은 그 값을 안 건드린다(아래
   * `...prev`로 유지).
   */
  function handleCreationEvent(event: ChatEvent) {
    if (event.type === 'awaiting_confirmation') {
      let actions: CreationAction[];
      if ('action_requests' in event) {
        actions = event.action_requests.map((request) => ({ name: request.name, args: request.args ?? {} }));
      } else {
        actions = [{ name: event.tool_name, args: event.arguments ?? {} }];
      }
      const isAsk = actions.length === 1 && actions[0].name === ASK_FOLLOWUP_TOOL_NAME;
      if (isAsk) {
        const question = typeof actions[0].args.question === 'string' ? (actions[0].args.question as string) : '';
        setFollowupAnswer('');
        setCreation((prev) => (prev ? { ...prev, phase: 'ask', question, actions: null } : prev));
      } else {
        setCreation((prev) => (prev ? { ...prev, phase: 'confirm', actions, question: null } : prev));
      }
      return;
    }
    if (event.type === 'tool_completed' && event.tool_ref === 'skill_register' && event.status === 'OK') {
      setCreation((prev) => (prev ? { ...prev, registered: true } : prev));
      return;
    }
    if (event.type === 'result') {
      setCreation((prev) => {
        if (!prev) return prev;
        if (prev.registrationCancelled) {
          // **모델의 실제 응답을 지우지 않는다**(2026-08-24 UX 점검 — 예전엔
          // `finalText: null`로 버려서, 거절한 뒤엔 아무 내용도 없이 「닫기」
          // 버튼 하나만 남는 막다른 화면이었다. 이제 그 응답을 보여주고,
          // 바로 이어서 설명할 수 있는 입력칸을 아래(`continueAfterCancel`)
          // 붙인다 — 세션은 안 지웠으니 그대로 이어갈 수 있다.
          return { ...prev, phase: 'cancelled', finalText: event.text, errorText: null, runningReason: null };
        }
        if (!prev.registered) {
          return {
            ...prev,
            phase: 'error',
            finalText: null,
            errorText:
              '스킬 생성기가 등록 요청 없이 종료되었습니다. 일반 대화로 이어가지 않고 중단했습니다. 다시 시도해 주세요.',
          };
        }
        return { ...prev, phase: 'done', finalText: event.text };
      });
      return;
    }
    if (event.type === 'error') {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: event.detail ?? event.message ?? '스킬을 만들지 못했습니다.' } : prev,
      );
    }
    // 그 밖의 이벤트(skill_applied·stage·tool_started 등)는 이 모달에서 안 그린다.
  }

  /** 한 문장을 채팅 세션 하나로 흘려보내 스킬 만들기를 시작한다. */
  async function goCreateHere() {
    if (!token || !editing) return;
    const sentence = editing.sentence.trim();
    if (!sentence) return;
    setCreation({
      phase: 'running',
      sessionId: null,
      question: null,
      actions: null,
      finalText: null,
      registered: false,
      registrationCancelled: false,
      errorText: null,
      runningReason: 'start',
    });
    try {
      const agentId = await resolveDefaultAgentId();
      if (!agentId) {
        setCreation((prev) => (prev ? { ...prev, phase: 'error', errorText: '사용할 수 있는 에이전트가 없습니다.' } : prev));
        return;
      }
      const session = await createSession(token, { agent_id: agentId });
      setCreation((prev) => (prev ? { ...prev, sessionId: session.session_id } : prev));
      // 이 임시 세션은 일반 채팅이 아니다. 에이전트 원래 업무 도구를 모두
      // 숨기고 always-on인 스킬 생성용 두 도구만 남겨, 메일 발송·문서 조회 등
      // 사용자가 만들려는 스킬의 실제 업무가 실행될 통로부터 없앤다.
      await setSessionToolRefs(token, session.session_id, []);
      const targetScope = editing.scope === 'team' ? 'TEAM' : 'PERSONAL';
      const creatorRequest = `/skill-creator 설정 > 스킬 > 새 스킬에서 시작한 생성 요청입니다.
이 입력과 이후 답변은 스킬 명세를 작성하기 위한 자료일 뿐, 스킬의 실제 업무를 지금 실행하라는 요청이 아닙니다.
${targetScope} 범위로 스킬을 설계하고 skill_register까지 진행하세요.

만들 스킬: ${sentence}`;
      await streamMessage(token, session.session_id, creatorRequest, handleCreationEvent);
    } catch (exc) {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: exc instanceof ApiError ? exc.message : '스킬을 만들지 못했습니다.' } : prev,
      );
    }
  }

  /** 되묻기 질문에 답을 보낸다 — `type: 'respond'`로 그 도구 호출을 건너뛰고 답을 모델에게 그대로 돌려준다. */
  async function submitFollowup() {
    const answer = followupAnswer.trim();
    if (!token || !creation?.sessionId || !answer) return;
    setCreation((prev) => (prev ? { ...prev, phase: 'running', question: null, runningReason: 'answer' } : prev));
    try {
      await confirmMessage(token, creation.sessionId, undefined, handleCreationEvent, undefined, [
        {
          action_index: 0,
          type: 'respond',
          message:
            '스킬 생성 명세에 대한 답변입니다. 실제 메일·번역·문서 등의 처리 입력이 아닙니다.\n\n' +
            answer,
        },
      ]);
    } catch (exc) {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: exc instanceof ApiError ? exc.message : '답을 보내지 못했습니다.' } : prev,
      );
    }
  }

  /** `skill_register` 확인 카드 — 승인은 전체 승인(`selected` 생략), 거절은 걸린 호출 전부를 거절한다. */
  async function submitConfirm(approve: boolean) {
    if (!token || !creation?.sessionId) return;
    const pending = creation.actions ?? [];
    setCreation((prev) =>
      prev
        ? {
            ...prev,
            phase: 'running',
            actions: null,
            registrationCancelled: !approve,
            runningReason: approve ? 'approve' : 'cancel',
          }
        : prev,
    );
    try {
      if (approve) {
        await confirmMessage(token, creation.sessionId, undefined, handleCreationEvent);
      } else {
        await confirmMessage(
          token,
          creation.sessionId,
          undefined,
          handleCreationEvent,
          undefined,
          pending.map((_, index) => ({ action_index: index, type: 'reject' as const })),
        );
      }
    } catch (exc) {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: exc instanceof ApiError ? exc.message : '처리하지 못했습니다.' } : prev,
      );
    }
  }

  /**
   * 거절(다시 설명하기) 뒤에 이어서 설명한다(2026-08-24 UX 점검 — 예전엔
   * 거절하면 모델의 응답도 안 보여주고 「닫기」밖에 없는 막다른 화면이었다).
   * 세션은 살아 있으므로(`closeCreation`을 안 불렀다) `confirmMessage`가
   * 아니라 보통 발화처럼 `streamMessage`로 새 턴을 이어 보낸다 — 거절로
   * 이미 그 호출은 끝났고, 이건 다음 턴의 새 사용자 발화다.
   */
  async function continueAfterCancel() {
    const text = followupAnswer.trim();
    const sessionId = creation?.sessionId;
    if (!token || !sessionId || !text) return;
    setFollowupAnswer('');
    setCreation((prev) =>
      prev
        ? { ...prev, phase: 'running', runningReason: 'answer', registrationCancelled: false, finalText: null }
        : prev,
    );
    try {
      await streamMessage(token, sessionId, text, handleCreationEvent);
    } catch (exc) {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: exc instanceof ApiError ? exc.message : '메시지를 보내지 못했습니다.' } : prev,
      );
    }
  }

  /**
   * 스킬 만들기 대화창을 닫는다 — 성공·취소·오류 어느 경우든 여기 하나로
   * 모은다. **채팅 세션을 지운다.** 이 흐름은 `/chat/sessions/`를 그대로
   * 빌려 쓰지만(위 `goCreateHere` 주석) 사용자에게는 절대 "채팅"이
   * 아니다 — 스킬을 만들기 위한 질의응답일 뿐이다. 안 지우면 이게 진짜
   * 대화 목록(Chat 사이드바)에 남아 뒤섞인다(2026-08-24 실제로 겪은
   * 문제). `skill_register`는 이미 스킬 저장소에 별도로 저장했으므로
   * 세션을 지워도 등록된 스킬 자체는 그대로 남는다 — 지우는 건 이
   * 흐름의 흔적일 뿐이다. 실패해도 조용히 넘어간다(모달을 닫는 것보다
   * 중요하지 않다).
   */
  function closeCreation() {
    const sessionId = creation?.sessionId;
    setCreation(null);
    setEditing(null);
    if (token && sessionId) {
      void deleteSession(token, sessionId).catch(() => {});
    }
  }

  /** 오류 화면의 「다시 시도」— 대화창은 안 닫고 실패한 세션만 지운다. `goCreateHere()`가 새 세션을 다시 만든다. */
  function retryCreation() {
    const sessionId = creation?.sessionId;
    setCreation(null);
    if (token && sessionId) {
      void deleteSession(token, sessionId).catch(() => {});
    }
  }

  /** 만들기 완료(`phase === 'done'`) 뒤 「확인」— 대화창을 닫고 목록을 새로 받는다. */
  function finishCreation() {
    closeCreation();
    void load();
  }

  /**
   * 활성/비활성 토글. **삭제와 다르다** — 값은 그대로 두고
   * `metadata.enabled` 만 바꿔서, 꺼진 스킬은 `SkillVisibilityMiddleware`가
   * 에이전트에게 안 보이게만 거른다(2026-08-26). 목록 전체를 다시 안
   * 불러온다 — 서버가 돌려준 그 한 건만 바꿔치면 된다(`remove()`와 같은 이유).
   */
  async function toggleEnabled(toggleScope: Scope, skill: Skill) {
    const toggleKey = `${toggleScope}:${skill.skill_id}`;
    if (!token || togglingSkillKey === toggleKey) return;
    const next = !skill.enabled;
    setTogglingSkillKey(toggleKey);
    try {
      const updated = await updateMySkill(token, skill.skill_id, { enabled: next });
      setPersonalSkills((prev) => prev.map((item) => (item.skill_id === updated.skill_id ? updated : item)));
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '상태를 바꾸지 못했습니다.', 'error');
    } finally {
      setTogglingSkillKey(null);
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
        setTeamSkills((prev) =>
          prev
            .filter((item) => !(item.shared_by_me && item.name === skill.name))
            .map((item) =>
              skill.imported_from_team && item.name === skill.name
                ? { ...item, imported_by_me: false }
                : item,
            ),
        );
      } else {
        await deleteTeamSkill(token, skill.skill_id);
        setTeamSkills((prev) => prev.filter((item) => item.skill_id !== skill.skill_id));
      }
      showToast(
        removeScope === 'personal'
          ? '내 스킬을 삭제했습니다.'
          : '팀 공유 목록에서 삭제했습니다. 이미 가져간 개인 사본은 유지됩니다.',
        'success',
      );
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '삭제하지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function setShared(skill: Skill, shared: boolean) {
    if (!token || sharingSkillKey === skill.skill_id) return;
    setSharingSkillKey(skill.skill_id);
    try {
      if (shared) {
        const teamSkill = await shareMySkill(token, skill.skill_id);
        setTeamSkills((prev) => [...prev, teamSkill].sort((a, b) => a.name.localeCompare(b.name)));
        showToast('팀에 스킬을 공유했습니다.', 'success');
      } else {
        await stopSharingMySkill(token, skill.skill_id);
        setTeamSkills((prev) => prev.filter((item) => !(item.shared_by_me && item.name === skill.name)));
        showToast('팀 공유를 중지했습니다. 내 스킬은 그대로 남아 있습니다.', 'success');
      }
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '공유 상태를 바꾸지 못했습니다.', 'error');
    } finally {
      setSharingSkillKey(null);
    }
  }

  async function importSharedSkill(skill: Skill) {
    if (!token || importingSkillKey === skill.skill_id || skill.imported_by_me) return;
    setImportingSkillKey(skill.skill_id);
    try {
      const imported = await importTeamSkill(token, skill.skill_id);
      setPersonalSkills((prev) => [...prev, imported].sort((a, b) => a.name.localeCompare(b.name)));
      setTeamSkills((prev) =>
        prev.map((item) =>
          item.skill_id === skill.skill_id ? { ...item, imported_by_me: true } : item,
        ),
      );
      showToast('내 스킬로 가져왔습니다. 이제 활성 상태와 내용은 나에게만 적용됩니다.', 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '내 스킬로 가져오지 못했습니다.', 'error');
    } finally {
      setImportingSkillKey(null);
    }
  }

  const rows = scope === 'personal' ? personalSkills : teamSkills;
  const sharedPersonalNames = useMemo(
    () => new Set(teamSkills.filter((skill) => skill.shared_by_me).map((skill) => skill.name)),
    [teamSkills],
  );

  /** 이름으로 걸러진 목록. 서버를 다시 안 부른다 — 두 목록 다 이미 화면에 있다. */
  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const currentFilters = filters[scope];
    return rows.filter((skill) => {
      if (currentFilters.activeOnly && !skill.enabled) return false;
      if (currentFilters.sharedOnly) {
        const matchesShare = scope === 'personal' ? sharedPersonalNames.has(skill.name) : skill.shared_by_me;
        if (!matchesShare) return false;
      }
      if (currentFilters.importedOnly) {
        const isImported = scope === 'personal' ? skill.imported_from_team : skill.imported_by_me;
        if (!isImported) return false;
      }
      return !query || skill.name.toLowerCase().includes(query) || skill.description.toLowerCase().includes(query);
    });
  }, [filters, rows, scope, search, sharedPersonalNames]);

  const bodyBytes = editing ? byteLength(editing.body) : 0;
  const bodyTooLarge = bodyBytes > MAX_SKILL_BODY_BYTES;

  /** 새로 만들기 · 직접 작성 — 한 문장을 채웠는가. */
  const sentenceReady = editing !== null && editing.sentence.trim().length > 0;
  /** 새로 만들기 · 직접 작성 탭인가(폼이 아니라 한 문장 입력을 보여줄 자리). */
  const isSentenceCreate = editing?.skill === null && editing.mode === 'write';

  /** 업로드 탭은 파일을 성공적으로 읽었을 때만 저장할 수 있다. */
  const saveable =
    editing !== null &&
    editing.name.trim().length > 0 &&
    editing.description.trim().length > 0 &&
    !bodyTooLarge &&
    (editing.skill !== null || (editing.uploadFileName !== null && editing.uploadError === null));

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
                <strong>내 스킬</strong>만 에이전트가 사용합니다. <strong>팀 스킬</strong>은 팀원이
                공유한 스킬을 살펴보고 내 스킬로 가져오는 곳입니다.
              </p>
              <p>
                파일로 올릴 때는 이름을 따로 적지 않습니다 — 파일 안 <code>name</code>을 그대로
                씁니다. 파일 하나는 최대 {formatKB(MAX_SKILL_BODY_BYTES)}까지 올릴 수 있습니다.
              </p>
              <p>가져온 스킬은 독립된 내 스킬이므로 원 공유자의 비활성화나 공유 중지에 영향을 받지 않습니다.</p>
              <p>
                <strong>skill-creator</strong>는 모든 팀원에게 기본 제공되는 내장 스킬입니다.
                이 목록에는 안 뜨지만(개인/팀 스킬이 아니라서), 채팅에서 "~하는 스킬
                만들어줘"라고 하면 자동으로 켜져 필요한 것을 되물어 가며 스킬을 만듭니다.
              </p>
              <p>
                토글을 끄면 삭제하지 않고도 에이전트가 그 스킬을 못 보게 할 수 있습니다.
                내용은 그대로 남아 있어 언제든 다시 켤 수 있습니다. 이 상태는 나에게만 적용됩니다.
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
            {scope === 'personal' && (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setCreation(null);
                  setEditing(emptyEditing(scope));
                }}
              >
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

        <div className={styles.skillFilters} aria-label={`${scope === 'personal' ? '내' : '팀'} 스킬 필터`}>
          {scope === 'personal' && (
            <button
              type="button"
              aria-pressed={filters.personal.activeOnly}
              className={[styles.skillFilter, filters.personal.activeOnly ? styles.skillFilterOn : ''].filter(Boolean).join(' ')}
              onClick={() =>
                setFilters((prev) => ({
                  ...prev,
                  personal: { ...prev.personal, activeOnly: !prev.personal.activeOnly },
                }))
              }
            >
              활성화된 스킬
            </button>
          )}
          {scope === 'team' && (
            <button
              type="button"
              aria-pressed={filters.team.importedOnly}
              className={[styles.skillFilter, filters.team.importedOnly ? styles.skillFilterOn : ''].filter(Boolean).join(' ')}
              onClick={() =>
                setFilters((prev) => ({
                  ...prev,
                  team: { ...prev.team, importedOnly: !prev.team.importedOnly },
                }))
              }
            >
              등록된 스킬
            </button>
          )}
          <button
            type="button"
            aria-pressed={filters[scope].sharedOnly}
            className={[styles.skillFilter, filters[scope].sharedOnly ? styles.skillFilterOn : ''].filter(Boolean).join(' ')}
            onClick={() =>
              setFilters((prev) => ({
                ...prev,
                [scope]: { ...prev[scope], sharedOnly: !prev[scope].sharedOnly },
              }))
            }
          >
            {scope === 'personal' ? '팀에 공유한 스킬' : '내가 공유한 스킬'}
          </button>
          {scope === 'personal' && (
            <button
              type="button"
              aria-pressed={filters.personal.importedOnly}
              className={[styles.skillFilter, filters.personal.importedOnly ? styles.skillFilterOn : ''].filter(Boolean).join(' ')}
              onClick={() =>
                setFilters((prev) => ({
                  ...prev,
                  personal: { ...prev.personal, importedOnly: !prev.personal.importedOnly },
                }))
              }
            >
              팀 스킬에서 가져온 스킬
            </button>
          )}
        </div>

        <div className={styles.list}>
          {loaded && rows.length === 0 && (
            <p className={styles.cardSub}>
              {scope === 'personal' ? '아직 만든 스킬이 없습니다.' : '아직 등록된 팀 스킬이 없습니다.'}
            </p>
          )}

          {loaded && rows.length > 0 && filteredRows.length === 0 && (
            <p className={styles.cardSub}>선택한 조건에 맞는 스킬이 없습니다.</p>
          )}

          {filteredRows.map((skill) => {
            const toggleKey = `${scope}:${skill.skill_id}`;
            const toggling = togglingSkillKey === toggleKey;
            const sharedByMe = scope === 'team' ? skill.shared_by_me : sharedPersonalNames.has(skill.name);
            const sharing = sharingSkillKey === skill.skill_id;
            const importing = importingSkillKey === skill.skill_id;
            return (
              <div key={skill.skill_id} className={`${styles.row} ${styles.rowTall}`}>
                <span className={styles.rowIcon}>
                  <Icon name="sparkles" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.rowBody}>
                  <span className={styles.rowName}>
                    {skill.name}
                    {sharedByMe && <Badge tone="primary">공유중</Badge>}
                    {scope === 'personal' && skill.imported_from_team && (
                      <Badge tone="neutral">팀 스킬</Badge>
                    )}
                  </span>
                  {/* 설명은 줄여서 감추지 않는다 — 에이전트가 이것만 보고 고르는
                      값이라, 사람도 여기서 그대로 읽고 고칠 수 있어야 한다. */}
                  <span className={styles.rowMeta}>{skill.description}</span>
                </div>
                {scope === 'personal' ? (
                  <div className={styles.rowActions}>
                    {/* 꺼지면 값은 그대로 두고 에이전트에게만 안 보이게 한다
                        (삭제와 다름) — `toggleEnabled()` 참고. */}
                    <div
                      className={[
                        styles.skillState,
                        skill.enabled ? styles.skillStateOn : styles.skillStateOff,
                      ].join(' ')}
                    >
                      <span className={styles.skillStateText} aria-live="polite">
                        {toggling ? '변경 중' : skill.enabled ? '활성' : '비활성'}
                      </span>
                      <ToggleSwitch
                        checked={skill.enabled}
                        disabled={toggling}
                        ariaLabel={`${skill.name} 스킬을 ${skill.enabled ? '비활성화' : '활성화'}`}
                        onChange={() => void toggleEnabled(scope, skill)}
                      />
                    </div>
                    {!skill.imported_from_team && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy || sharing}
                        onClick={() => void setShared(skill, !sharedByMe)}
                      >
                        {sharing ? '처리 중…' : sharedByMe ? '중지' : '공유'}
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => openEdit('personal', skill)}>
                      수정
                    </Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirming({ scope, skill })}>
                      삭제
                    </Button>
                  </div>
                ) : (
                  <div className={styles.rowActions}>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => void openTeamSkill(skill)}>
                      내용 보기
                    </Button>
                    {!skill.shared_by_me && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy || importing || skill.imported_by_me}
                        onClick={() => void importSharedSkill(skill)}
                      >
                        {importing ? '가져오는 중…' : skill.imported_by_me ? '이미 등록됨' : '내 스킬로 등록'}
                      </Button>
                    )}
                    {skill.shared_by_me && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={sharing}
                        onClick={() => void setShared(skill, false)}
                      >
                        {sharing ? '처리 중…' : '중지'}
                      </Button>
                    )}
                    {skill.can_delete && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => setConfirming({ scope: 'team', skill })}
                      >
                        삭제
                      </Button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <Modal
        open={editing !== null}
        onClose={() => (creation ? closeCreation() : setEditing(null))}
        // **`running`이라고 무조건 못 닫게 하지 않는다**(2026-08-24 UX 점검
        // — "거절해도 1초 만에 안 끝나는데 뒤로 가기도 없다"는 지적). 정말
        // 닫으면 안 되는 경우는 지금 막 시작했거나(`start`) 실제로 등록
        // 쓰기가 걸린 순간(`approve`)뿐이다 — 그 둘은 닫아도 배경에서 계속
        // 진행돼 나중에 목록에 예상 못 한 결과가 나타날 수 있다(`Modal.tsx`의
        // `dismissible` 문서 그대로). 되묻기 답 반영(`answer`)이나 거절 반영
        // (`cancel`)은 실패해도 아무 것도 안 만들어지므로 언제든 닫아도 된다.
        dismissible={
          creation
            ? creation.phase !== 'running' ||
              creation.runningReason === 'answer' ||
              creation.runningReason === 'cancel'
            : true
        }
        title={
          creation
            ? creation.phase === 'running'
              ? {
                  start: '스킬을 만드는 중…',
                  answer: '답변을 반영하는 중…',
                  approve: '스킬을 등록하는 중…',
                  cancel: '취소하는 중…',
                }[creation.runningReason ?? 'start']
              : creation.phase === 'done'
                ? '스킬을 만들었습니다'
                : {
                    ask: '하나만 확인할게요',
                    confirm: '등록 확인',
                    cancelled: '다시 설명해 주세요',
                    error: '스킬을 만들지 못했습니다',
                  }[creation.phase]
            : editing?.skill
              ? '스킬 수정'
              : editing?.scope === 'team'
                ? '새 팀 스킬'
                : '새 스킬'
        }
        footer={
          creation ? (
            creation.phase === 'ask' ? (
              <>
                <Button variant="outline" onClick={closeCreation}>
                  닫기
                </Button>
                <Button variant="primary" disabled={!followupAnswer.trim()} onClick={() => void submitFollowup()}>
                  답변 보내기
                </Button>
              </>
            ) : creation.phase === 'confirm' ? (
              <>
                {/* **"거절"이 아니라 "다시 설명하기"다**(2026-08-24) — 이
                    화면의 거절은 완전히 그만두는 게 아니라 "이 초안 말고 다시
                    설명하고 싶다"는 뜻에 가깝다(스킬 생성 절차 자체가 몇 번을
                    고쳐 말해도 되는 걸 전제한다). 버튼 문구도 그 의도를
                    그대로 따라간다. */}
                <Button variant="outline" onClick={() => void submitConfirm(false)}>
                  다시 설명하기
                </Button>
                <Button variant="primary" onClick={() => void submitConfirm(true)}>
                  등록
                </Button>
              </>
            ) : creation.phase === 'done' ? (
              <Button variant="primary" onClick={finishCreation}>
                확인
              </Button>
            ) : creation.phase === 'cancelled' ? (
              <>
                <Button variant="outline" onClick={closeCreation}>
                  닫기
                </Button>
                {/* **막다른 화면이 아니다**(2026-08-24 UX 점검 — 예전엔
                    「닫기」하나뿐이라, 다시 만들려면 모달을 닫고 한 문장부터
                    다시 적어야 했다). 세션은 살아 있으므로 바로 이어서
                    설명할 수 있다. */}
                <Button
                  variant="primary"
                  disabled={!followupAnswer.trim()}
                  onClick={() => void continueAfterCancel()}
                >
                  이어서 설명하기
                </Button>
              </>
            ) : creation.phase === 'error' ? (
              <>
                <Button variant="outline" onClick={retryCreation}>
                  다시 시도
                </Button>
                <Button variant="primary" onClick={closeCreation}>
                  닫기
                </Button>
              </>
            ) : (
              // running — 진행 중에는 닫을 수 있는 버튼을 안 둔다. 대신 위
              // `dismissible`이 이유(`runningReason`)에 따라 X 버튼 자체를
              // 열어 준다 — 등록 확인의 「거절」처럼 빠르게 빠져나갈 방법이
              // 필요한 경우를 그쪽에서 이미 감당한다.
              undefined
            )
          ) : (
            <>
              <Button variant="outline" onClick={() => setEditing(null)}>
                취소
              </Button>
              {isSentenceCreate ? (
                <Button variant="primary" disabled={!sentenceReady} onClick={() => void goCreateHere()}>
                  만들기
                </Button>
              ) : (
                <Button variant="primary" disabled={!saveable || busy} onClick={() => void save()}>
                  {busy ? '저장하는 중…' : '저장'}
                </Button>
              )}
            </>
          )
        }
      >
        {creation ? (
          <div className={styles.formStack}>
            {creation.phase === 'running' && (
              <div className={styles.statusRow}>
                <Icon name="loader" size={16} color="var(--color-primary)" spin />
                <p className={styles.confirmText}>
                  {{
                    start: '스킬을 만드는 중입니다…',
                    answer: '답변을 반영하는 중입니다…',
                    approve: '스킬을 등록하는 중입니다…',
                    cancel: '취소를 반영하는 중입니다…',
                  }[creation.runningReason ?? 'start']}
                </p>
              </div>
            )}
            {/* 거절(다시 설명하기)을 반영하는 동안은 안전하게 닫아도 된다는
                걸 알려준다(2026-08-24) — 위 `dismissible`이 실제로 이 순간
                모달을 열어 두므로, 굳이 몇 초를 기다리지 않아도 된다는 걸
                말로도 확인해 준다. */}
            {creation.phase === 'running' && creation.runningReason === 'cancel' && (
              <p className={styles.cardSub}>지금 닫아도 괜찮습니다 — 등록되지 않습니다.</p>
            )}

            {creation.phase === 'ask' && (
              <div className={styles.formField}>
                {/* 모델 생성 문장이 아니라 화면이 직접 고정으로 보여주는
                    안내다(2026-08-24) — "지금 실제로 뭔가 보내는 채팅"으로
                    오해하지 않도록, 이 답이 스킬 설계에만 쓰인다는 걸 프롬프트
                    문구와 무관하게 항상 같은 자리에서 알려준다. */}
                <p className={styles.cardSub}>스킬을 등록하기 위한 질문입니다 — 지금 실행되지 않습니다.</p>
                <p className={styles.confirmText}>{creation.question}</p>
                <textarea
                  className={styles.formTextarea}
                  rows={5}
                  autoFocus
                  value={followupAnswer}
                  placeholder="이곳에 답변을 해주세요"
                  onChange={(event) => setFollowupAnswer(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                      event.preventDefault();
                      void submitFollowup();
                    }
                  }}
                />
              </div>
            )}

            {creation.phase === 'confirm' && (
              <>
                <p className={styles.confirmText}>다음 스킬을 등록합니다.</p>
                {(creation.actions ?? []).map((action, index) => {
                  const name = typeof action.args.name === 'string' ? action.args.name : action.name;
                  const description = typeof action.args.description === 'string' ? action.args.description : null;
                  return (
                    <div key={index} className={styles.formField}>
                      <span className={styles.formLabel}>{name}</span>
                      {description && <p className={styles.cardSub}>{description}</p>}
                    </div>
                  );
                })}
                {/* 이름·설명이 마음에 안 들면 등록 대신 「다시 설명하기」를
                    누르라는 걸 여기서도 한 번 더 짚는다(2026-08-24) — 「등록
                    전에 나온 설명을 고치고 싶으면?」에 대한 답. 이 칸 자체는
                    읽기 전용이다 — 고치려면 다시 설명해서 모델이 새 초안을
                    짓게 한다(값만 바꿔 승인하면 사람이 안 본 내용이 등록될
                    수 있어, 승인 게이트가 지금 보여준 값 그대로만 등록한다). */}
                <p className={styles.cardSub}>
                  이름이나 설명을 바꾸고 싶으면 「다시 설명하기」를 누르고 무엇을 바꿀지 알려주세요.
                </p>
              </>
            )}

            {creation.phase === 'done' && (
              <div className={styles.statusRow}>
                <Icon name="check-circle" size={16} color="var(--color-primary)" />
                <p className={styles.confirmText}>{creation.finalText || '스킬을 등록했습니다.'}</p>
              </div>
            )}

            {creation.phase === 'cancelled' && (
              // **막다른 화면이 아니다**(2026-08-24 UX 점검) — 모델이 실제로
              // 뭐라고 답했는지 보여주고, 바로 이어서 설명할 수 있는 입력칸을
              // 준다. 세션이 살아 있어(`closeCreation` 전) 그대로 이어진다.
              <div className={styles.formField}>
                <p className={styles.confirmText}>
                  {creation.finalText || '이 초안으로는 등록하지 않았습니다.'}
                </p>
                <p className={styles.cardSub}>
                  무엇을 바꿀지 알려주시면 이어서 다시 만들어 드릴게요. 그만하시려면 닫기를 눌러주세요.
                </p>
                <textarea
                  className={styles.formTextarea}
                  rows={4}
                  autoFocus
                  value={followupAnswer}
                  placeholder="예: 좀 더 격식 있는 톤으로, 이름을 다르게"
                  onChange={(event) => setFollowupAnswer(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                      event.preventDefault();
                      void continueAfterCancel();
                    }
                  }}
                />
              </div>
            )}

            {creation.phase === 'error' && (
              <p className={`${styles.notice} ${styles.noticeDanger}`}>{creation.errorText}</p>
            )}
          </div>
        ) : (
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
          ) : isSentenceCreate ? (
            <div className={styles.formField}>
              <label className={styles.formLabel} htmlFor="skill-sentence">
                어떤 스킬을 만들고 싶으신가요?
              </label>
              <textarea
                id="skill-sentence"
                className={styles.formTextarea}
                rows={5}
                value={editing?.sentence ?? ''}
                placeholder="예: 회의록을 요약해서 담당자별 할 일로 정리하는 스킬 만들어줘"
                onChange={(event) =>
                  setEditing((prev) => (prev ? { ...prev, sentence: event.target.value } : prev))
                }
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                    event.preventDefault();
                    void goCreateHere();
                  }
                }}
              />
              <p className={styles.cardSub}>
                한 문장으로 적으면 바로 여기서 만듭니다. 이름·설명은 스킬이 스스로 짓고, 더
                필요한 정보가 있으면 이어서 하나씩 되물어 확인합니다.
              </p>
            </div>
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
        )}
      </Modal>

      <Modal
        open={viewingSkill !== null}
        onClose={() => setViewingSkill(null)}
        title="팀 스킬 내용"
        footer={(
          <Button variant="primary" onClick={() => setViewingSkill(null)}>
            확인
          </Button>
        )}
      >
        <div className={styles.formStack}>
          <div className={styles.formField}>
            <span className={styles.formLabel}>이름</span>
            <p className={styles.confirmText}>{viewingSkill?.name}</p>
          </div>
          <div className={styles.formField}>
            <span className={styles.formLabel}>설명</span>
            <p className={styles.confirmText}>{viewingSkill?.description}</p>
          </div>
          <div className={styles.formField}>
            <span className={styles.formLabel}>내용</span>
            <pre className={styles.skillBodyPreview}>{viewingSkill?.body || '작성된 내용이 없습니다.'}</pre>
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
              onClick={() => confirming && void remove(confirming.scope, confirming.skill)}
            >
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
            ? '팀 공유 목록에서만 삭제됩니다. 팀원이 이미 가져간 개인 사본은 삭제되지 않습니다.'
            : '에이전트가 더 이상 이 절차를 따르지 않습니다.'}
        </p>
      </Modal>
    </div>
  );
}
